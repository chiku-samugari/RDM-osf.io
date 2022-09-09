# -*- coding: utf-8 -*-
from __future__ import absolute_import

import inspect  # noqa
import json
import logging

from celery.contrib.abortable import AbortableAsyncResult
from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from addons.osfstorage.models import Region
from admin.rdm.utils import RdmPermissionMixin
from admin.rdm_custom_storage_location import tasks
from admin.rdm_custom_storage_location.export_data import utils
from osf.models import ExportData, ExportDataRestore
from website.settings import WATERBUTLER_URL
from website.util import inspect_info  # noqa

logger = logging.getLogger(__name__)
INSTITUTIONAL_STORAGE_PROVIDER_NAME = 'osfstorage'


class ProcessError(Exception):
    # Raise for exception found in process
    pass


@method_decorator(transaction.non_atomic_requests, name='dispatch')
class RestoreDataActionView(RdmPermissionMixin, APIView):
    raise_exception = True

    def post(self, request, **kwargs):
        destination_id = request.POST.get('destination_id')
        export_id = self.kwargs.get('export_id')
        cookies = request.COOKIES
        is_from_confirm_dialog = request.POST.get('is_from_confirm_dialog', default=False)
        if destination_id is None or export_id is None:
            return Response({'message': f'Missing required parameters.'}, status=status.HTTP_400_BAD_REQUEST)

        if not is_from_confirm_dialog:
            # Check the destination is available (not in restore process or checking restore data process)
            any_process_running = utils.check_for_any_running_restore_process(destination_id)
            if any_process_running:
                return Response({'message': f'Cannot restore in this time.'}, status=status.HTTP_400_BAD_REQUEST)

            result = check_before_restore_export_data(cookies, export_id, destination_id)
            if result.get('open_dialog'):
                # If open_dialog is True, return HTTP 200 with empty response
                return Response({}, status=status.HTTP_200_OK)
            elif result.get('message'):
                # If there is error message, return HTTP 400
                return Response({'message': result.get('message')}, status=status.HTTP_400_BAD_REQUEST)
            else:
                # Otherwise, start restore data task and return task id
                return prepare_for_restore_export_data_process(cookies, export_id, destination_id)
        else:
            # Start restore data task and return task id
            return prepare_for_restore_export_data_process(cookies, export_id, destination_id)


@method_decorator(transaction.non_atomic_requests, name='dispatch')
class StopRestoreDataActionView(RdmPermissionMixin, APIView):
    raise_exception = True

    def post(self, request, *args, **kwargs):
        task_id = request.POST.get('task_id')
        destination_id = request.POST.get('destination_id')
        export_id = self.kwargs.get('export_id')
        cookies = request.COOKIES

        if not destination_id or not export_id or not task_id:
            return Response({'message': f'Missing required parameters.'}, status=status.HTTP_400_BAD_REQUEST)

        # Get corresponding export data restore record
        export_data_restore_set = ExportDataRestore.objects.filter(task_id=task_id, export_id=export_id, destination_id=destination_id)
        if not export_data_restore_set.exists():
            return Response({'message': f'Permission denied for this restore process'}, status=status.HTTP_400_BAD_REQUEST)
        export_data_restore = export_data_restore_set.first()

        # Get current task's result
        task = AbortableAsyncResult(task_id)
        state = task.state
        result = task.result

        # Get current restore progress step
        current_progress_step = result.get('current_restore_step', -1)
        if current_progress_step >= 4:
            return Response({'message': f'Cannot stop restore process at this time.'}, status=status.HTTP_400_BAD_REQUEST)

        # Update process status
        export_data_restore.update(status=ExportData.STATUS_STOPPING)

        if state != 'STARTED' and state != 'PENDING':
            export_data_restore.update(status=ExportData.STATUS_ERROR)
            return Response({'message': f'Cannot stop restore process at this time.'}, status=status.HTTP_400_BAD_REQUEST)

        # Abort current task
        task.abort()
        # task.revoke(terminate=True)
        # Start rollback restore export data process
        process = tasks.run_restore_export_data_rollback_process.delay(cookies, export_id, destination_id,
                                                                       export_data_restore.pk, current_progress_step)
        return Response({'task_id': process.task_id}, status=status.HTTP_200_OK)


class CheckTaskStatusRestoreDataActionView(RdmPermissionMixin, APIView):
    def get(self, request, **kwargs):
        task_id = request.GET.get('task_id')
        if task_id is None:
            return Response({'message': f'Missing required parameters.'}, status=status.HTTP_400_BAD_REQUEST)
        task = AbortableAsyncResult(task_id)
        response = {
            'state': task.state,
        }
        if task.result is not None:
            response = {
                'state': task.state,
                'result': task.result if isinstance(task.result, dict) else str(task.result),
            }
        return Response(response, status=status.HTTP_200_OK if task.state != 'FAILURE' else status.HTTP_400_BAD_REQUEST)


def check_before_restore_export_data(cookies, export_id, destination_id):
    # Get export file (/export_{process_start}/export_data_{institution_guid}_{process_start}.json)
    export_data = ExportData.objects.filter(id=export_id, is_deleted=False)[0]
    try:
        response = export_data.read_export_data_from_location(cookies)
        if response.status_code != 200:
            # Error
            logger.error(f'Return error with response: {response.content}')
            return {'open_dialog': False, 'message': f'Cannot connect to the export data storage location'}
        response_body = response.content
        response_file_content = response_body.decode('utf-8')
        response_file_json = json.loads(response_file_content)
    except Exception as e:
        logger.error(f'Exception: {e}')
        return {'open_dialog': False, 'message': f'Cannot connect to the export data storage location'}

    # Validate export file schema
    is_file_valid = utils.validate_file_json(response_file_json, 'export-data-schema.json')
    if not is_file_valid:
        return {'open_dialog': False, 'message': f'The export data files are corrupted'}

    # Get file info file: /export_{process_start}/file_info_{institution_guid}_{process_start}.json
    try:
        response = export_data.read_file_info_from_location(cookies)
        if response.status_code != 200:
            # Error
            logger.error(f'Return error with response: {response.content}')
            return {'open_dialog': False, 'message': f'Cannot connect to the export data storage location'}
        response_body = response.content
        response_file_content = response_body.decode('utf-8')
        response_file_json = json.loads(response_file_content)
    except Exception as e:
        logger.error(f'Exception: {e}')
        return {'open_dialog': False, 'message': f'Cannot connect to the export data storage location'}

    # Validate file info schema
    is_file_valid = utils.validate_file_json(response_file_json, 'file-info-schema.json')
    if not is_file_valid:
        return {'open_dialog': False, 'message': f'The export data files are corrupted'}

    destination_first_project_id = response_file_json.get('files', [{}])[0].get('project', {}).get('id')

    # Check whether the restore destination storage is not empty
    destination_region = Region.objects.filter(id=destination_id).first()
    if not destination_region:
        raise {'open_dialog': False, 'message': f'Failed to get destination storage information'}
    destination_base_url = destination_region.waterbutler_url
    destination_provider = INSTITUTIONAL_STORAGE_PROVIDER_NAME
    internal = destination_base_url == WATERBUTLER_URL
    try:
        response = utils.get_file_data(destination_first_project_id, destination_provider, '/', cookies,
                                       internal, destination_base_url, get_file_info=True)
        if response.status_code != 200:
            # Error
            logger.error(f'Return error with response: {response.content}')
            return {'open_dialog': False, 'message': f'Cannot connect to destination storage'}

        response_body = response.json()
        data = response_body.get('data')
        if len(data) != 0:
            # Destination storage is not empty, show confirm dialog
            return {'open_dialog': True}
    except Exception as e:
        logger.error(f'Exception: {e}')
        return {'open_dialog': False, 'message': f'Cannot connect to destination storage'}

    # Destination storage is empty, return False
    return {'open_dialog': False}


def prepare_for_restore_export_data_process(cookies, export_id, destination_id):
    # Check the destination is available (not in restore process or checking restore data process)
    any_process_running = utils.check_for_any_running_restore_process(destination_id)
    if any_process_running:
        return Response({'message': f'Cannot restore in this time.'}, status=status.HTTP_400_BAD_REQUEST)

    # Try to add new process record to DB
    export_data_restore = ExportDataRestore(export_id=export_id, destination_id=destination_id,
                                            status=ExportData.STATUS_RUNNING)
    export_data_restore.save()
    # If user clicked 'Restore' button in confirm dialog, start restore data task and return task id
    process = tasks.run_restore_export_data_process.delay(cookies, export_id, destination_id,
                                                          export_data_restore.pk)
    return Response({'task_id': process.task_id}, status=status.HTTP_200_OK)


def restore_export_data_process(task, cookies, export_id, destination_id, export_data_restore_id):
    current_process_step = 0
    task.update_state(state='PENDING', meta={'current_restore_step': current_process_step})
    try:
        export_data_restore = ExportDataRestore.objects.get(pk=export_data_restore_id)
        export_data_restore.update(task_id=task.request.id)

        export_data = ExportData.objects.filter(id=export_id, is_deleted=False)[0]
        export_base_url = export_data.location.waterbutler_url

        # Get file which have same information between export data and database
        # File info file: /export_{process_start}/file_info_{institution_guid}_{process_start}.json
        try:
            response = export_data.read_file_info_from_location(cookies)
            if response.status_code != 200:
                # Error
                logger.error(f'Return error with response: {response.content}')
                raise ProcessError(f'Cannot get file infomation list')
            response_body = response.content
            response_file_content = response_body.decode('utf-8')
            response_file_json = json.loads(response_file_content)
        except Exception as e:
            logger.error(f'Exception: {e}')
            raise ProcessError(f'Cannot get file infomation list')

        # Validate file info schema
        is_file_valid = utils.validate_file_json(response_file_json, 'file-info-schema.json')
        if not is_file_valid:
            raise ProcessError(f'The export data files are corrupted')

        files = response_file_json.get('files', [])
        if len(files) == 0:
            export_data_restore.update(process_end=timezone.make_naive(timezone.now(), timezone.utc),
                                       status=ExportData.STATUS_COMPLETED)
            return None
        destination_first_project_id = files[0].get('project', {}).get('id')

        # Check destination storage type (bulk-mounted or add-on)
        destination_region = export_data_restore.destination
        is_destination_addon_storage = export_data_restore.destination.is_add_on_storage
        destination_base_url = destination_region.waterbutler_url
        destination_provider = INSTITUTIONAL_STORAGE_PROVIDER_NAME
        internal = destination_base_url == WATERBUTLER_URL

        check_if_restore_process_stopped(task, current_process_step)
        current_process_step = 1
        task.update_state(state='PENDING', meta={'current_restore_step': current_process_step})
        with transaction.atomic():
            try:
                # move all old data in restore destination storage to a folder to back up folder
                if is_destination_addon_storage:
                    response = utils.move_addon_folder_to_backup(
                        destination_first_project_id,
                        destination_provider,
                        process_start=export_data_restore.process_start_timestamp,
                        cookies=cookies,
                        callback_log=False,
                        internal=internal,
                        base_url=destination_base_url)
                else:
                    response = utils.move_bulk_mount_folder_to_backup(
                        destination_first_project_id,
                        destination_provider,
                        process_start=export_data_restore.process_start_timestamp,
                        cookies=cookies,
                        callback_log=False,
                        internal=internal,
                        base_url=destination_base_url)
                check_if_restore_process_stopped(task, current_process_step)
                if response and 'error' in response:
                    # Error
                    error_msg = response.get('error')
                    logger.error(f'Return error with response: {error_msg}')
                    raise ProcessError(f'Failed to move files to backup folder.')
                current_process_step = 2
                task.update_state(state='PENDING', meta={'current_restore_step': current_process_step})
            except Exception as e:
                logger.error(f'Exception: {e}')
                raise ProcessError(f'Failed to move files to backup folder.')

            for file in files:
                check_if_restore_process_stopped(task, current_process_step)

                file_materialized_path = file.get('materialized_path')
                file_versions = file.get('version')
                file_project_id = file.get('project', {}).get('id')
                file_tags = file.get('tags')
                file_timestamp = file.get('timestamp')
                # Sort file by version id
                file_versions.sort(key=lambda k: k.get('identifier', 0))

                try:
                    for index, version in enumerate(file_versions):
                        check_if_restore_process_stopped(task, current_process_step)

                        # Prepare file name and file path for uploading
                        metadata = version.get('metadata', {})
                        file_hash = metadata.get('sha256', metadata.get('md5'))
                        version_id = version.get('identifier')
                        if file_hash is None or version_id is None:
                            # Cannot get path in export data storage, pass this file
                            continue

                        file_hash_path = f'/{export_data.export_data_folder_name}/{ExportData.EXPORT_DATA_FILES_FOLDER}/{file_hash}'

                        # If the destination storage is add-on institutional storage:
                        # - for past version files, rename and save each version as filename_{version} in '_version_files' folder
                        # - the latest version is saved as the original
                        if is_destination_addon_storage:
                            new_file_materialized_path = file_materialized_path
                            if len(file_materialized_path) > 0 and index < len(file_versions) - 1:
                                # for past version files, rename and save each version as filename_{version} in '_version_files' folder
                                path_splits = new_file_materialized_path.split('/')

                                # add _{version} to file name
                                file_name = path_splits[len(path_splits) - 1]
                                file_splits = file_name.split('.')
                                file_splits[0] = f'{file_splits[0]}_{version_id}'
                                versioned_file_name = '.'.join(file_splits)

                                # add _version_files to folder path
                                path_splits.insert(len(path_splits) - 1, '_version_files')
                                path_splits[len(path_splits) - 1] = versioned_file_name
                                new_file_materialized_path = '/'.join(path_splits)
                                logger.info(new_file_materialized_path)
                            new_file_path = new_file_materialized_path
                        else:
                            new_file_path = file_materialized_path
                        logger.info(new_file_path)
                        # Download file by version
                        response = export_data.read_data_file_from_location(cookies, file_hash_path,
                                                                            base_url=export_base_url)
                        if response.status_code != 200:
                            logger.error(f'Download error content: {response.content}')
                            continue
                        download_data = response.content

                        # Upload downloaded file to new storage
                        is_upload_url_internal = destination_base_url == WATERBUTLER_URL
                        response_body = utils.upload_file_path(file_project_id, destination_provider, new_file_path,
                                                               download_data, cookies, internal=is_upload_url_internal,
                                                               base_url=destination_base_url)
                        if response_body is None:
                            continue

                        # Add info to DB

                except Exception as e:
                    logger.error(f'Download or upload exception: {e}')
                    check_if_restore_process_stopped(task, current_process_step)
                    # Did not download or upload, pass this file
                    continue

        check_if_restore_process_stopped(task, current_process_step)
        current_process_step = 3
        task.update_state(state='PENDING', meta={'current_restore_step': current_process_step})

        # Update process data with process_end timestamp and 'Completed' status
        export_data_restore.update(process_end=timezone.make_naive(timezone.now(), timezone.utc),
                                   status=ExportData.STATUS_COMPLETED)

        check_if_restore_process_stopped(task, current_process_step)
        current_process_step = 4
        task.update_state(state='PENDING', meta={'current_restore_step': current_process_step})
    except Exception as e:
        logger.error(f'Exception: {e}')
        if task.is_aborted():
            task.update_state(state='ABORTED',
                              meta={'current_restore_step': current_process_step})
        else:
            restore_export_data_rollback_process(task, cookies, export_id, destination_id, export_data_restore_id, process_step=current_process_step)
        raise e

    return None


def restore_export_data_rollback_process(task, cookies, export_id, destination_id, export_data_restore_id, process_step):
    if process_step >= 4:
        # Restore process is already done, cannot stop anymore
        return None

    export_data_restore = ExportDataRestore.objects.get(pk=export_data_restore_id)
    if export_data_restore.task_id != task.request.id:
        export_data_restore.update(task_id=task.request.id)

    if process_step == 0 or process_step is None:
        # Restore process has not done anything related to files
        export_data_restore.update(process_end=timezone.make_naive(timezone.now(), timezone.utc),
                                   status=ExportData.STATUS_STOPPED)
        return None

    try:
        with transaction.atomic():
            export_data = ExportData.objects.filter(id=export_id, is_deleted=False)[0]
            # File info file: /export_{process_start}/file_info_{institution_guid}_{process_start}.json
            try:
                response = export_data.read_file_info_from_location(cookies)
                if response.status_code != 200:
                    # Error
                    logger.error(f'Return error with response: {response.content}')
                    raise ProcessError(f'Cannot get file infomation list')
                response_body = response.content
                response_file_content = response_body.decode('utf-8')
                response_file_json = json.loads(response_file_content)
            except Exception as e:
                logger.error(f'Exception: {e}')
                raise ProcessError(f'Cannot get file infomation list')

            # Validate file info schema
            is_file_valid = utils.validate_file_json(response_file_json, 'file-info-schema.json')
            if not is_file_valid:
                raise ProcessError(f'The file info file is corrupted')

            files = response_file_json.get('files', [])
            if len(files) == 0:
                export_data_restore.update(process_end=timezone.make_naive(timezone.now(), timezone.utc),
                                           status=ExportData.STATUS_STOPPED)
                return None
            destination_first_project_id = files[0].get('project', {}).get('id')

            # Check destination storage type (bulk-mounted or add-on)
            destination_region = export_data_restore.destination
            is_destination_addon_storage = export_data_restore.destination.is_add_on_storage
            destination_base_url = destination_region.waterbutler_url
            destination_provider = INSTITUTIONAL_STORAGE_PROVIDER_NAME
            internal = destination_base_url == WATERBUTLER_URL

            location_id = export_data.location.id
            # Delete files, except the backup folder.
            if process_step == 2 or process_step == 3:
                try:
                    utils.delete_all_files_except_backup(
                        destination_first_project_id, destination_provider,
                        cookies, location_id,
                        internal, destination_base_url)
                except Exception as e:
                    logger.error(f'Exception: {e}')
                    raise ProcessError(f'Cannot connect to destination storage')

            # Move all files from the backup folder out and delete backup folder
            if 0 < process_step < 4:
                try:
                    if is_destination_addon_storage:
                        response = utils.move_addon_folder_from_backup(
                            destination_first_project_id,
                            destination_provider,
                            process_start=export_data_restore.process_start_timestamp,
                            cookies=cookies,
                            callback_log=False,
                            internal=internal,
                            base_url=destination_base_url)
                    else:
                        response = utils.move_bulk_mount_folder_from_backup(
                            destination_first_project_id,
                            destination_provider,
                            process_start=export_data_restore.process_start_timestamp,
                            cookies=cookies,
                            callback_log=False,
                            internal=internal,
                            base_url=destination_base_url)
                    if 'error' in response:
                        # Error
                        error_msg = response.get('error')
                        logger.error(f'Return error with response: {error_msg}')
                        raise ProcessError(f'Failed to move backup folder to root')
                except Exception as e:
                    logger.error(f'Exception: {e}')
                    raise ProcessError(f'Failed to move backup folder to root')

        export_data_restore.update(process_end=timezone.make_naive(timezone.now(), timezone.utc),
                                   status=ExportData.STATUS_STOPPED)
    except Exception as e:
        export_data_restore.update(status=ExportData.STATUS_ERROR)
        raise e

    return None


def check_if_restore_process_stopped(task, current_process_step):
    if task.is_aborted():
        task.update_state(state='ABORTED',
                          meta={'current_restore_step': current_process_step})
        raise ProcessError(f'Restore process is stopped')
