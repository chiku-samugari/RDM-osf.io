# -*- coding: utf-8 -*-
import inspect  # noqa
import logging

from addons.base import signals as file_signals
from addons.base.utils import get_root_institutional_storage
from addons.osfstorage.models import OsfStorageFileNode, Region
from api.base import settings as api_settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import Sum
from django.db.models.functions import Coalesce
from api.base.settings import ADDON_METHOD_PROVIDER, NII_STORAGE_REGION_ID
from osf.models import (
    AbstractNode, BaseFileNode, FileLog, FileInfo, Guid, OSFUser, UserQuota,
    ProjectStorageType
)
from django.utils import timezone
from osf.models.user_storage_quota import UserStorageQuota
from rest_framework import status as http_status
from framework.exceptions import HTTPError
from website.util import inspect_info  # noqa

# import inspect
logger = logging.getLogger(__name__)
ENABLE_QUOTA_PROVIDERS = ADDON_METHOD_PROVIDER + ['osfstorage']


def used_quota(user_id, storage_type=UserQuota.NII_STORAGE):
    guid = Guid.objects.get(
        _id=user_id,
        content_type_id=ContentType.objects.get_for_model(OSFUser).id
    )
    projects_ids = AbstractNode.objects.filter(
        projectstoragetype__storage_type=storage_type,
        is_deleted=False,
        creator_id=guid.object_id
    ).values_list('id', flat=True)
    if storage_type != UserQuota.NII_STORAGE:
        files_ids = BaseFileNode.objects.filter(
            target_object_id__in=projects_ids,
            target_content_type_id=ContentType.objects.get_for_model(AbstractNode),
            deleted_on=None,
            deleted_by_id=None,
        ).values_list('id', flat=True)
    else:
        files_ids = OsfStorageFileNode.objects.filter(
            target_object_id__in=projects_ids,
            target_content_type_id=ContentType.objects.get_for_model(AbstractNode),
            deleted_on=None,
            deleted_by_id=None,
        ).values_list('id', flat=True)
    db_sum = FileInfo.objects.filter(file_id__in=files_ids).aggregate(
        filesize_sum=Coalesce(Sum('file_size'), 0))
    return db_sum['filesize_sum'] if db_sum['filesize_sum'] is not None else 0


def update_user_used_quota(user, storage_type=UserQuota.NII_STORAGE):
    used = used_quota(user._id, storage_type)

    try:
        user_quota = UserQuota.objects.get(
            user=user,
            storage_type=storage_type
        )
        user_quota.used = used
        user_quota.save()
    except UserQuota.DoesNotExist:
        UserQuota.objects.create(
            user=user,
            storage_type=storage_type,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=used,
        )


def abbreviate_size(size):
    size = float(size)
    abbr_dict = {0: 'B', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}

    power = 0
    while size > api_settings.BASE_FOR_METRIC_PREFIX and power < 4:
        size /= api_settings.BASE_FOR_METRIC_PREFIX
        power += 1

    return (size, abbr_dict[power])

def get_quota_info(user, storage_type=UserQuota.NII_STORAGE):
    try:
        user_quota = user.userquota_set.get(storage_type=storage_type)
        return (user_quota.max_quota, user_quota.used)
    except UserQuota.DoesNotExist:
        return (api_settings.DEFAULT_MAX_QUOTA, used_quota(user._id, storage_type))


def get_storage_quota_info(user, region):
    """ Get the per-user-per-storage info

    :param Object user: User is using the storage
    :param Object region: Institution storage
    :return tuple: Tuple of storage's quota and used quota

    """
    try:
        user_storage_quota = user.userstoragequota_set.get(region=region)
        return user_storage_quota.max_quota, user_storage_quota.used
    except UserStorageQuota.DoesNotExist:
        return (
            api_settings.DEFAULT_MAX_QUOTA,
            recalculate_used_of_user_by_region(user._id, region.id)
        )


def get_project_storage_type(node):
    try:
        return ProjectStorageType.objects.get(node=node).storage_type
    except ProjectStorageType.DoesNotExist:
        return ProjectStorageType.NII_STORAGE

@file_signals.file_updated.connect
def update_used_quota(self, target, user, event_type, payload):
    data = dict(payload.get('metadata', {}))
    logger.debug(f'payload data is {dict(payload)}')
    provider = data.get('provider')
    # Case move/copy
    if not provider and payload.get('destination'):
        provider = payload['destination']['provider']
    if provider not in ENABLE_QUOTA_PROVIDERS:
        return
    kind = data.get('kind')
    # Case move
    if not kind:
        kind = payload['destination']['kind']
    action = dict(payload).get('action')
    target_content_type_id = ContentType.objects.get_for_model(AbstractNode)
    file_node = None
    # When move/rename won't get basefilenode
    if event_type != FileLog.FILE_MOVED and event_type != FileLog.FILE_COPIED and event_type != FileLog.FILE_RENAMED:
        try:
            if provider not in ADDON_METHOD_PROVIDER:
                if data.get('path'):
                    file_node = BaseFileNode.objects.get(
                        _id=data.get('path').strip('/'),
                        target_object_id=target.id,
                        target_content_type_id=target_content_type_id
                    )
                # elif payload['destination']['path']:
                #     logger.warning('dest path '+str(payload['destination']['path']))
                #     file_node = BaseFileNode.objects.get(
                #         _id=payload['destination']['path'].strip('/'),
                #         target_object_id=target.id,
                #         target_content_type_id=target_content_type_id
                #     )
            else:
                if data.get('kind') == 'folder' and action == 'create_folder':
                    return
                if payload.get('root_path'):
                    root_path = payload.get('root_path').strip('/')
                # elif payload ['destination']['root_path']:
                #     root_path = payload ['destination']['root_path'].strip('/')
                materialized = data.get('materialized')
                name = data.get('name')
                # if event_type == FileLog.FILE_MOVED:
                #     root_path = payload['destination']['root_path'].strip('/')
                #     materialized = payload['destination']['materialized']
                #     name = payload['destination']['name']
                logger.debug(f'provider is {provider}')
                logger.debug(f'root_path is {root_path}')
                logger.debug(f'materialized is {materialized}')
                # If provider is onedrivebusiness will find by materialized_path
                if provider == 'onedrivebusiness':
                    file_node = BaseFileNode.objects.filter(
                        _materialized_path='/' + materialized.strip('/'),
                        name=name,
                        provider=provider,
                        type='osf.onedrivebusinessfile',
                        target_object_id=target.id,
                        target_content_type=target_content_type_id,
                    ).order_by('-id').first()
                else:
                    file_node = BaseFileNode.objects.filter(
                        _path='/' + root_path + '/' + materialized.strip('/'),
                        name=name,
                        provider=provider,
                        target_object_id=target.id,
                        target_content_type=target_content_type_id
                    ).order_by('-id').first()

            if file_node is None and kind != 'folder':
                raise BaseFileNode.DoesNotExist
        except BaseFileNode.DoesNotExist:
            logger.error('FileNode not found, cannot update used quota!')
            return
        storage_type = get_project_storage_type(target)

    if event_type == FileLog.FILE_ADDED:
        file_added(target, payload, file_node, storage_type)
    elif event_type == FileLog.FILE_REMOVED:
        # Remove from bulkmount
        if provider not in ADDON_METHOD_PROVIDER:
            node_removed(target, payload, file_node, storage_type)
        # Remove file from addon
        elif kind == 'file':
            file_node.is_deleted = True
            file_node.deleted = timezone.now()
            file_node.deleted_on = file_node.deleted
            file_node.type = 'osf.trashedfile'
            file_node.deleted_by_id = user.id
            file_node.save()
            node_removed(target, payload, file_node, storage_type)
        # Remove folder from addon
        elif kind == 'folder':
            # if provider in ADDON_METHOD_PROVIDER:
            root_file_node = BaseFileNode.objects.get(_id=payload.get('root_path').strip('/'))
            list_file_node = BaseFileNode.objects.filter(
                _materialized_path__startswith=data.get('materialized'),
                provider=provider,
                deleted=None,
                target_object_id=target.id,
                target_content_type_id=target_content_type_id,
                parent_id=root_file_node.id if root_file_node else None
            ).all()
            # else:
            #     list_file_node = BaseFileNode.objects.filter(
            #         _materialized_path__startswith=data.get('materialized'),
            #         provider=provider,
            #         deleted=None,
            #         target_object_id=target.id,
            #         target_content_type_id=target_content_type_id
            #     ).all()
            for file_node in list_file_node:
                file_node.is_deleted = True
                file_node.deleted = timezone.now()
                file_node.deleted_on = file_node.deleted
                file_node.deleted_by_id = user.id
                file_node.type = file_node.type.replace(provider, 'trashed')
                file_node.save()
                if file_node.type == 'osf.trashedfile':
                    node_removed(target, payload, file_node, storage_type)
        if file_node is None:
            logging.error('FileNode not found, cannot update used quota!')
            return
    elif event_type == FileLog.FILE_UPDATED:
        file_modified(target, user, payload, file_node, storage_type)
    elif event_type == FileLog.FILE_MOVED:
        file_moved(target, payload)
    elif event_type == FileLog.FILE_COPIED:
        file_copied(target, payload)

def file_added(target, payload, file_node, storage_type):
    file_size = int(payload['metadata']['size'])
    if file_size < 0:
        return

    region_id = get_region_id_of_institutional_storage_by_path(
        target, payload['provider'], payload['metadata']['path'], storage_type, file_node)
    if region_id is None:
        logging.error('Institutional storage not found, cannot update used quota!')
        return

    user_storage_quota, _ = UserStorageQuota.objects.select_for_update().get_or_create(
        user=target.creator,
        defaults={'max_quota': api_settings.DEFAULT_MAX_QUOTA},
        region_id=region_id
    )

    user_storage_quota.used += file_size
    user_storage_quota.save()

    FileInfo.objects.create(file=file_node, file_size=file_size)


def node_removed(target, payload, file_node, storage_type):
    region_id = get_region_id_of_institutional_storage_by_path(
        target, payload['provider'], payload['metadata']['path'], storage_type, file_node)
    if region_id is None:
        logging.error('Institutional storage not found, cannot update used quota!')
        return

    user_storage_quota, _ = UserStorageQuota.objects.select_for_update().get_or_create(
        user=target.creator,
        defaults={'max_quota': api_settings.DEFAULT_MAX_QUOTA},
        region_id=region_id
    )

    if user_storage_quota is not None:
        if 'osf.trashed' not in file_node.type:
            logging.error('FileNode is not trashed, cannot update used quota!')
            return

        for removed_file in get_node_file_list(file_node):
            try:
                file_info = FileInfo.objects.get(file=removed_file)
            except FileInfo.DoesNotExist:
                logging.error('FileInfo not found, cannot update used quota!')
                continue

            file_size = min(file_info.file_size, user_storage_quota.used)
            user_storage_quota.used -= file_size
        user_storage_quota.save()

def file_modified(target, user, payload, file_node, storage_type):
    file_size = int(payload['metadata']['size'])
    if file_size < 0:
        return

    region_id = get_region_id_of_institutional_storage_by_path(target, payload['provider'], payload['metadata']['path'], storage_type, file_node)
    if region_id is None:
        logging.error('Institutional storage not found, cannot update used quota!')
        return

    user_storage_quota, _ = UserStorageQuota.objects.select_for_update().get_or_create(
        user=target.creator,
        defaults={'max_quota': api_settings.DEFAULT_MAX_QUOTA},
        region_id=region_id
    )

    try:
        file_info = FileInfo.objects.get(file=file_node)
    except FileInfo.DoesNotExist:
        file_info = FileInfo(file=file_node, file_size=0)

    user_storage_quota.used += file_size - file_info.file_size
    if user_storage_quota.used < 0:
        user_storage_quota.used = 0
    user_storage_quota.save()

    file_info.file_size = file_size
    file_info.save()


def get_file_size(children):
    children = children.get('children', [])
    size = 0
    for child in children:
        if child['kind'] == 'file':
            size += int(child['size'])
        else:
            size += get_file_size(child)
    return size


def file_moved(target, payload):
    """Update per-user-per-storage used quota when moving file

    :param Object target: Id of project
    :param str path: _Id of file or folder
    :param str provider: The addon name
    :return Object: The addon is found

    """
    if isinstance(target, AbstractNode):
        storage_type = get_project_storage_type(target)
        if storage_type == ProjectStorageType.CUSTOM_STORAGE:
            file_size = -1
            dest_size = payload['destination'].get('size', None)
            children = payload['destination'].get('children', None)
            # Move file
            if dest_size is not None:
                file_size = int(dest_size)
            # Move folder
            elif children is not None:
                file_size = get_file_size(payload['destination'])
            logger.debug(f'file size is {file_size}')
            if file_size < 0:
                return

            # Move to bulkmount
            if payload['destination']['provider'] == 'osfstorage':
                node_addon_destination = get_addon_osfstorage_by_path(
                    target,
                    payload['destination']['path'] if payload['destination']['kind'] == 'file' else payload['destination']['root_path'] + '/' + payload['destination']['materialized'],
                    payload['destination']['provider']
                )

                if node_addon_destination is not None:
                    update_institutional_storage_used_quota(
                        target.creator,
                        node_addon_destination.region,
                        file_size
                    )
            # Move to addon
            elif payload['destination']['provider'] in ADDON_METHOD_PROVIDER:
                node_addon_destination = get_addon_osfstorage_by_path(
                    target,
                    payload['destination']['root_path'] + '/' + payload['destination']['materialized'],
                    payload['destination']['provider']
                )

                if node_addon_destination is not None:
                    update_institutional_storage_used_quota(
                        target.creator,
                        node_addon_destination.region,
                        file_size
                    )

            source_node_id = payload['source']['nid']
            source_node = AbstractNode.objects.get(guids___id=source_node_id)
            # Move from bulkmount
            if payload['source']['provider'] == 'osfstorage' \
                    and source_node.type != 'osf.quickfilesnode':
                node_addon_source = get_addon_osfstorage_by_path(
                    target,
                    payload['source']['old_root_id'],
                    payload['source']['provider']
                )

                if node_addon_source is not None:
                    update_institutional_storage_used_quota(
                        target.creator,
                        node_addon_source.region,
                        file_size,
                        add=False
                    )
            # Move to addon
            elif payload['source']['provider'] in ADDON_METHOD_PROVIDER \
                    and source_node.type != 'osf.quickfilesnode':
                node_addon_source = get_addon_osfstorage_by_path(
                    target,
                    payload['source']['root_path'] + '/' + payload['source']['materialized'],
                    payload['source']['provider']
                )
                if node_addon_source is not None:
                    update_institutional_storage_used_quota(
                        target.creator,
                        node_addon_source.region,
                        file_size,
                        add=False
                    )

def update_default_storage(user):
    #logger.debug('----{}:{}::{} from {}:{}::{}'.format(*inspect_info(inspect.currentframe(), inspect.stack())))
    # logger.info(user)
    if user is not None:
        user_settings = user.get_addon('osfstorage')
        if user_settings is None:
            user_settings = user.add_addon('osfstorage')
        institution = user.affiliated_institutions.first()
        if institution is not None:
            region = Region.objects.filter(_id=institution._id).first()
            if region is None:
                # logger.info('Inside update_default_storage: region does not exist.')
                pass
            else:
                if user_settings.default_region._id != region._id:
                    user_settings.set_region(region.id)
                    logger.info(u'user={}, institution={}, user_settings.set_region({})'.format(user, institution.name, region.name))

def get_node_file_list(file_node):
    if 'file' in file_node.type:
        return [file_node]

    file_list = []
    folder_list = [file_node]

    while len(folder_list) > 0:
        folder_id_list = list(map(lambda f: f.id, folder_list))
        folder_list = []
        for child_file_node in BaseFileNode.objects.filter(parent_id__in=folder_id_list):
            if 'folder' in child_file_node.type:
                folder_list.append(child_file_node)
            else:  # file
                file_list.append(child_file_node)

    return file_list


def get_region_id_of_institutional_storage_by_path(target, provider, path, storage_type, file_node=None, root_path=None):
    region_id = NII_STORAGE_REGION_ID
    if storage_type != ProjectStorageType.CUSTOM_STORAGE:
        return region_id

    if provider == 'osfstorage':
        osf_node_setting = get_addon_osfstorage_by_path(target, path, provider)
        if osf_node_setting:
            region_id = osf_node_setting.region.id
        else:
            return None
    elif provider in ADDON_METHOD_PROVIDER:
        node_addon = None
        if file_node and hasattr(file_node, 'parent_id'):
            if hasattr(target, 'get_addon'):
                node_addon = target.get_addon(provider, root_id=file_node.parent_id)
        elif root_path:
            root_file_node = BaseFileNode.objects.filter(_id=root_path).first()
            if root_file_node:
                node_addon = target.get_addon(provider, root_id=root_file_node.id)
        institution = target.creator.affiliated_institutions.first()
        if institution and node_addon:
            regions = Region.objects.filter(
                _id=institution._id,
                waterbutler_settings__storage__provider=provider,
                id=node_addon.region.id
            )
            region = regions.first()
            if region is None:
                return None
            region_id = region.id
        else:
            return None
    return region_id


def get_addon_osfstorage_by_path(target, path, provider):
    """Get addon of project by path and provider name

    :param Object target: Project owns addon
    :param str path: _Id of file or folder
    :param str provider: The addon name
    :return Object: The addon is found

    """
    root_folder = get_root_institutional_storage(path.strip('/').split('/')[0])
    root_folder_id = None
    if root_folder is not None:
        root_folder_id = root_folder.id
    if hasattr(target, 'get_addon'):
        node_addon = target.get_addon(provider, root_id=root_folder_id)
        if node_addon is None:
            raise HTTPError(http_status.HTTP_400_BAD_REQUEST)
        return node_addon
    else:
        return None


def update_institutional_storage_used_quota(creator, region, size, add=True):
    """Update used per-user-per-storage

    :param Object creator: User is updated
    :param Object region: Institutional storage is updated
    :param int size: Size of file
    :param bool add: Add or subtract

    """
    try:
        user_storage_quota = UserStorageQuota.objects.select_for_update().get(
            user=creator,
            region=region
        )
        if add:
            user_storage_quota.used += size
        else:
            user_storage_quota.used -= size

        if user_storage_quota.used < 0:
            user_storage_quota.used = 0

        user_storage_quota.save()
        logger.debug(f'used quota was updated is {user_storage_quota}')
    except UserStorageQuota.DoesNotExist:
        storage_max_quota = api_settings.DEFAULT_MAX_QUOTA

        UserStorageQuota.objects.create(
            user=creator,
            region=region,
            max_quota=storage_max_quota,
            used=size
        )

        # Add max quota of user-per-storage to max quota of user
        user_quota = UserQuota.objects.get(
            user=creator,
            storage_type=UserQuota.CUSTOM_STORAGE
        )
        user_quota.max_quota += storage_max_quota
        user_quota.save()


def recalculate_used_quota_by_user(user_id, storage_type=UserQuota.NII_STORAGE):
    """Recalculate used per-user-per-storage

    :param str user_id: The user is recalculated
    """
    guid = Guid.objects.get(
        _id=user_id,
        content_type_id=ContentType.objects.get_for_model(OSFUser).id
    )
    projects = AbstractNode.objects.filter(
        projectstoragetype__storage_type=storage_type,
        is_deleted=False,
        creator_id=guid.object_id
    )

    if projects is not None:
        # Dict with key=region_id and value=used_quota
        used_quota_result = {}
        for project in projects:
            addons = project.get_osfstorage_addons()
            for addon in addons:
                sum = calculate_used_quota_by_institutional_storage(
                    project.id,
                    addon
                )
                if addon.region_id in used_quota_result.keys():
                    used_quota_result[addon.region_id] += sum
                else:
                    used_quota_result[addon.region_id] = sum

        # Update used quota for each institutional storage
        for region_id in used_quota_result:
            try:
                storage_quota = UserStorageQuota.objects.select_for_update().get(
                    user_id=guid.object_id,
                    region_id=region_id
                )
                storage_quota.used = used_quota_result[region_id]
                storage_quota.save()
            except UserStorageQuota.DoesNotExist:
                pass


def recalculate_used_of_user_by_region(user_id, region_id=NII_STORAGE_REGION_ID):
    """Recalculate used of user by region

    :param str user_id: The guid of user is recalculated
    :param int region_id: The ids of region
    """
    region_id = int(region_id)
    if region_id == NII_STORAGE_REGION_ID:
        storage_type = UserQuota.NII_STORAGE
    else:
        storage_type = UserQuota.CUSTOM_STORAGE

    guid = Guid.objects.get(
        _id=user_id,
        content_type_id=ContentType.objects.get_for_model(OSFUser).id
    )
    projects = AbstractNode.objects.filter(
        projectstoragetype__storage_type=storage_type,
        is_deleted=False,
        creator_id=guid.object_id
    )

    used = 0
    if projects is None:
        return used

    _length = len(projects)
    for index, project in enumerate(projects):
        logger.debug(f'[{1 + index}/{_length}] project: {project._id}')
        addon = project.get_addon('osfstorage', region_id=region_id)
        if addon is None or addon.region_id != region_id:
            continue
        used += calculate_used_quota_by_institutional_storage(
            project.id,
            addon
        )

    try:
        storage_quota = UserStorageQuota.objects.select_for_update().get(
            user_id=guid.object_id,
            region_id=region_id
        )
        storage_quota.used = used
        storage_quota.save()
    except UserStorageQuota.DoesNotExist:
        pass
    return used


def get_file_ids_by_institutional_storage(result, project_id, root_id):
    """ Get all file ids of institutional storage in a project

    :param list result: Array of file id
    :param str project_id: Id of project
    :param str root_id: Id of storage root folder

    """
    children = BaseFileNode.objects.filter(
        target_object_id=project_id,
        target_content_type_id=ContentType.objects.get_for_model(AbstractNode),
        deleted_on=None,
        deleted_by_id=None,
        parent_id=root_id
    )
    if children is None:
        return
    else:
        for item in children:
            if item.type == 'osf.osfstoragefile':
                result.append(item.id)
            elif item.type == 'osf.osfstoragefolder':
                get_file_ids_by_institutional_storage(
                    result,
                    project_id, item.id
                )


def calculate_used_quota_by_institutional_storage(project_id, osf_node_setting):
    """Calculate the total size of institutional storage in a project

    :param str project_id: Id of project
    :param object osf_node_setting: Osf node setting
    :return int: Total size of all files in storage
    """
    files_ids = []
    provider = osf_node_setting.region.waterbutler_settings['storage']['provider']
    if provider in ADDON_METHOD_PROVIDER:
        file_nodes = BaseFileNode.objects.filter(
            target_object_id=project_id,
            target_content_type_id=ContentType.objects.get_for_model(AbstractNode),
            deleted_on=None,
            deleted_by_id=None,
            provider=provider,
        )
        for item in file_nodes:
            if 'file' in item.type:
                files_ids.append(item)
    else:
        get_file_ids_by_institutional_storage(files_ids, project_id, osf_node_setting.root_node_id)

    files_info = FileInfo.objects.filter(file_id__in=files_ids)
    db_sum = files_info.aggregate(filesize_sum=Coalesce(Sum('file_size'), 0))
    return db_sum['filesize_sum'] or 0


def calculate_size_of_all_files_by_provider_name(projects, provider):
    """Calculate size of all addon method files in projects by provider name

    :param list projects: All projects
    :param string provider: provider name of addon storage
    :return int: Result
    """
    files_ids = []
    for project in projects:
        # get all files by provider name
        addon_method_file_ids = BaseFileNode.objects.filter(
            target_object_id=project.id,
            target_content_type_id=ContentType.objects.get_for_model(AbstractNode),
            deleted_on=None,
            deleted_by_id=None,
            provider=provider
        )
        for file in addon_method_file_ids:
            files_ids.append(file.id)

    db_sum = FileInfo.objects.filter(file_id__in=files_ids).aggregate(
        filesize_sum=Coalesce(Sum('file_size'), 0))
    return db_sum['filesize_sum'] if db_sum['filesize_sum'] is not None else 0


def user_per_storage_used_quota(institution, user, region):
    """Calculate per-user-per-storage used quota

    :param Institution institution: The institution of user
    :param Object user: The user are using the storage
    :param str region: Id of institutional storage
    :return int: Result

    """
    projects = institution.nodes.filter(creator_id=user.id)
    result = 0
    provider = region.waterbutler_settings['storage']['provider']

    if provider in ADDON_METHOD_PROVIDER:
        result = calculate_size_of_all_files_by_provider_name(projects, provider)
    else:
        for project in projects:
            addon = project.get_addon('osfstorage', region_id=region.id)
            if addon is not None:
                result += calculate_used_quota_by_institutional_storage(
                    project.id,
                    addon
                )
    return result


def update_institutional_storage_max_quota(user, region, max_quota):
    """ Update max quota for per-user-per-storage

    :param Object user: The user are using the storage
    :param Object region: The storage needs to be updated
    :param int max_quota: New max quota

    """
    old_max_quota = 0

    # Update user-per-storage max quota
    try:
        user_storage_quota = UserStorageQuota.objects.select_for_update().get(
            user=user,
            region=region
        )
        old_max_quota = user_storage_quota.max_quota
        user_storage_quota.max_quota = max_quota
        user_storage_quota.save()
    except UserStorageQuota.DoesNotExist:
        UserStorageQuota.objects.create(
            user=user,
            region=region,
            max_quota=max_quota,
        )

    # Update CUSTOM_STORAGE max quota of user
    try:
        user_quota = UserQuota.objects.select_for_update().get(
            user=user,
            storage_type=UserQuota.CUSTOM_STORAGE,
        )
        user_quota.max_quota += max_quota - old_max_quota

        if user_quota.max_quota < 0:
            user_quota.max_quota = 0
        user_quota.save()
    except UserQuota.DoesNotExist:
        UserQuota.objects.create(
            user=user,
            storage_type=UserQuota.CUSTOM_STORAGE,
            max_quota=max_quota,
        )

def file_copied(target, payload):
    """Update per-user-per-storage used quota when moving file

    :param Object target: Id of project
    :param str path: _Id of file or folder
    :param str provider: The addon name
    :return Object: The addon is found

    """
    if isinstance(target, AbstractNode):
        storage_type = get_project_storage_type(target)
        if storage_type == ProjectStorageType.CUSTOM_STORAGE:
            file_size = -1
            dest_size = payload['destination'].get('size', None)
            children = payload['destination'].get('children', None)
            # Move file
            if dest_size is not None:
                file_size = int(dest_size)
            # Move folder
            elif children is not None:
                file_size = get_file_size(payload['destination'])
            logger.debug(f'file size is {file_size}')
            if file_size < 0:
                return

            # Move to bulkmount
            if payload['destination']['provider'] == 'osfstorage':
                node_addon_destination = get_addon_osfstorage_by_path(
                    target,
                    payload['destination']['path'] if payload['destination']['kind'] == 'file' else payload['destination']['root_path'] + '/' + payload['destination']['materialized'],
                    payload['destination']['provider']
                )

                if node_addon_destination is not None:
                    update_institutional_storage_used_quota(
                        target.creator,
                        node_addon_destination.region,
                        file_size
                    )
            # Move to addon
            elif payload['destination']['provider'] in ADDON_METHOD_PROVIDER:
                node_addon_destination = get_addon_osfstorage_by_path(
                    target,
                    payload['destination']['root_path'] + '/' + payload['destination']['materialized'],
                    payload['destination']['provider']
                )

                if node_addon_destination is not None:
                    update_institutional_storage_used_quota(
                        target.creator,
                        node_addon_destination.region,
                        file_size
                    )
