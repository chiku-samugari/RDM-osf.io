'use strict';

var $ = require('jquery');
var bootbox = require('bootbox');
var m = require('mithril');
var Treebeard = require('treebeard');
var $osf = require('js/osfHelpers');
var projectSettingsTreebeardBase = require('js/projectSettingsTreebeardBase');

var rdmGettext = require('js/rdmGettext');
var gt = rdmGettext.rdmGettext();
var _ = function(msgid) { return gt.gettext(msgid); };
var agh = require('agh.sprintf');

function expandOnLoad() {
    var tb = this;  // jshint ignore: line
    for (var i = 0; i < tb.treeData.children.length; i++) {
        var parent = tb.treeData.children[i];
        tb.updateFolder(null, parent);
    }
}

function beforeChangePermissions(item, permission){
    var safeTitle = $osf.htmlEscape(item.parent().data.node.title);
    if(permission === 'public'){
        bootbox.dialog({
            title: _('Make publicly editable'),
            message: agh.sprintf(_('Are you sure you want to make the wiki of <b>%1$s\
                 </b> publicly editable? This will allow any logged in user to edit the content of this wiki. '),safeTitle) +
                _('<b>Note</b>: Users without write access will not be able to add, delete, or rename pages.'),
            buttons: {
                cancel : {
                    label: _('Cancel'),
                    className: 'btn-default',
                    callback: function() {item.notify.update('', 'notify-primary', 1, 10);}
                },
                success: {
                    label: _('Apply'),
                    className: 'btn-primary',
                    callback: function() {changePermissions(item, permission);}
                }
            }
        });
    }
    else {
        changePermissions(item, permission);
    }
}

function changePermissions(item, permission) {
    var id = item.parent().data.node.id;

    return $osf.putJSON(
        buildPermissionsURL(item), {'permission': permission}
    ).done(function(){
        item.notify.update(_('Settings updated'), 'notify-success', 1, 2000);
        item.data.select.permission = permission;
    }).fail(function() {
        item.notify.update(_('Could not update settings'), 'notify-danger', 1, 2000);
    });
}

// Helper to build path
function buildPermissionsURL(item) {
    var id = item.parent().data.node.id;
    var permissionsChangePath = '/api/v1/project/'+ id +
        '/wiki/settings/';
    return permissionsChangePath;
}

function ProjectWiki(data) {

    //  Treebeard version
    var tbOptions = $.extend({}, projectSettingsTreebeardBase.defaults, {
        filesData: data,
        divID: 'wgrid',
        ondataload: function () {
            var tb = this;
            expandOnLoad.call(tb);
        },
        resolveRows: function wikiResolveRows(item){
            var columns = [];
            var iconcss = '';
            // check if should not get icon
            if(item.children.length < 1 ){
                iconcss = 'tb-no-icon';
            }
            if (item.data.kind === 'folder' || item.data.kind === 'node') {
                columns.push({
                    data : 'project',  // Data field name
                    folderIcons : true,
                    filter : true,
                    sortInclude : false,
                    custom : function() {
                        if (item.data.node.url !== '') {
                            return m('a', { href : item.data.node.url, target : '_blank' }, item.data.node.title);
                        } else {
                            return m('span', item.data.node.title);
                        }

                    }
                });
            }

            else {
                columns.push(
                {
                    data : 'project',  // Data field name
                    folderIcons : true,
                    filter : true,
                    css : iconcss,
                    sortInclude : false,
                    custom : function() {

                        if(!item.parent().data.permissions.admin){
                            return _('Only admins may change permissions of this wiki.');
                        } else {
                            return item.parent().data.node.is_public ? _('Select who can edit') : agh.sprintf(ngettext('This feature is disabled for wikis of private %1$s','This feature is disabled for wikis of private %1$ss',  item.parent().data.nodeType ),item.parent().data.nodeType);
                        }
                    }
                },
                {
                    data : 'permission',  // Data field name
                    folderIcons : false,
                    filter : false,
                    custom : function() {
                        return  m('div[style="padding-right:10px"]',
                            [m('select.form-control', {
                                onchange: function(ev) {
                                    beforeChangePermissions(item, ev.target.value);
                                },
                                disabled: !item.parent().data.node.is_public || !item.parent().data.permissions.admin
                                },
                                [
                                    m('option', {value: 'private', selected : item.data.select.permission === 'public' ? 'selected': ''}, _('Contributors (with write access)')),
                                    m('option', {value: 'public', selected : item.data.select.permission === 'public' ? 'selected': '' }, _('All GakuNin RDM users'))
                            ])
                        ]);
                    }
                });
            }

            return columns;
        }
    });
    var wgrid = new Treebeard(tbOptions);
}

module.exports = ProjectWiki;
