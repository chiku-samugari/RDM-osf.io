from addons.base.utils import get_root_institutional_storage
from framework.auth.decorators import must_be_signed
from osf.models import AbstractNode, ProjectStorageType
from osf.models.user_storage_quota import UserStorageQuota
from website.project.decorators import must_be_contributor_or_public
from website.util import quota
from api.base import settings as api_settings


@must_be_signed
def waterbutler_creator_quota(pid, **kwargs):
    return get_quota_from_pid(pid)

@must_be_contributor_or_public
def get_creator_quota(pid, **kwargs):
    return get_quota_from_pid(pid)

@must_be_contributor_or_public
def get_institution_storage_quota(pid, fid, **kwargs):
    node = AbstractNode.load(pid)
    if node.projectstoragetype.storage_type == ProjectStorageType.CUSTOM_STORAGE:
        file_node_root_id = get_root_institutional_storage(fid)
        if file_node_root_id is not None:
            file_node_root_id = file_node_root_id.id
            provider_settings = node.get_addon('osfstorage', root_id=file_node_root_id)
            try:
                user_storage_quota = node.creator.userstoragequota_set.get(region=provider_settings.region)
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
