import os

from addons.base.apps import BaseAddonAppConfig
from website.util import rubeus
from addons.nextcloudinstitutions.settings import MAX_UPLOAD_SIZE

FULL_NAME = 'Nextcloud for Institutions'
SHORT_NAME = 'nextcloudinstitutions'
LONG_NAME = 'addons.{}'.format(SHORT_NAME)

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(
    HERE,
    'templates'
)


def nextcloudinstitutions_root(addon_config, node_settings, auth, **kwargs):
    from addons.osfstorage.models import Region

    node = node_settings.owner
    institution = node_settings.addon_option.institution
    if Region.objects.filter(_id=institution._id).exists():
        region = Region.objects.filter(
            _id=institution._id,
            waterbutler_settings__storage__provider=SHORT_NAME,
            id=node_settings.region.id
        ).first()
        if region:
            node_settings.region = region
    root = rubeus.build_addon_root(
        node_settings=node_settings,
        name='',
        permissions=auth,
        user=auth.user,
        nodeUrl=node.url,
        nodeApiUrl=node.api_url,
    )
    return [root]


class NextcloudInstitutionsAddonAppConfig(BaseAddonAppConfig):
    name = 'addons.{}'.format(SHORT_NAME)
    label = 'addons_{}'.format(SHORT_NAME)
    full_name = FULL_NAME
    short_name = SHORT_NAME
    owners = ['user', 'node']
    configs = ['accounts', 'node']
    categories = ['storage']
    has_hgrid_files = True
    max_file_size = MAX_UPLOAD_SIZE

    user_settings_template = os.path.join(
        TEMPLATE_PATH, 'nextcloudinstitutions_user_settings.mako')
    # node_settings_template is not used.

    get_hgrid_data = nextcloudinstitutions_root

    actions = ()

    # default value for RdmAddonOption.is_allowed for GRDM Admin
    is_allowed_default = False
    for_institutions = True

    @property
    def routes(self):
        from .routes import api_routes
        return [api_routes]

    @property
    def node_settings(self):
        return self.get_model('NodeSettings')
