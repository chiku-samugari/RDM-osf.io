from framework.auth.decorators import must_be_signed
from osf.models import AbstractNode
from osf.models.user_quota import UserQuota
from website.project.decorators import must_be_contributor_or_public
from website.util import quota
from api.base import settings as api_settings
from flask import request
from rest_framework import status as http_status
from framework.exceptions import HTTPError
from website.util.quota import get_region_id_of_institutional_storage_by_path


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
    return get_institution_user_quota_from_pid(pid, provider, fid)


@must_be_contributor_or_public
def get_institution_storage_user_quota(pid, **kwargs):
    provider = request.json.get('provider', None)
    fid = request.json.get('path', None)
    return get_institution_user_quota_from_pid(pid, provider, fid)


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


def get_institution_user_quota_from_pid(pid, provider, fid):
    node = AbstractNode.load(pid)
    if provider is None or fid is None:
        raise HTTPError(http_status.HTTP_400_BAD_REQUEST)

    region_id = get_region_id_of_institutional_storage_by_path(node, provider, fid, node.projectstoragetype.storage_type)
    if region_id is not None:
        try:
            user_storage_quota = node.creator.userquota_set.get(
                storage_type=node.projectstoragetype.storage_type,
                region_id=region_id
            )
            return {
                'max': user_storage_quota.max_quota * api_settings.SIZE_UNIT_GB,
                'used': user_storage_quota.used
            }
        except UserQuota.DoesNotExist:
            pass

    return {
        'max': api_settings.DEFAULT_MAX_QUOTA * api_settings.SIZE_UNIT_GB,
        'used': 0
    }
