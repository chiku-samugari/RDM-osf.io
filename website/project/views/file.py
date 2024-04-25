"""
Files views.
"""
from flask import request

from osf import features

from website.util import rubeus
from website.project.decorators import must_be_contributor_or_public, must_not_be_retracted_registration
from website.project.views.node import _view_project
from website.ember_osf_web.decorators import ember_flag_is_active
from addons.osfstorage.models import NodeSettings

@must_not_be_retracted_registration
@must_be_contributor_or_public
@ember_flag_is_active(features.EMBER_PROJECT_FILES)
def collect_file_trees(auth, node, **kwargs):
    """Collect file trees for all add-ons implementing HGrid views, then
    format data as appropriate.
    """
    serialized = _view_project(node, auth, primary=True)
    # Add addon static assets
    serialized.update(rubeus.collect_addon_assets(node))

    return serialized

@must_be_contributor_or_public
def open_directory_link(auth, node, provider, **kwargs):
    path = '/'
    if kwargs.get('path'):
        path = path + kwargs['path']

    serialized = _view_project(node, auth, primary=True)
    # Add addon static assets
    serialized.update(rubeus.collect_addon_assets(node))

    serialized.update({
        'directory': {
            'provider': provider,
            'path': path,
            'materializedPath': path,
        }
    })

    return serialized


@must_be_contributor_or_public
def grid_data(auth, node, **kwargs):
    """View that returns the formatted data for rubeus.js/hgrid
    """
    data = request.args.to_dict()
    ret = rubeus.to_hgrid(node, auth, **data)
    if NodeSettings.objects.filter(owner_id=node.id).exists() and ret[0]['children']:
        for _, child in enumerate(ret[0]['children']):
            if child.get('provider') == 'osfstorage' and 'nodeRegion' in child:
                update_custom_storage_icon_url(child)
            elif 'nodeType' in child and child.get('nodeType') == 'component':
                # update icon url for components
                for component in child.get('children'):
                    if component.get('provider') == 'osfstorage' and 'nodeRegion' in component:
                        update_custom_storage_icon_url(component)
    return {'data': ret}


def update_custom_storage_icon_url(storage):
    if storage.get('provider') == 'osfstorage' and 'nodeRegion' in storage:
        if storage['nodeRegion'] in ['NII Storage', 'United States']:
            storage['nodeRegion'] = 'NII Storage'
        else:
            storage['iconUrl'] = '/static/addons/osfstorage/comicon_custom_storage.png'
            storage['name'] = storage['nodeRegion']
            storage['addonFullname'] = storage['nodeRegion']
