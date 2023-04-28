import mock
import pytest
import unittest

from rest_framework import status as http_status
from nose.tools import (assert_equal, assert_true, assert_false)
from django.utils import timezone

from addons.datasteward.tests.utils import DataStewardAddonTestCase
from addons.datasteward.views import disable_datasteward_addon, enable_datasteward_addon
from framework.auth.core import Auth
from osf.exceptions import UserStateError, ValidationValueError
from osf.models.contributor import Contributor
from osf.utils import permissions

from osf_tests.factories import AuthUserFactory, ContributorFactory, InstitutionFactory, ProjectFactory
from tests.base import OsfTestCase
from website.util import api_url_for

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

    def test_enable_datasteward_addon_update_not_admin_permission_contributor_to_admin_permission_success(self):
        user = AuthUserFactory(fullname='enabledatasteward@osf', username='enabledatasteward@osf.com')
        institution = InstitutionFactory()
        node = ProjectFactory(creator=self.new_user, type=OSF_NODE, is_deleted=False)
        institution.nodes.add(node)
        institution.save()
        user.affiliated_institutions.add(institution)
        user.save()

        kwargs = node.contributor_kwargs
        kwargs['_order'] = 0
        new_contributor = ContributorFactory(**kwargs)
        new_contributor.user = user
        new_contributor.is_data_steward = False
        new_contributor.visible = True
        new_contributor.save()

        result = enable_datasteward_addon(Auth(user))

        updated_contributor = Contributor.objects.filter(node=node, user=user)
        assert_true(updated_contributor.exists() and updated_contributor.first().permission == permissions.ADMIN)
        assert_true(result)

    def test_enable_datasteward_addon_add_contributor_success(self):
        user = AuthUserFactory(fullname='enabledatasteward@osf', username='enabledatasteward@osf.com')
        institution = InstitutionFactory()
        node = ProjectFactory(creator=self.new_user, type=OSF_NODE, is_deleted=False)
        institution.nodes.add(node)
        institution.save()
        user.affiliated_institutions.add(institution)
        user.save()

        result = enable_datasteward_addon(Auth(user))

        updated_contributor = Contributor.objects.filter(node=node, user=user)
        assert_true(updated_contributor.exists() and updated_contributor.first().permission == permissions.ADMIN)
        assert_true(result)

    def test_enable_datasteward_addon_add_contributor_user_is_disabled(self):
        user = AuthUserFactory(fullname='enabledatasteward@osf', username='enabledatasteward@osf.com')
        institution = InstitutionFactory()
        node = ProjectFactory(creator=self.new_user, type=OSF_NODE, is_deleted=False)
        institution.nodes.add(node)
        institution.save()
        user.affiliated_institutions.add(institution)
        user.date_disabled = timezone.now()
        user.save()

        with self.assertRaises(ValidationValueError):
            enable_datasteward_addon(Auth(user))

    def test_enable_datasteward_addon_add_contributor_user_is_not_registered(self):
        user = AuthUserFactory(fullname='enabledatasteward@osf', username='enabledatasteward@osf.com')
        institution = InstitutionFactory()
        node = ProjectFactory(creator=self.new_user, type=OSF_NODE, is_deleted=False)
        institution.nodes.add(node)
        institution.save()
        user.affiliated_institutions.add(institution)
        user.is_registered = False
        user.save()

        with self.assertRaises(UserStateError):
            enable_datasteward_addon(Auth(user))

    def test_disable_datasteward_addon_affiliated_institutions_is_empty(self):
        result = disable_datasteward_addon(self.auth)

        assert_false(result)

    def test_disable_datasteward_addon_skip_project_has_only_one_admin(self):
        institution = InstitutionFactory()
        node = ProjectFactory(creator=self.new_user, type=OSF_NODE, is_deleted=False)
        institution.nodes.add(node)
        institution.save()
        self.new_user.affiliated_institutions.add(institution)
        self.new_user.save()

        contributor = Contributor.objects.filter(user=self.new_user, node=node).first()
        contributor.is_data_steward = True
        contributor.data_steward_old_permission = permissions.READ
        contributor.save()
        result = disable_datasteward_addon(self.auth)

        assert_true(len(result) == 1)


    def test_disable_datasteward_addon_update_permission_success(self):
        user = AuthUserFactory(fullname='disabledatasteward@osf', username='disabledatasteward@osf.com')
        institution = InstitutionFactory()
        node = ProjectFactory(creator=self.new_user, type=OSF_NODE, is_deleted=False)
        institution.nodes.add(node)
        institution.save()
        self.new_user.affiliated_institutions.add(institution)
        self.new_user.save()
        user.affiliated_institutions.add(institution)
        user.save()

        contributor = Contributor.objects.filter(user=self.new_user, node=node).first()
        contributor.is_data_steward = False
        contributor.save()

        kwargs = node.contributor_kwargs
        kwargs['_order'] = 0
        new_contributor = ContributorFactory(**kwargs)
        new_contributor.user = user
        new_contributor.is_data_steward = True
        new_contributor.visible = True
        new_contributor.data_steward_old_permission = permissions.READ
        new_contributor.save()

        node.add_permission(user, permissions.ADMIN, save=False)

        result = disable_datasteward_addon(Auth(user))

        assert_false(result)


    def test_disable_datasteward_addon_contributor_is_data_steward_is_False_skip_project(self):
        institution = InstitutionFactory()
        node = ProjectFactory(creator=self.new_user, type=OSF_NODE, is_deleted=False)
        institution.nodes.add(node)
        institution.save()
        self.new_user.affiliated_institutions.add(institution)
        self.new_user.save()

        contributor = Contributor.objects.filter(user=self.new_user, node=node).first()
        contributor.is_data_steward = False
        contributor.save()

        result = disable_datasteward_addon(self.auth)

        assert_false(result)


    def test_disable_datasteward_addon_remove_contributor_skip_project(self):
        user = AuthUserFactory(fullname='disabledatasteward@osf', username='disabledatasteward@osf.com')
        institution = InstitutionFactory()
        node = ProjectFactory(creator=self.new_user, type=OSF_NODE, is_deleted=False)
        institution.nodes.add(node)
        institution.save()
        self.new_user.affiliated_institutions.add(institution)
        self.new_user.save()
        user.affiliated_institutions.add(institution)
        user.save()

        contributor = Contributor.objects.filter(user=self.new_user, node=node).first()
        contributor.visible = False
        contributor.save()

        kwargs = node.contributor_kwargs
        kwargs['_order'] = 0
        new_contributor = ContributorFactory(**kwargs)
        new_contributor.user = user
        new_contributor.is_data_steward = True
        new_contributor.visible = True
        new_contributor.save()

        node.add_permission(user, permissions.ADMIN, save=False)

        result = disable_datasteward_addon(Auth(user))

        assert_true(len(result) == 1)


    def test_disable_datasteward_addon_remove_contributor_success(self):
        user = AuthUserFactory(fullname='disabledatasteward@osf', username='disabledatasteward@osf.com')
        institution = InstitutionFactory()
        node = ProjectFactory(creator=self.new_user, type=OSF_NODE, is_deleted=False)
        institution.nodes.add(node)
        institution.save()
        self.new_user.affiliated_institutions.add(institution)
        self.new_user.save()
        user.affiliated_institutions.add(institution)
        user.unclaimed_records = {}
        user.unclaimed_records[node._id] = {'name': node.title}
        user.save()

        contributor = Contributor.objects.filter(user=self.new_user, node=node).first()
        contributor.visible = True
        contributor.save()

        kwargs = node.contributor_kwargs
        kwargs['_order'] = 0
        new_contributor = ContributorFactory(**kwargs)
        new_contributor.user = user
        new_contributor.is_data_steward = True
        new_contributor.visible = True
        new_contributor.save()

        node.add_permission(user, permissions.ADMIN, save=False)

        result = disable_datasteward_addon(Auth(user))

        assert_false(result)


    def test_disable_datasteward_addon_skip_project_not_have_user_as_contributor(self):
        user = AuthUserFactory(fullname='disabledatasteward@osf', username='disabledatasteward@osf.com')
        institution = InstitutionFactory()
        node = ProjectFactory(creator=self.new_user, type=OSF_NODE, is_deleted=False)
        institution.nodes.add(node)
        institution.save()
        self.new_user.affiliated_institutions.add(institution)
        self.new_user.save()
        user.affiliated_institutions.add(institution)
        user.save()

        result = disable_datasteward_addon(Auth(user))

        assert_false(result)