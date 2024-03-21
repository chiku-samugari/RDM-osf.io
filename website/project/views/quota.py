from framework.auth.decorators import must_be_signed, must_be_logged_in
from osf.models import AbstractNode, ProjectStorageType
from osf.models.user_storage_quota import UserStorageQuota
from website.project.decorators import must_be_contributor_or_public
from website.util import quota
from api.base import settings as api_settings
from flask import request
from rest_framework import status as http_status
from framework.exceptions import HTTPError
from website.util.quota import get_region_id_of_institutional_storage_by_path
import logging

logger = logging.getLogger(__name__)

@must_be_signed
def waterbutler_creator_quota(pid, **kwargs):
    return get_quota_from_pid(pid)

@must_be_contributor_or_public
def get_creator_quota(pid, **kwargs):
    return get_quota_from_pid(pid)

@must_be_signed
def waterbutler_institution_storage_user_quota(pid, payload, **kwargs):
    provider = payload.get('provider', None)
    fid = payload.get('path', None)
    root_path = payload.get('root_path', None)
    return get_institution_user_quota_from_pid(pid, provider, fid, root_path)


@must_be_contributor_or_public
def get_institution_storage_user_quota(pid, **kwargs):
    provider = request.json.get('provider', None)
    fid = request.json.get('path', None)
    root_path = request.json.get('root_path', None)
    return get_institution_user_quota_from_pid(pid, provider, fid, root_path)


def get_quota_from_pid(pid):
    """Auxiliary function for getting the quota from a project ID.
    Used on requests by waterbutler and the user (from browser)."""
    node = AbstractNode.load(pid)
    max_quota, used_quota = quota.get_quota_info(
        node.creator, quota.get_project_storage_type(node)
    )
    return {
        'max': max_quota * api_settings.SIZE_UNIT_GB,
        'used': used_quota
    }


def get_institution_user_quota_from_pid(pid, provider, fid, root_path=None):
    node = AbstractNode.load(pid)
    if provider is None or fid is None:
        raise HTTPError(http_status.HTTP_400_BAD_REQUEST)
    try:
        project_storage_type = node.projectstoragetype.storage_type
    except ProjectStorageType.DoesNotExist:
        forked_project = AbstractNode.objects.filter(id=node.forked_from.id).first()
        if forked_project:
            project_storage_type = forked_project.projectstoragetype.storage_type
        else:
            project_storage_type = ProjectStorageType.CUSTOM_STORAGE

    region_id = get_region_id_of_institutional_storage_by_path(node, provider, fid, project_storage_type, root_path=root_path)
    if region_id is not None:
        try:
            user_storage_quota = node.creator.userstoragequota_set.get(
                region_id=region_id
            )
            logger.debug(f'quota used is {user_storage_quota.used}')
            return {
                'max': user_storage_quota.max_quota * api_settings.SIZE_UNIT_GB,
                'used': user_storage_quota.used
            }
        except UserStorageQuota.DoesNotExist:
            pass

    return {
        'max': api_settings.DEFAULT_MAX_QUOTA * api_settings.SIZE_UNIT_GB,
        'used': 0
    }
