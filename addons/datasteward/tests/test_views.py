import mock
import pytest
import unittest

from rest_framework import status as http_status
from nose.tools import (assert_equal, assert_true, assert_false)

from addons.datasteward.tests.utils import DataStewardAddonTestCase
from addons.datasteward.views import disable_datasteward_addon, enable_datasteward_addon, revert_project_permission, set_project_permission_to_admin
from framework.auth.core import Auth
from osf.utils import permissions

from osf_tests.factories import AuthUserFactory, InstitutionFactory, OSFGroupFactory, ProjectFactory
from tests.base import OsfTestCase
from website.util import api_url_for
from unittest import mock

OSF_NODE = 'osf.node'

@pytest.mark.django_db
class TestDataStewardViews(DataStewardAddonTestCase, OsfTestCase, unittest.TestCase):
    def setUp(self):
        super(TestDataStewardViews, self).setUp()
        self.new_user = AuthUserFactory(fullname='datasteward@osf', username='datasteward@osf.com')
        self.new_user.save()
        self.project = ProjectFactory(creator=self.new_user)
        self.project.save()
        self.auth = Auth(self.new_user)

    def set_datasteward_addon(self):
        self.new_user.is_data_steward = True
        self.new_user.save()

        self.settings = self.new_user.get_or_add_addon(self.ADDON_SHORT_NAME)
        if not self.settings.enabled:
            self.settings.enabled = True
            self.settings.save()
            self.new_user.save()

    def test_datasteward_user_config_get_forbidden(self):
        url = api_url_for('datasteward_user_config_get')
        self.new_user.is_data_steward = False
        self.new_user.save()

        res = self.app.get(url, auth=self.new_user.auth, expect_errors=True)

        assert_equal(res.status_code, http_status.HTTP_403_FORBIDDEN)
        assert_equal(res.json, {})

    def test_datasteward_user_config_get_false_by_addon_settings_not_found(self):
        url = api_url_for('datasteward_user_config_get')
        self.new_user.is_data_steward = True
        self.new_user.save()

        res = self.app.get(url, auth=self.new_user.auth)

        assert_equal(res.status_code, http_status.HTTP_200_OK)
        assert_false(res.json.get('enabled'))

    def test_datasteward_user_config_get_true(self):
        url = api_url_for('datasteward_user_config_get')
        self.set_datasteward_addon()

        res = self.app.get(url, auth=self.new_user.auth)

        assert_equal(res.status_code, http_status.HTTP_200_OK)
        assert_true(res.json.get('enabled'))

    def test_datasteward_user_config_post_bad_request(self):
        url = api_url_for('datasteward_user_config_post')
        res = self.app.post_json(url, {}, auth=self.new_user.auth, expect_errors=True)
        assert_equal(res.status_code, http_status.HTTP_400_BAD_REQUEST)

    def test_datasteward_user_config_post_forbidden(self):
        url = api_url_for('datasteward_user_config_post')
        self.new_user.is_data_steward = False
        self.new_user.save()

        res = self.app.post_json(url, {'enabled': True}, auth=self.new_user.auth, expect_errors=True)
        assert_equal(res.status_code, http_status.HTTP_403_FORBIDDEN)

    @mock.patch('addons.datasteward.views.disable_datasteward_addon')
    def test_datasteward_user_config_post_enabled_is_false_and_skipped_projects_is_none(self, mock_disable_addon):
        self.set_datasteward_addon()
        url = api_url_for('datasteward_user_config_post')
        mock_disable_addon.return_value = None

        res = self.app.post_json(url, {'enabled': False}, auth=self.new_user.auth, expect_errors=True)
        assert_equal(res.status_code, http_status.HTTP_500_INTERNAL_SERVER_ERROR)

    @mock.patch('addons.datasteward.views.disable_datasteward_addon')
    def test_datasteward_user_config_post_enabled_is_false_and_skipped_projects_is_not_none(self, mock_disable_addon):
        self.set_datasteward_addon()
        url = api_url_for('datasteward_user_config_post')
        project = ProjectFactory.build()
        mock_disable_addon.return_value = [project]

        res = self.app.post_json(url, {'enabled': False}, auth=self.new_user.auth, status=http_status.HTTP_200_OK)

        assert_equal(res.status_code, http_status.HTTP_200_OK)
        assert_equal(res.json.get('skipped_projects')[0].get('name'), project.title)

    @mock.patch('addons.datasteward.views.enable_datasteward_addon')
    def test_datasteward_user_config_post_enabled_is_true_and_enable_addon_result_is_false(self, mock_enable_addon):
        self.set_datasteward_addon()
        url = api_url_for('datasteward_user_config_post')
        mock_enable_addon.return_value = False

        res = self.app.post_json(url, {'enabled': True}, auth=self.new_user.auth, status=http_status.HTTP_500_INTERNAL_SERVER_ERROR)
        assert_equal(res.status_code, http_status.HTTP_500_INTERNAL_SERVER_ERROR)

    @mock.patch('addons.datasteward.views.enable_datasteward_addon')
    def test_datasteward_user_config_post_enabled_is_true_and_enable_addon_result_is_true(self, mock_enable_addon):
        self.set_datasteward_addon()
        url = api_url_for('datasteward_user_config_post')
        mock_enable_addon.return_value = True

        res = self.app.post_json(url, {'enabled': True}, auth=self.new_user.auth)
        assert_equal(res.status_code, http_status.HTTP_200_OK)

    def test_enable_datasteward_addon_no_affiliated_institutions(self):
        result = enable_datasteward_addon(self.auth)

        assert_false(result)

    def test_enable_datasteward_addon_success(self):
        institution = InstitutionFactory()

        node = ProjectFactory(creator=self.new_user, type=OSF_NODE, is_deleted=False)

        institution.nodes.add(node)
        institution.save()
        self.new_user.affiliated_institutions.add(institution)
        self.new_user.save()
        result = enable_datasteward_addon(self.auth)

        assert_true(result)

    def test_set_project_permission_to_admin_error(self):
        mock_project = mock.Mock()
        mock_project.is_contributor.side_effect = Exception('mock test error')

        set_project_permission_to_admin(mock_project, self.auth, True)

    async def test_set_project_permission_to_admin_raise_exception(self):
        mock_project = mock.Mock()
        mock_project.is_contributor.side_effect = Exception('mock test error')
        with pytest.raises(Exception):
            await set_project_permission_to_admin(mock_project, self.auth, False)

    async def test_set_project_permission_to_admin_add_new_contributor(self):
        user = AuthUserFactory(username='new_admin@osf.com', fullname='new_admin')
        await set_project_permission_to_admin(self.project, Auth(user), False)

        contributor = self.project.contributor_class.objects.get(user=user, node=self.project)
        assert_equal(permissions.ADMIN, contributor.permission)

    async def test_set_project_permission_to_admin_update_contributor_permission_is_not_admin(self):
        group_mem = AuthUserFactory(username='test@osf.com', fullname='group_mem')
        group_mem.is_data_steward = False
        group_mem.save()
        group = OSFGroupFactory(creator=group_mem)
        self.project.add_osf_group(group, permissions.READ)

        self.project.add_contributor(contributor=group_mem, permissions=permissions.READ, log=False, save=False)
        self.project.save()

        await set_project_permission_to_admin(self.project, Auth(group_mem), False)

        contributor = self.project.contributor_class.objects.get(user=group_mem, node=self.project)
        assert_equal(permissions.ADMIN, contributor.permission)

    def test_disable_datasteward_addon_affiliated_institutions_is_empty(self):
        result = disable_datasteward_addon(self.auth)

        assert_false(result)

    def test_disable_datasteward_addon_affiliated_institutions(self):
        institution = InstitutionFactory()

        node = ProjectFactory(creator=self.new_user, type=OSF_NODE, is_deleted=False)

        institution.nodes.add(node)
        institution.save()
        self.new_user.affiliated_institutions.add(institution)
        self.new_user.save()
        result = disable_datasteward_addon(self.auth)

        assert_equal(result, [])

    async def test_revert_project_permission_error(self):
        skipped_projects = []
        self.project.add_contributor(contributor=self.new_user, permissions=permissions.ADMIN, log=False, save=False)
        self.project.save()
        with mock.patch('osf.models.mixins.ContributorMixin.is_contributor', side_effect=Exception('mock test error')):
            await revert_project_permission(self.project, self.auth, skipped_projects)
            assert_equal(skipped_projects, [self.project])

    def test_revert_project_permission_is_not_contributor(self):
        user_auth = Auth(AuthUserFactory())
        skipped_projects = []
        revert_project_permission(self.project, user_auth, skipped_projects)

        assert_equal(skipped_projects, [])

    def test_revert_project_permission_contributor_is_data_steward_is_false(self):
        group_mem = AuthUserFactory(username='test@osf.com', fullname='group_mem')
        group_mem.is_data_steward = False
        group_mem.save()
        group = OSFGroupFactory(creator=group_mem)
        self.project.add_osf_group(group, permissions.READ)

        self.project.add_contributor(contributor=group_mem, permissions=permissions.READ, log=False, save=False)
        self.project.save()

        skipped_projects = []
        revert_project_permission(self.project, Auth(group_mem), skipped_projects)

        assert_equal(skipped_projects, [])

    async def test_revert_project_permission_update_contributor(self):
        self.project.add_contributor(contributor=self.new_user, permissions=permissions.ADMIN, log=False, save=False)
        self.project.save()

        contributor = self.project.contributor_class.objects.get(user=self.new_user, node=self.project)
        contributor.data_steward_old_permission = contributor.permission
        contributor.is_data_steward = True
        contributor.save()

        skipped_projects = []
        await revert_project_permission(self.project, self.auth, skipped_projects)

        contributor = self.project.contributor_class.objects.get(user=self.new_user, node=self.project)
        assert_equal(skipped_projects, [])
        assert_false(contributor.is_data_steward)
        assert_false(contributor.data_steward_old_permission)

    def test_revert_project_permission_remove_contributor(self):
        group_mem = AuthUserFactory(username='test@osf.com', fullname='group_mem')
        group_mem.is_data_steward = False
        group_mem.save()
        group = OSFGroupFactory(creator=group_mem)
        self.project.add_osf_group(group, permissions.READ)

        self.project.add_contributor(contributor=group_mem, permissions=permissions.READ, log=False, save=False)
        self.project.save()

        skipped_projects = []
        revert_project_permission(self.project, Auth(group_mem), skipped_projects)

        assert_equal(skipped_projects, [])

    async def test_revert_project_permission_remove_contributor_error(self):
        self.project.add_contributor(contributor=self.new_user, permissions=permissions.ADMIN, log=False, save=False)
        self.project.save()

        contributor = self.project.contributor_class.objects.get(user=self.new_user, node=self.project)
        contributor.data_steward_old_permission = None
        contributor.is_data_steward = True
        contributor.save()

        skipped_projects = []
        await revert_project_permission(self.project, self.auth, skipped_projects)

        assert_equal(skipped_projects, [self.project])
