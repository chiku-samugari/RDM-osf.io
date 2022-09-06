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
from osf.models import ExportData, ExportDataRestore, BaseFileNode
from website.settings import WATERBUTLER_URL
from website.util import inspect_info  # noqa

logger = logging.getLogger(__name__)


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
            any_process_running = utils.check_any_running_restore_process(destination_id)
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

        # Update process status
        export_data_restore.update(status=ExportData.STATUS_STOPPING)

        # Get current task's result
        task = AbortableAsyncResult(task_id)
        result = task.result

        # Get current restore progress step
        current_progress_step = result.get('current_restore_step', -1)
        if current_progress_step == 3:
            return Response({'message': f'Cannot stop restore process.'}, status=status.HTTP_400_BAD_REQUEST)

        # Abort current task
        task.abort()
        if task.state != 'ABORTED':
            return Response({'message': f'Cannot stop restore process.'}, status=status.HTTP_400_BAD_REQUEST)

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
                'result': task.result if isinstance(task.result, str) or isinstance(task.result, dict) else {},
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

    first_project_id = response_file_json.get('files', [{}])[0].get('project', {}).get('id')

    # Check whether the restore destination storage is not empty
    destination_provider, destination_base_url = utils.get_provider_and_base_url_from_destination_storage(destination_id)
    internal = destination_base_url == WATERBUTLER_URL
    try:
        response = utils.get_file_data(first_project_id, destination_provider, '/', cookies,
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
    any_process_running = utils.check_any_running_restore_process(destination_id)
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
    export_data_restore = ExportDataRestore.objects.get(pk=export_data_restore_id)
    export_data_restore.update(task_id=task.request.id)
    current_process_step = 0
    task.update_state(state='PENDING', meta={'current_restore_step': current_process_step})
    try:
        export_data = ExportData.objects.filter(id=export_id, is_deleted=False)[0]
        export_base_url = export_data.location.waterbutler_url

        # Get file which have same information between export data and database
        # File info file: /export_{process_start}/file_info_{institution_guid}_{process_start}.json
        try:
            response = export_data.read_file_info_from_location(cookies)
            if response.status_code != 200:
                # Error
                logger.error(f'Return error with response: {response.content}')
                export_data_restore.update(status=ExportData.STATUS_STOPPED)
                return {'message': f'Cannot get file infomation list'}
            response_body = response.content
            response_file_content = response_body.decode('utf-8')
            response_file_json = json.loads(response_file_content)
        except Exception as e:
            logger.error(f'Exception: {e}')
            export_data_restore.update(status=ExportData.STATUS_STOPPED)
            return {'message': f'Cannot get file infomation list'}

        # Validate file info schema
        is_file_valid = utils.validate_file_json(response_file_json, 'file-info-schema.json')
        if not is_file_valid:
            export_data_restore.update(status=ExportData.STATUS_STOPPED)
            return {'message': f'The export data files are corrupted'}

        files = response_file_json.get('files', [])
        if len(files) == 0:
            return {}
        first_project_id = files[0].get('project', {}).get('id')

        # Check destination storage type (bulk-mounted or add-on)
        is_destination_addon_storage = utils.check_storage_type(destination_id)
        try:
            destination_provider, destination_base_url = utils.get_provider_and_base_url_from_destination_storage(
                destination_id)
            internal = destination_base_url == WATERBUTLER_URL

            check_if_restore_process_stopped(task, current_process_step)
            # move all old data in restore destination storage to a folder to back up folder
            if is_destination_addon_storage:
                response = utils.move_addon_folder_to_backup(first_project_id, destination_provider,
                                                             process_start=export_data_restore.process_start_timestamp,
                                                             cookies=cookies, internal=internal,
                                                             base_url=destination_base_url)
            else:
                response = utils.move_bulk_mount_folder_to_backup(first_project_id, destination_provider,
                                                                  process_start=export_data_restore.process_start_timestamp,
                                                                  cookies=cookies, internal=internal,
                                                                  base_url=destination_base_url)
            check_if_restore_process_stopped(task, current_process_step)
            current_process_step = 1
            task.update_state(state='PENDING', meta={'current_restore_step': current_process_step})
            if 'error' in response:
                # Error
                error_msg = response.get('error')
                logger.error(f'Return error with response: {error_msg}')
                export_data_restore.update(status=ExportData.STATUS_STOPPED)
                # restore_export_data_rollback_process(cookies, export_id, destination_id, export_data_restore_id,
                #                                       current_process_step)
                return {'message': f'Failed to move files to backup folder.'}
        except Exception as e:
            logger.error(f'Exception: {e}')
            export_data_restore.update(status=ExportData.STATUS_STOPPED)
            # restore_export_data_rollback_process(cookies, export_id, destination_id, export_data_restore_id,
            #                                       current_process_step)
            return {'message': f'Failed to move files to backup folder.'}

        with transaction.atomic():
            for file in files:
                check_if_restore_process_stopped(task, current_process_step)

                file_path = file.get('path')
                file_materialized_path = file.get('materialized_path')
                file_created_at = file.get('created_at')
                file_modified_at = file.get('modified_at')
                file_versions = file.get('version')
                file_project_id = file.get('project', {}).get('id')
                # Sort file by version id
                file_versions.sort(key=lambda k: k.get('identifier', 0))

                try:
                    for index, version in enumerate(file_versions):
                        check_if_restore_process_stopped(task, current_process_step)

                        # Prepare file name and file path for uploading
                        metadata = version.get('metadata', {})
                        file_hash = metadata.get('sha256', metadata.get('md5'))
                        if file_hash is None:
                            # Cannot get path in export data storage, pass this file
                            continue

                        file_hash_path = f'{export_data.export_data_folder_name}/{ExportData.EXPORT_DATA_FILES_FOLDER}/{file_hash}'

                        # If the destination storage is add-on institutional storage and source data storage is bulk-mounted storage:
                        # - for past version files, rename and save each version as filename_{version} in '_version_files' folder
                        # - the latest version is saved as the original
                        is_source_addon_storage = utils.check_storage_type(export_data.source.id)
                        if is_destination_addon_storage and not is_source_addon_storage:
                            new_file_materialized_path = file_materialized_path
                            if len(file_materialized_path) > 0 and index < len(file_versions) - 1:
                                # for past version files, rename and save each version as filename_{version} in '_version_files' folder
                                path_splits = new_file_materialized_path.split('/')

                                # add _{version} to file name
                                file_name = path_splits[len(path_splits) - 1]
                                file_splits = file_name.split('.')
                                file_splits[0] = f'{file_splits[0]}_{version}'
                                versioned_file_name = '.'.join(file_splits)

                                # add _version_files to folder path
                                path_splits.insert(len(path_splits) - 2, '_version_files')
                                path_splits[len(path_splits) - 1] = versioned_file_name
                                new_file_materialized_path = '/'.join(path_splits)
                            new_file_path = new_file_materialized_path
                        else:
                            new_file_path = file_path if is_source_addon_storage else file_materialized_path
                        # Download file from export data storage by version then upload that file to destination storage
                        destination_region = Region.objects.filter(id=destination_id)
                        destination_base_url, destination_settings = \
                            destination_region.values_list('waterbutler_url', 'waterbutler_settings')[0]
                        destination_provider = destination_settings.get('storage', {}).get('provider')

                        # Download file by version
                        is_download_url_internal = export_base_url == WATERBUTLER_URL
                        response = utils.get_file_data(ExportData.EXPORT_DATA_FAKE_NODE_ID, export_data.location.provider_name,
                                                       file_hash_path, cookies, is_download_url_internal,
                                                       export_base_url, version, location_id=export_data.location.id)
                        if response.status_code != 200:
                            logger.error(f'Download error content: {response.content}')
                            continue
                        download_data = response.content

                        # Upload downloaded file to new storage
                        is_upload_url_internal = destination_base_url == WATERBUTLER_URL
                        response_body = utils.upload_file_path(file_project_id, destination_provider, new_file_path,
                                                               download_data, cookies, is_upload_url_internal,
                                                               destination_base_url)
                        logger.info(f'Upload :{response_body}')
                        if response_body is None:
                            continue
                except Exception as e:
                    logger.error(f'Download or upload exception: {e}')
                    # Did not download or upload, pass this file
                    continue

            current_process_step = 2
            task.update_state(state='PENDING', meta={'current_restore_step': current_process_step})
            check_if_restore_process_stopped(task, current_process_step)

            # Update process data with process_end timestamp and 'Completed' status
            export_data_restore.update(process_end=timezone.now(), status=ExportData.STATUS_COMPLETED)

            current_process_step = 3
            task.update_state(state='PENDING', meta={'current_restore_step': current_process_step})
    except Exception as e:
        logger.error(f'Exception: {e}')
        export_data_restore.update(status=ExportData.STATUS_STOPPED)
        # restore_export_data_rollback_process(task, cookies, export_id, destination_id, export_data_restore_id, current_process_step)
        raise e

    return {}


def restore_export_data_rollback_process(task, cookies, export_id, destination_id, export_data_restore_id, process_step):
    export_data_restore = ExportDataRestore.objects.get(pk=export_data_restore_id)
    export_data_restore.update(task_id=task.request.id)

    export_data = ExportData.objects.filter(id=export_id, is_deleted=False)[0]
    # File info file: /export_{process_start}/file_info_{institution_guid}_{process_start}.json
    try:
        response = export_data.read_file_info_from_location(cookies)
        if response.status_code != 200:
            # Error
            logger.error(f'Return error with response: {response.content}')
            return {'message': f'Cannot get file infomation list'}
        response_body = response.content
        response_file_content = response_body.decode('utf-8')
        response_file_json = json.loads(response_file_content)
    except Exception as e:
        logger.error(f'Exception: {e}')
        return {'message': f'Cannot get file infomation list'}

    # Validate file info schema
    is_file_valid = utils.validate_file_json(response_file_json, 'file-info-schema.json')
    if not is_file_valid:
        return {'message': f'The file info file is corrupted'}

    files = response_file_json.get('files', [])
    if len(files) == 0:
        return {}
    first_project_id = files[0].get('project', {}).get('id')

    # Check destination storage type (bulk-mounted or add-on)
    is_destination_addon_storage = utils.check_storage_type(destination_id)

    destination_provider, destination_base_url = utils.get_provider_and_base_url_from_destination_storage(destination_id)
    internal = destination_base_url == WATERBUTLER_URL

    # Delete files, except the backup folder.
    if process_step == 1 or process_step == 2:
        try:
            utils.delete_all_files_except_backup(first_project_id, destination_provider, cookies,
                                                 internal, destination_base_url)
        except Exception as e:
            logger.error(f'Exception: {e}')
            export_data_restore.update(status=ExportData.STATUS_STOPPED)
            return {'message': f'Cannot connect to destination storage'}

    # Move all files from the backup folder out and delete backup folder
    if 0 <= process_step <= 2:
        try:
            if is_destination_addon_storage:
                response = utils.move_addon_folder_from_backup(first_project_id, destination_provider,
                                                               process_start=export_data_restore.process_start_timestamp,
                                                               cookies=cookies, internal=internal,
                                                               base_url=destination_base_url)
            else:
                response = utils.move_bulk_mount_folder_from_backup(first_project_id, destination_provider,
                                                                    process_start=export_data_restore.process_start_timestamp,
                                                                    cookies=cookies, internal=internal,
                                                                    base_url=destination_base_url)
            if 'error' in response:
                # Error
                error_msg = response.get('error')
                logger.error(f'Return error with response: {error_msg}')
                export_data_restore.update(status=ExportData.STATUS_STOPPED)
                return {'message': f'Failed to move backup folder to root'}
        except Exception as e:
            logger.error(f'Exception: {e}')
            export_data_restore.update(status=ExportData.STATUS_STOPPED)
            return {'message': f'Failed to move backup folder to root'}

    export_data_restore.update(status=ExportData.STATUS_STOPPED)
    return {}


def check_if_restore_process_stopped(task, current):
    if task.is_aborted():
        task.update_state(state='ABORTED',
                          meta={'current_restore_step': current})
        raise Exception('Restore process is stopped')
