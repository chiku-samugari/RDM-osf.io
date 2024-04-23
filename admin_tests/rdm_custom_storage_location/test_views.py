from django.test import RequestFactory
from django.http import Http404, HttpResponse
import json
import mock
from nose import tools as nt

from admin_tests.utilities import setup_user_view
from admin.rdm_custom_storage_location import views
from addons.osfstorage.models import Region
from api.base import settings as api_settings
from framework.exceptions import HTTPError
from osf.models import AuthenticationAttribute
from tests.base import AdminTestCase
from osf_tests.factories import (
    AuthUserFactory,
    RegionFactory,
    InstitutionFactory,
    AuthenticationAttributeFactory,
)
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied


class TestInstitutionDefaultStorage(AdminTestCase):
    def setUp(self):
        super(TestInstitutionDefaultStorage, self).setUp()
        self.institution1 = InstitutionFactory()
        self.institution2 = InstitutionFactory()
        self.user = AuthUserFactory()
        self.default_region = Region.objects.first()

        self.user = AuthUserFactory()
        self.user.affiliated_institutions.add(self.institution1)
        self.user.is_active = True
        self.user.is_registered = True
        self.user.is_superuser = False
        self.user.is_staff = True
        self.user.save()
        self.request = RequestFactory().get('/fake_path')
        self.view = views.InstitutionalStorageView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        self.addon_type_dict = [
            'BoxAddonAppConfig',
            'OSFStorageAddonAppConfig',
            'OwnCloudAddonAppConfig',
            'S3AddonAppConfig',
            'GoogleDriveAddonConfig',
            'SwiftAddonAppConfig',
            'S3CompatAddonAppConfig',
            'NextcloudAddonAppConfig',
            'DropboxBusinessAddonAppConfig',
            'NextcloudInstitutionsAddonAppConfig',
            'S3CompatInstitutionsAddonAppConfig',
            'OCIInstitutionsAddonAppConfig',
            'OneDriveBusinessAddonAppConfig',
        ]

    def test_admin_login(self):
        self.request.user.is_active = True
        self.request.user.is_registered = True
        self.request.user.is_superuser = False
        self.request.user.is_staff = True
        nt.assert_true(self.view.test_func())

    def test_get(self, *args, **kwargs):
        res = self.view.get(self.request, *args, **kwargs)
        nt.assert_equal(res.status_code, 200)

    def test_get_without_custom_storage(self, *args, **kwargs):
        res = self.view.get(self.request, *args, **kwargs)
        for addon in res.context_data['providers']:
            nt.assert_true(type(addon).__name__ in self.addon_type_dict)
        region = Region.objects.filter(_id=self.institution1._id, is_allowed=True, is_readonly=False).first()
        nt.assert_equal(res.context_data['region'][0], region)
        nt.assert_equal(res.context_data['selected_provider_short_name'], 'osfstorage')

    def test_get_custom_storage(self, *args, **kwargs):
        self.us = RegionFactory()
        self.us._id = self.institution1._id
        self.us.save()
        res = self.view.get(self.request, *args, **kwargs)
        for addon in res.context_data['providers']:
            nt.assert_true(type(addon).__name__ in self.addon_type_dict)
        nt.assert_equal(res.context_data['region'][0], self.us)
        nt.assert_equal(res.context_data['selected_provider_short_name'],
                        res.context_data['region'][0].waterbutler_settings['storage']['provider'])


class TestIconView(AdminTestCase):
    def setUp(self):
        super(TestIconView, self).setUp()
        self.user = AuthUserFactory()
        self.institution = InstitutionFactory()
        self.user.affiliated_institutions.add(self.institution)
        self.request = RequestFactory().get('/fake_path')
        self.request.user = self.user
        self.request.user.is_active = True
        self.request.user.is_registered = True
        self.request.user.is_superuser = False
        self.request.user.is_staff = True
        self.view = views.IconView()
        self.view = setup_user_view(self.view, self.request, user=self.user)

    def tearDown(self):
        super(TestIconView, self).tearDown()
        self.user.delete()

    def test_login_user(self):
        nt.assert_true(self.view.test_func())

    def test_valid_get(self, *args, **kwargs):
        self.view.kwargs = {'addon_name': 's3'}
        res = self.view.get(self.request, *args, **self.view.kwargs)
        nt.assert_equal(res.status_code, 200)

    def test_invalid_get(self, *args, **kwargs):
        self.view.kwargs = {'addon_name': 'invalidprovider'}
        with nt.assert_raises(Http404):
            self.view.get(self.request, *args, **self.view.kwargs)


class TestPermissionTestConnection(AdminTestCase):

    def setUp(self):
        self.user = AuthUserFactory()

    def view_post(self, params):
        request = RequestFactory().post(
            'fake_path',
            json.dumps(params),
            content_type='application/json'
        )
        request.is_ajax()
        request.user = self.user
        return views.TestConnectionView.as_view()(request)

    def test_normal_user(self):
        with nt.assert_raises(PermissionDenied):
            self.view_post({})

    def test_staff_without_institution(self):
        self.user.is_staff = True
        self.user.save()

        with nt.assert_raises(PermissionDenied):
            self.view_post({})

    def test_staff_with_institution(self):
        institution = InstitutionFactory()

        self.user.is_staff = True
        self.user.affiliated_institutions.add(institution)
        self.user.save()

        response = self.view_post({})
        nt.assert_is_instance(response, HttpResponse)

    def test_superuser(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()

        with nt.assert_raises(PermissionDenied):
            self.view_post({})

class TestPermissionSaveCredentials(AdminTestCase):

    def setUp(self):
        self.user = AuthUserFactory()

    def view_post(self, params):
        request = RequestFactory().post(
            'fake_path',
            json.dumps(params),
            content_type='application/json'
        )
        request.is_ajax()
        request.user = self.user
        return views.SaveCredentialsView.as_view()(request)

    def test_normal_user(self):
        with nt.assert_raises(PermissionDenied):
            self.view_post({})

    def test_staff_without_institution(self):
        self.user.is_staff = True
        self.user.save()

        with nt.assert_raises(PermissionDenied):
            self.view_post({})

    def test_staff_with_institution(self):
        institution = InstitutionFactory()

        self.user.is_staff = True
        self.user.affiliated_institutions.add(institution)
        self.user.save()

        response = self.view_post({})
        nt.assert_is_instance(response, HttpResponse)

    def test_superuser(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()

        with nt.assert_raises(PermissionDenied):
            self.view_post({})

    def test_post_with_provider_short_name_s3(self):
        institution = InstitutionFactory()

        self.user.is_staff = True
        self.user.affiliated_institutions.add(institution)
        self.user.save()
        self.request = RequestFactory().post(
            'custom_storage_location:save_credentials',
            json.dumps({
                'provider_short_name': 's3', 'storage_name': 'test_storage_name',
                'new_storage_name': 'test_new_storage_name'
            }),
            content_type='application/json'
        )
        self.request.is_ajax()
        self.view = views.SaveCredentialsView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)

        nt.assert_equal(response.status_code, 400)

    def test_post_with_provider_short_name_s3compat(self):
        institution = InstitutionFactory()

        self.user.is_staff = True
        self.user.affiliated_institutions.add(institution)
        self.user.save()
        self.request = RequestFactory().post(
            'custom_storage_location:save_credentials',
            json.dumps({
                'provider_short_name': 's3compat', 'storage_name': 'test_storage_name',
                'new_storage_name': 'test_new_storage_name',
                's3compat_endpoint_url': 'https://fake_end_point',
                's3compat_server_side_encryption': 'False',
            }),
            content_type='application/json'
        )
        self.request.is_ajax()
        self.view = views.SaveCredentialsView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)

        nt.assert_equal(response.status_code, 400)

    def test_post_with_provider_short_name_s3compatb3(self):
        institution = InstitutionFactory()

        self.user.is_staff = True
        self.user.affiliated_institutions.add(institution)
        self.user.save()
        self.request = RequestFactory().post(
            'custom_storage_location:save_credentials',
            json.dumps({
                'provider_short_name': 's3compatb3', 'storage_name': 'test_storage_name',
                'new_storage_name': 'test_new_storage_name',
                's3compatb3_endpoint_url': 'https://fake_end_point',
            }),
            content_type='application/json'
        )
        self.request.is_ajax()
        self.view = views.SaveCredentialsView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)

        nt.assert_equal(response.status_code, 400)

    def test_post_with_provider_short_name_s3compatinstitutions(self):
        institution = InstitutionFactory()

        self.user.is_staff = True
        self.user.affiliated_institutions.add(institution)
        self.user.save()
        self.request = RequestFactory().post(
            'custom_storage_location:save_credentials',
            json.dumps({
                'provider_short_name': 's3compatinstitutions', 'storage_name': 'test_storage_name',
                'new_storage_name': 'test_new_storage_name',
                's3compatinstitutions_endpoint_url': 'https://fake_end_point',
            }),
            content_type='application/json'
        )
        self.request.is_ajax()
        self.view = views.SaveCredentialsView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)

        nt.assert_equal(response.status_code, 400)

    def test_post_with_provider_short_name_ociinstitutions(self):
        institution = InstitutionFactory()

        self.user.is_staff = True
        self.user.affiliated_institutions.add(institution)
        self.user.save()
        self.request = RequestFactory().post(
            'custom_storage_location:save_credentials',
            json.dumps({
                'provider_short_name': 'ociinstitutions', 'storage_name': 'test_storage_name',
                'ociinstitutions_endpoint_url': 'https://fake_end_point'
            }),
            content_type='application/json'
        )
        self.request.is_ajax()
        self.view = views.SaveCredentialsView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)

        nt.assert_equal(response.status_code, 400)

    def test_post_with_provider_short_name_swift(self):
        institution = InstitutionFactory()

        self.user.is_staff = True
        self.user.affiliated_institutions.add(institution)
        self.user.save()
        self.request = RequestFactory().post(
            'custom_storage_location:save_credentials',
            json.dumps({
                'provider_short_name': 'swift', 'storage_name': 'test_storage_name',
                'new_storage_name': 'test_new_storage_name'
            }),
            content_type='application/json'
        )
        self.request.is_ajax()
        self.view = views.SaveCredentialsView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)

        nt.assert_equal(response.status_code, 400)

    def test_post_with_provider_short_name_osfstorage(self):
        institution = InstitutionFactory()

        self.user.is_staff = True
        self.user.affiliated_institutions.add(institution)
        self.user.save()
        self.request = RequestFactory().post(
            'custom_storage_location:save_credentials',
            json.dumps({
                'provider_short_name': 'osfstorage', 'storage_name': 'test_storage_name',
                'new_storage_name': 'test_new_storage_name'
            }),
            content_type='application/json'
        )
        self.request.is_ajax()
        self.view = views.SaveCredentialsView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)

        nt.assert_equal(response.status_code, 200)

    def test_post_with_provider_short_name_googledrive(self):
        institution = InstitutionFactory()

        self.user.is_staff = True
        self.user.affiliated_institutions.add(institution)
        self.user.save()
        self.request = RequestFactory().post(
            'custom_storage_location:save_credentials',
            json.dumps({
                'provider_short_name': 'googledrive', 'storage_name': 'test_storage_name',
                'new_storage_name': 'test_new_storage_name'
            }),
            content_type='application/json'
        )
        self.request.is_ajax()
        self.view = views.SaveCredentialsView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)

        nt.assert_equal(response.status_code, 400)

    def test_post_with_provider_short_name_owncloud(self):
        institution = InstitutionFactory()

        self.user.is_staff = True
        self.user.affiliated_institutions.add(institution)
        self.user.save()
        self.request = RequestFactory().post(
            'custom_storage_location:save_credentials',
            json.dumps({
                'provider_short_name': 'owncloud', 'storage_name': 'test_storage_name',
                'owncloud_host': 'https://fake_end_point'
            }),
            content_type='application/json'
        )
        self.request.is_ajax()
        self.view = views.SaveCredentialsView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)

        nt.assert_equal(response.status_code, 400)

    def test_post_with_provider_short_name_nextcloud(self):
        institution = InstitutionFactory()

        self.user.is_staff = True
        self.user.affiliated_institutions.add(institution)
        self.user.save()
        self.request = RequestFactory().post(
            'custom_storage_location:save_credentials',
            json.dumps({
                'provider_short_name': 'nextcloud', 'storage_name': 'test_storage_name',
                'nextcloud_host': 'https://fake_end_point'
            }),
            content_type='application/json'
        )
        self.request.is_ajax()
        self.view = views.SaveCredentialsView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)

        nt.assert_equal(response.status_code, 400)

    def test_post_with_provider_short_name_nextcloudinstitutions(self):
        institution = InstitutionFactory()

        self.user.is_staff = True
        self.user.affiliated_institutions.add(institution)
        self.user.save()
        self.request = RequestFactory().post(
            'custom_storage_location:save_credentials',
            json.dumps({
                'provider_short_name': 'nextcloudinstitutions', 'storage_name': 'test_storage_name',
                'nextcloudinstitutions_host': 'https://fake_end_point'
            }),
            content_type='application/json'
        )
        self.request.is_ajax()
        self.view = views.SaveCredentialsView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)

        nt.assert_equal(response.status_code, 400)

    def test_post_with_provider_short_name_box(self):
        institution = InstitutionFactory()

        self.user.is_staff = True
        self.user.affiliated_institutions.add(institution)
        self.user.save()
        self.request = RequestFactory().post(
            'custom_storage_location:save_credentials',
            json.dumps({
                'provider_short_name': 'box', 'storage_name': 'test_storage_name',
                'new_storage_name': 'test_new_storage_name'
            }),
            content_type='application/json'
        )
        self.request.is_ajax()
        self.view = views.SaveCredentialsView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)

        nt.assert_equal(response.status_code, 400)

    def test_post_with_provider_short_name_dropboxbusiness(self):
        institution = InstitutionFactory()

        self.user.is_staff = True
        self.user.affiliated_institutions.add(institution)
        self.user.save()
        self.request = RequestFactory().post(
            'custom_storage_location:save_credentials',
            json.dumps({
                'provider_short_name': 'dropboxbusiness', 'storage_name': 'test_storage_name',
                'new_storage_name': 'test_new_storage_name'
            }),
            content_type='application/json'
        )
        self.request.is_ajax()
        self.view = views.SaveCredentialsView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)

        nt.assert_equal(response.status_code, 400)

    def test_post_with_provider_short_name_onedrivebusiness(self):
        institution = InstitutionFactory()

        self.user.is_staff = True
        self.user.affiliated_institutions.add(institution)
        self.user.save()
        self.request = RequestFactory().post(
            'custom_storage_location:save_credentials',
            json.dumps({
                'provider_short_name': 'onedrivebusiness', 'storage_name': 'test_storage_name',
                'new_storage_name': 'test_new_storage_name'
            }),
            content_type='application/json'
        )
        self.request.is_ajax()
        self.view = views.SaveCredentialsView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)

        nt.assert_equal(response.status_code, 400)

    def test_post_with_provider_short_name_invalid_provider(self):
        institution = InstitutionFactory()

        self.user.is_staff = True
        self.user.affiliated_institutions.add(institution)
        self.user.save()
        self.request = RequestFactory().post(
            'custom_storage_location:save_credentials',
            json.dumps({
                'provider_short_name': 'invalid_provider', 'storage_name': 'test_storage_name',
                'new_storage_name': 'test_new_storage_name'
            }),
            content_type='application/json'
        )
        self.request.is_ajax()
        self.view = views.SaveCredentialsView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)

        nt.assert_equal(response.status_code, 400)

    def test_post_with_empty_storage_name_and_provider_short_name(self):
        institution = InstitutionFactory()

        self.user.is_staff = True
        self.user.affiliated_institutions.add(institution)
        self.user.save()
        self.request = RequestFactory().post(
            'custom_storage_location:save_credentials',
            json.dumps({'provider_short_name': 'dropboxbusiness', 'storage_name': '', }),
            content_type='application/json'
        )
        self.request.is_ajax()
        self.view = views.SaveCredentialsView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)

        nt.assert_equal(response.status_code, 400)


class TestPermissionFetchTemporaryToken(AdminTestCase):

    def setUp(self):
        self.user = AuthUserFactory()

    def view_post(self, params):
        request = RequestFactory().post(
            'fake_path',
            json.dumps(params),
            content_type='application/json'
        )
        request.is_ajax()
        request.user = self.user
        return views.FetchTemporaryTokenView.as_view()(request)

    def test_normal_user(self):
        response = self.view_post({})
        self.assertEquals(response.status_code, 302)
        self.assertEquals(response._headers['location'][1], '/accounts/login/?next=/fake_path')

    def test_staff_without_institution(self):
        self.user.is_staff = True
        self.user.save()

        response = self.view_post({})
        self.assertEquals(response.status_code, 302)
        self.assertEquals(response._headers['location'][1], '/accounts/login/?next=/fake_path')

    def test_staff_with_institution(self):
        institution = InstitutionFactory()

        self.user.is_staff = True
        self.user.affiliated_institutions.add(institution)
        self.user.save()

        response = self.view_post({})
        nt.assert_is_instance(response, HttpResponse)

    def test_superuser(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()

        response = self.view_post({})
        self.assertEquals(response.status_code, 302)
        self.assertEquals(response._headers['location'][1], '/accounts/login/?next=/fake_path')


class TestChangeAuthenticationAttributeView(AdminTestCase):

    def setUp(self):
        self.user = AuthUserFactory()
        self.institution = InstitutionFactory()
        self.user.is_staff = True
        self.user.affiliated_institutions.add(self.institution)
        self.user.save()

        self.anon = AnonymousUser()

        self.normal_user = AuthUserFactory(fullname='normal_user')
        self.normal_user.is_staff = False
        self.normal_user.is_superuser = False
        self.normal_user.save()

        self.superuser = AuthUserFactory(fullname='superuser')
        self.superuser.is_staff = True
        self.superuser.is_superuser = True
        self.superuser.save()

        self.admin_not_inst = AuthUserFactory(fullname='admin_without_ins')
        self.admin_not_inst.is_staff = True
        self.admin_not_inst.save()

    def test_post_change_authentication_attribute(self):
        self.request = RequestFactory().post(
            'custom_storage_location:change_attribute_authentication',
            json.dumps({'is_active': True}),
            content_type='application/json'
        )

        self.view = views.ChangeAuthenticationAttributeView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 200)

    def test_post_change_authentication_attribute_missing_param(self):
        self.request = RequestFactory().post(
            'custom_storage_location:change_attribute_authentication',
            json.dumps({}),
            content_type='application/json'
        )
        self.view = views.ChangeAuthenticationAttributeView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)

    def test_permission_anonymous(self):
        request = RequestFactory().post(
            'custom_storage_location:change_attribute_authentication',
            json.dumps({'is_active': True}),
            content_type='application/json'
        )
        request.user = self.anon
        with nt.assert_raises(PermissionDenied):
            views.ChangeAuthenticationAttributeView.as_view()(request)

    def test_permission_normal_user(self):
        request = RequestFactory().post(
            'custom_storage_location:change_attribute_authentication',
            json.dumps({'is_active': True}),
            content_type='application/json'
        )
        request.user = self.normal_user
        with nt.assert_raises(PermissionDenied):
            views.ChangeAuthenticationAttributeView.as_view()(request)

    def test_permission_super(self):
        request = RequestFactory().post(
            'custom_storage_location:change_attribute_authentication',
            json.dumps({'is_active': True}),
            content_type='application/json'
        )
        request.user = self.superuser
        with nt.assert_raises(PermissionDenied):
            views.ChangeAuthenticationAttributeView.as_view()(request)

    def test_permission_admin_without_inst(self):
        request = RequestFactory().post(
            'custom_storage_location:change_attribute_authentication',
            json.dumps({'is_active': True}),
            content_type='application/json'
        )
        request.user = self.admin_not_inst
        with nt.assert_raises(PermissionDenied):
            views.ChangeAuthenticationAttributeView.as_view()(request)

    def test_permission_admin_without_body(self):
        self.request = RequestFactory().post(
            'custom_storage_location:change_attribute_authentication',
            json.dumps({}),
            content_type='application/json'
        )
        self.view = views.ChangeAuthenticationAttributeView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)

    def test_permission_admin_with_invalid_body(self):
        self.request = RequestFactory().post(
            'custom_storage_location:change_attribute_authentication',
            'example',
            content_type='application/json'
        )
        self.view = views.ChangeAuthenticationAttributeView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)


class TestAddAttributeFormView(AdminTestCase):

    def setUp(self):
        self.user = AuthUserFactory()
        self.institution = InstitutionFactory()
        self.user.is_staff = True
        self.user.affiliated_institutions.add(self.institution)
        self.user.save()

        self.anon = AnonymousUser()

        self.normal_user = AuthUserFactory(fullname='normal_user')
        self.normal_user.is_staff = False
        self.normal_user.is_superuser = False
        self.normal_user.save()

        self.superuser = AuthUserFactory(fullname='superuser')
        self.superuser.is_staff = True
        self.superuser.is_superuser = True
        self.superuser.save()

        self.admin_not_inst = AuthUserFactory(fullname='admin_without_ins')
        self.admin_not_inst.is_staff = True
        self.admin_not_inst.save()

        self.admin_not_auth = AuthUserFactory(fullname='admin_with_ins_not_authentication_attribute')
        self.institution_not_auth = InstitutionFactory()
        self.institution_not_auth.is_authentication_attribute = False
        self.institution_not_auth.save()

        self.admin_not_auth.is_staff = True
        self.admin_not_auth.affiliated_institutions.add(self.institution_not_auth)
        self.admin_not_auth.save()

    def test_add_first_attribute(self):
        self.request = RequestFactory().post(
            'custom_storage_location:add_attribute_form',
            json.dumps({}),
            content_type='application/json'
        )

        self.view = views.AddAttributeFormView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        attribute = AuthenticationAttribute.objects.get(
            institution=self.institution,
            index_number=api_settings.DEFAULT_INDEX_NUMBER
        )
        nt.assert_true(attribute is not None)
        nt.assert_equal(response.status_code, 200)

    def test_add_attribute_with_new_index_number(self):
        attribute_1 = AuthenticationAttribute.objects.create(
            institution=self.institution,
            index_number=api_settings.DEFAULT_INDEX_NUMBER
        )
        self.request = RequestFactory().post(
            'custom_storage_location:add_attribute_form',
            json.dumps({}),
            content_type='application/json'
        )

        self.view = views.AddAttributeFormView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        attribute_2 = AuthenticationAttribute.objects.get(
            institution=self.institution,
            index_number=api_settings.DEFAULT_INDEX_NUMBER + 1
        )
        nt.assert_equal(attribute_1.index_number + 1, attribute_2.index_number)
        nt.assert_equal(response.status_code, 200)

    def test_add_attribute_restore_renew_index(self):
        index = 2
        AuthenticationAttribute.objects.create(
            institution=self.institution,
            index_number=index,
            is_deleted=True
        )
        AuthenticationAttribute.objects.create(
            institution=self.institution,
            index_number=api_settings.MAX_INDEX_NUMBER,
        )
        self.request = RequestFactory().post(
            'custom_storage_location:add_attribute_form',
            json.dumps({}),
            content_type='application/json'
        )

        self.view = views.AddAttributeFormView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        attribute = AuthenticationAttribute.objects.get(
            institution=self.institution,
            index_number=index
        )
        nt.assert_true(attribute.is_deleted is False)
        nt.assert_equal(response.status_code, 200)

    def test_add_attribute_reached_limit(self):
        AuthenticationAttribute.objects.create(
            institution=self.institution,
            index_number=api_settings.MAX_INDEX_NUMBER,
        )
        self.request = RequestFactory().post(
            'custom_storage_location:add_attribute_form',
            json.dumps({}),
            content_type='application/json'
        )

        self.view = views.AddAttributeFormView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 404)

    def test_permission_anonymous(self):
        request = RequestFactory().post(
            'custom_storage_location:add_attribute_form',
            json.dumps({}),
            content_type='application/json'
        )

        request.user = self.anon
        with nt.assert_raises(PermissionDenied):
            views.AddAttributeFormView.as_view()(request)

    def test_permission_normal_user(self):
        request = RequestFactory().post(
            'custom_storage_location:add_attribute_form',
            json.dumps({}),
            content_type='application/json'
        )

        request.user = self.normal_user
        with nt.assert_raises(PermissionDenied):
            views.AddAttributeFormView.as_view()(request)

    def test_permission_super(self):
        request = RequestFactory().post(
            'custom_storage_location:add_attribute_form',
            json.dumps({}),
            content_type='application/json'
        )

        request.user = self.superuser
        with nt.assert_raises(PermissionDenied):
            views.AddAttributeFormView.as_view()(request)

    def test_permission_admin_without_inst(self):
        request = RequestFactory().post(
            'custom_storage_location:add_attribute_form',
            json.dumps({}),
            content_type='application/json'
        )

        request.user = self.admin_not_inst
        with nt.assert_raises(PermissionDenied):
            views.AddAttributeFormView.as_view()(request)

    def test_permission_admin_with_inst_not_auth(self):
        self.request = RequestFactory().post(
            'custom_storage_location:add_attribute_form',
            json.dumps({}),
            content_type='application/json'
        )

        self.view = views.AddAttributeFormView()
        self.view = setup_user_view(self.view, self.request, user=self.admin_not_auth)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)


class TestDeleteAttributeFormView(AdminTestCase):

    def setUp(self):
        self.user = AuthUserFactory()
        self.institution = InstitutionFactory()
        self.user.is_staff = True
        self.user.affiliated_institutions.add(self.institution)
        self.user.save()
        self.region = RegionFactory()
        self.region._id = self.institution._id
        self.region.save()

        self.anon = AnonymousUser()

        self.normal_user = AuthUserFactory(fullname='normal_user')
        self.normal_user.is_staff = False
        self.normal_user.is_superuser = False
        self.normal_user.save()

        self.superuser = AuthUserFactory(fullname='superuser')
        self.superuser.is_staff = True
        self.superuser.is_superuser = True
        self.superuser.save()

        self.admin_not_inst = AuthUserFactory(fullname='admin_without_ins')
        self.admin_not_inst.is_staff = True
        self.admin_not_inst.save()

        self.admin_not_auth = AuthUserFactory(fullname='admin_with_ins_not_authentication_attribute')
        self.institution_not_auth = InstitutionFactory()
        self.institution_not_auth.is_authentication_attribute = False
        self.institution_not_auth.save()

        self.admin_not_auth.is_staff = True
        self.admin_not_auth.affiliated_institutions.add(self.institution_not_auth)
        self.admin_not_auth.save()

    def test_can_delete_attribute(self):
        index = 2
        attribute = AuthenticationAttribute.objects.create(
            institution=self.institution,
            index_number=index,
        )
        self.request = RequestFactory().post(
            'custom_storage_location:delete_attribute_form',
            json.dumps({'id': attribute.id}),
            content_type='application/json'
        )

        self.view = views.DeleteAttributeFormView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        deleted_attribute = AuthenticationAttribute.objects.get(
            institution=self.institution,
            index_number=index,
        )

        nt.assert_true(deleted_attribute.is_deleted)
        nt.assert_equal(response.status_code, 200)

    def test_delete_attribute_missing_param(self):
        self.request = RequestFactory().post(
            'custom_storage_location:delete_attribute_form',
            json.dumps({}),
            content_type='application/json'
        )
        self.view = views.DeleteAttributeFormView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)

    def test_delete_attribute_does_not_exist(self):
        self.request = RequestFactory().post(
            'custom_storage_location:delete_attribute_form',
            json.dumps({'id': 2}),
            content_type='application/json'
        )
        self.view = views.DeleteAttributeFormView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 404)

    def test_delete_attribute_used_in_allow_expression(self):
        self.region.allow_expression = '1&&2'
        self.region.save()
        attribute = AuthenticationAttributeFactory(
            institution=self.institution,
            index_number=1
        )
        self.request = RequestFactory().post(
            'custom_storage_location:delete_attribute_form',
            json.dumps({'id': attribute.id}),
            content_type='application/json'
        )
        self.view = views.DeleteAttributeFormView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)

    def test_delete_attribute_used_in_readonly_expression(self):
        self.region.readonly_expression = '1||2'
        self.region.save()
        attribute = AuthenticationAttributeFactory(
            institution=self.institution,
            index_number=2
        )
        self.request = RequestFactory().post(
            'custom_storage_location:delete_attribute_form',
            json.dumps({'id': attribute.id}),
            content_type='application/json'
        )
        self.view = views.DeleteAttributeFormView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)

    def test_permission_anonymous(self):
        index = 2
        attribute = AuthenticationAttribute.objects.create(
            institution=self.institution,
            index_number=index,
        )
        request = RequestFactory().post(
            'custom_storage_location:delete_attribute_form',
            json.dumps({'id': attribute.id}),
            content_type='application/json'
        )

        request.user = self.anon
        with nt.assert_raises(PermissionDenied):
            views.DeleteAttributeFormView.as_view()(request)

    def test_permission_normal_user(self):
        index = 2
        attribute = AuthenticationAttribute.objects.create(
            institution=self.institution,
            index_number=index,
        )
        request = RequestFactory().post(
            'custom_storage_location:delete_attribute_form',
            json.dumps({'id': attribute.id}),
            content_type='application/json'
        )

        request.user = self.normal_user
        with nt.assert_raises(PermissionDenied):
            views.DeleteAttributeFormView.as_view()(request)

    def test_permission_super(self):
        index = 2
        attribute = AuthenticationAttribute.objects.create(
            institution=self.institution,
            index_number=index,
        )
        request = RequestFactory().post(
            'custom_storage_location:delete_attribute_form',
            json.dumps({'id': attribute.id}),
            content_type='application/json'
        )

        request.user = self.superuser
        with nt.assert_raises(PermissionDenied):
            views.DeleteAttributeFormView.as_view()(request)

    def test_permission_admin_without_inst(self):
        index = 2
        attribute = AuthenticationAttribute.objects.create(
            institution=self.institution,
            index_number=index,
        )
        request = RequestFactory().post(
            'custom_storage_location:delete_attribute_form',
            json.dumps({'id': attribute.id}),
            content_type='application/json'
        )

        request.user = self.admin_not_inst
        with nt.assert_raises(PermissionDenied):
            views.DeleteAttributeFormView.as_view()(request)

    def test_permission_admin_with_inst_not_auth(self):
        index = 2
        attribute = AuthenticationAttribute.objects.create(
            institution=self.institution,
            index_number=index,
        )
        self.request = RequestFactory().post(
            'custom_storage_location:delete_attribute_form',
            json.dumps({'id': attribute.id}),
            content_type='application/json'
        )

        self.view = views.DeleteAttributeFormView()
        self.view = setup_user_view(self.view, self.request, user=self.admin_not_auth)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)

    def test_permission_admin_without_body(self):
        self.request = RequestFactory().post(
            'custom_storage_location:delete_attribute_form',
            json.dumps({}),
            content_type='application/json'
        )

        self.view = views.DeleteAttributeFormView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)

    def test_permission_admin_with_invalid_body(self):
        self.request = RequestFactory().post(
            'custom_storage_location:delete_attribute_form',
            'example',
            content_type='application/json'
        )

        self.view = views.DeleteAttributeFormView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)


class TestSaveAttributeFormView(AdminTestCase):

    def setUp(self):
        self.user = AuthUserFactory()
        self.institution = InstitutionFactory()
        self.user.is_staff = True
        self.user.affiliated_institutions.add(self.institution)
        self.user.save()

        self.anon = AnonymousUser()

        self.normal_user = AuthUserFactory(fullname='normal_user')
        self.normal_user.is_staff = False
        self.normal_user.is_superuser = False
        self.normal_user.save()

        self.superuser = AuthUserFactory(fullname='superuser')
        self.superuser.is_staff = True
        self.superuser.is_superuser = True
        self.superuser.save()

        self.admin_not_inst = AuthUserFactory(fullname='admin_without_ins')
        self.admin_not_inst.is_staff = True
        self.admin_not_inst.save()

        self.admin_not_auth = AuthUserFactory(fullname='admin_with_ins_not_authentication_attribute')
        self.institution_not_auth = InstitutionFactory()
        self.institution_not_auth.is_authentication_attribute = False
        self.institution_not_auth.save()

        self.admin_not_auth.is_staff = True
        self.admin_not_auth.affiliated_institutions.add(self.institution_not_auth)
        self.admin_not_auth.save()

    def test_save_attribute_missing_params(self):
        self.request = RequestFactory().post(
            'custom_storage_location:save_attribute_form',
            json.dumps({'id': 2, 'attribute': 'name'}),
            content_type='application/json'
        )

        self.view = views.SaveAttributeFormView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)

    def test_save_attribute_not_in_defined_list(self):
        self.request = RequestFactory().post(
            'custom_storage_location:save_attribute_form',
            json.dumps({'id': 2, 'attribute': 'name', 'attribute_value': 'admin'}),
            content_type='application/json'
        )

        self.view = views.SaveAttributeFormView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)

    def test_save_attribute_does_not_exist(self):
        self.request = RequestFactory().post(
            'custom_storage_location:save_attribute_form',
            json.dumps({'id': 2, 'attribute': 'mail', 'attribute_value': 'admin'}),
            content_type='application/json'
        )

        self.view = views.SaveAttributeFormView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 404)

    def test_save_attribute_is_not_deleted(self):
        attribute = AuthenticationAttributeFactory()
        attribute_name_test = 'mail'
        attribute_value_test = 'admin'
        self.request = RequestFactory().post(
            'custom_storage_location:save_attribute_form',
            json.dumps({'id': attribute.id, 'attribute': attribute_name_test, 'attribute_value': attribute_value_test}),
            content_type='application/json'
        )

        self.view = views.SaveAttributeFormView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        updated_attribute = AuthenticationAttribute.objects.get(id=attribute.id)
        nt.assert_equal(updated_attribute.attribute_name, attribute_name_test)
        nt.assert_equal(updated_attribute.attribute_value, attribute_value_test)
        nt.assert_equal(response.status_code, 200)

    def test_save_attribute_is_deleted(self):
        attribute = AuthenticationAttributeFactory(is_deleted=True)
        attribute_name_test = 'mail'
        attribute_value_test = 'admin'
        self.request = RequestFactory().post(
            'custom_storage_location:save_attribute_form',
            json.dumps({'id': attribute.id, 'attribute': attribute_name_test, 'attribute_value': attribute_value_test}),
            content_type='application/json'
        )

        self.view = views.SaveAttributeFormView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        updated_attribute = AuthenticationAttribute.objects.get(id=attribute.id)
        nt.assert_not_equal(updated_attribute.attribute_name, attribute_name_test)
        nt.assert_not_equal(updated_attribute.attribute_value, attribute_value_test)
        nt.assert_equal(response.status_code, 404)

    def test_permission_anonymous(self):
        attribute = AuthenticationAttributeFactory()
        attribute_name_test = 'mail'
        attribute_value_test = 'admin'
        request = RequestFactory().post(
            'custom_storage_location:save_attribute_form',
            json.dumps({'id': attribute.id, 'attribute': attribute_name_test, 'attribute_value': attribute_value_test}),
            content_type='application/json'
        )

        request.user = self.anon
        with nt.assert_raises(PermissionDenied):
            views.SaveAttributeFormView.as_view()(request)

    def test_permission_normal_user(self):
        attribute = AuthenticationAttributeFactory()
        attribute_name_test = 'mail'
        attribute_value_test = 'admin'
        request = RequestFactory().post(
            'custom_storage_location:save_attribute_form',
            json.dumps({'id': attribute.id, 'attribute': attribute_name_test, 'attribute_value': attribute_value_test}),
            content_type='application/json'
        )

        request.user = self.normal_user
        with nt.assert_raises(PermissionDenied):
            views.SaveAttributeFormView.as_view()(request)

    def test_permission_super(self):
        attribute = AuthenticationAttributeFactory()
        attribute_name_test = 'mail'
        attribute_value_test = 'admin'
        request = RequestFactory().post(
            'custom_storage_location:save_attribute_form',
            json.dumps({'id': attribute.id, 'attribute': attribute_name_test, 'attribute_value': attribute_value_test}),
            content_type='application/json'
        )

        request.user = self.superuser
        with nt.assert_raises(PermissionDenied):
            views.SaveAttributeFormView.as_view()(request)

    def test_permission_admin_without_inst(self):
        attribute = AuthenticationAttributeFactory()
        attribute_name_test = 'mail'
        attribute_value_test = 'admin'
        request = RequestFactory().post(
            'custom_storage_location:save_attribute_form',
            json.dumps({'id': attribute.id, 'attribute': attribute_name_test, 'attribute_value': attribute_value_test}),
            content_type='application/json'
        )

        request.user = self.admin_not_inst
        with nt.assert_raises(PermissionDenied):
            views.SaveAttributeFormView.as_view()(request)

    def test_permission_admin_with_inst_not_auth(self):
        self.request = RequestFactory().post(
            'custom_storage_location:save_attribute_form',
            json.dumps({}),
            content_type='application/json'
        )

        self.view = views.SaveAttributeFormView()
        self.view = setup_user_view(self.view, self.request, user=self.admin_not_auth)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)

    def test_permission_admin_without_body(self):
        self.request = RequestFactory().post(
            'custom_storage_location:save_attribute_form',
            json.dumps({}),
            content_type='application/json'
        )

        self.view = views.SaveAttributeFormView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)

    def test_permission_admin_with_invalid_body(self):
        self.request = RequestFactory().post(
            'custom_storage_location:save_attribute_form',
            '',
            content_type='application/json'
        )

        self.view = views.SaveAttributeFormView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)

    def test_permission_admin_with_id_not_integer(self):
        attribute_name_test = 'mail'
        attribute_value_test = 'admin'
        self.request = RequestFactory().post(
            'custom_storage_location:save_attribute_form',
            json.dumps({'id': 'invalid', 'attribute': attribute_name_test, 'attribute_value': attribute_value_test}),
            content_type='application/json'
        )

        self.view = views.SaveAttributeFormView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)


class TestSaveInstitutionalStorageView(AdminTestCase):

    def setUp(self):
        self.user = AuthUserFactory()
        self.institution = InstitutionFactory()
        self.user.is_staff = True
        self.user.affiliated_institutions.add(self.institution)
        self.user.save()
        self.region = RegionFactory()
        self.region._id = self.institution._id
        self.region.save()
        self.attribute_1 = AuthenticationAttributeFactory(
            institution=self.institution, index_number=1
        )
        self.attribute_2 = AuthenticationAttributeFactory(
            institution=self.institution, index_number=2
        )

        self.anon = AnonymousUser()

        self.normal_user = AuthUserFactory(fullname='normal_user')
        self.normal_user.is_staff = False
        self.normal_user.is_superuser = False
        self.normal_user.save()

        self.superuser = AuthUserFactory(fullname='superuser')
        self.superuser.is_staff = True
        self.superuser.is_superuser = True
        self.superuser.save()

        self.admin_not_inst = AuthUserFactory(fullname='admin_without_ins')
        self.admin_not_inst.is_staff = True
        self.admin_not_inst.save()

        self.admin_not_auth = AuthUserFactory(fullname='admin_with_ins_not_authentication_attribute')
        self.institution_not_auth = InstitutionFactory()
        self.institution_not_auth.is_authentication_attribute = False
        self.institution_not_auth.save()

        self.admin_not_auth.is_staff = True
        self.admin_not_auth.affiliated_institutions.add(self.institution_not_auth)
        self.admin_not_auth.save()

    def test_save_institutional_storage_missing_params(self):
        self.request = RequestFactory().post(
            'custom_storage_location:save_institutional_storage',
            json.dumps({}),
            content_type='application/json'
        )

        self.view = views.SaveInstitutionalStorageView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)

    def test_save_institutional_storage_allow_expression_invalid(self):
        self.request = RequestFactory().post(
            'custom_storage_location:save_institutional_storage',
            json.dumps({
                'region_id': self.region.id,
                'allow': True,
                'readonly': False,
                'allow_expression': '1|2',
                'readonly_expression': ''
            }),
            content_type='application/json'
        )

        self.view = views.SaveInstitutionalStorageView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)

    def test_save_institutional_storage_readonly_expression_invalid(self):
        self.request = RequestFactory().post(
            'custom_storage_location:save_institutional_storage',
            json.dumps({
                'region_id': self.region.id,
                'allow': True,
                'readonly': False,
                'allow_expression': '',
                'readonly_expression': '(1&3&2)||3'
            }),
            content_type='application/json'
        )

        self.view = views.SaveInstitutionalStorageView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)

    def test_save_institutional_storage_index_number_in_allow_expression_not_found(self):
        self.request = RequestFactory().post(
            'custom_storage_location:save_institutional_storage',
            json.dumps({
                'region_id': self.region.id,
                'allow': True,
                'readonly': False,
                'allow_expression': '2||5',
                'readonly_expression': ''
            }),
            content_type='application/json'
        )

        self.view = views.SaveInstitutionalStorageView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)

    def test_save_institutional_storage_index_number_in_readonly_expression_not_found(self):
        self.request = RequestFactory().post(
            'custom_storage_location:save_institutional_storage',
            json.dumps({
                'region_id': self.region.id,
                'allow': True,
                'readonly': False,
                'allow_expression': '',
                'readonly_expression': '(2&&3)||4'
            }),
            content_type='application/json'
        )

        self.view = views.SaveInstitutionalStorageView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)

    def test_save_institutional_storage_region_not_found(self):
        self.request = RequestFactory().post(
            'custom_storage_location:save_institutional_storage',
            json.dumps({
                'region_id': self.region.id + 1,
                'allow': True,
                'readonly': False,
                'allow_expression': '',
                'readonly_expression': ''
            }),
            content_type='application/json'
        )

        self.view = views.SaveInstitutionalStorageView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 404)

    def test_save_institutional_storage_with_new_storage_name(self):
        self.attribute_1.attribute_name = 'given_name'
        self.attribute_1.attribute_value = 'test'
        self.attribute_2.attribute_name = 'username'
        self.attribute_2.attribute_value = 'test@gmail.com'
        self.attribute_1.save()
        self.attribute_2.save()
        region = RegionFactory()
        region._id = self.institution._id
        region.save()
        storage_name_test = region.name + 'test'
        allow_test = True
        readonly_test = False
        allow_expression_test = '1&&2'
        readonly_expression_test = '!1'
        self.request = RequestFactory().post(
            'custom_storage_location:save_institutional_storage',
            json.dumps({
                'region_id': region.id,
                'allow': allow_test,
                'readonly': readonly_test,
                'allow_expression': allow_expression_test,
                'readonly_expression': readonly_expression_test,
                'storage_name': storage_name_test
            }),
            content_type='application/json'
        )

        self.view = views.SaveInstitutionalStorageView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        updated_region = Region.objects.get(id=region.id)
        nt.assert_equal(updated_region.is_allowed, allow_test)
        nt.assert_equal(updated_region.is_readonly, readonly_test)
        nt.assert_equal(updated_region.allow_expression, allow_expression_test)
        nt.assert_equal(updated_region.readonly_expression, readonly_expression_test)
        nt.assert_equal(response.status_code, 200)

    def test_save_institutional_storage_with_existing_storage_name(self):
        region_test = RegionFactory()
        region_test._id = self.institution._id
        region_test.save()
        self.request = RequestFactory().post(
            'custom_storage_location:save_institutional_storage',
            json.dumps({'region_id': self.region.id,
                        'allow': True,
                        'readonly': False,
                        'allow_expression': '',
                        'readonly_expression': '',
                        'storage_name': region_test.name}),
            content_type='application/json'
        )

        self.view = views.SaveInstitutionalStorageView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)

    def test_permission_anonymous(self):
        region = RegionFactory()
        region._id = self.institution._id
        region.save()
        storage_name_test = region.name + 'test'
        allow_test = True
        readonly_test = False
        allow_expression_test = '1&&2'
        readonly_expression_test = '!1'
        request = RequestFactory().post(
            'custom_storage_location:save_institutional_storage',
            json.dumps({'region_id': region.id,
                        'allow': allow_test,
                        'readonly': readonly_test,
                        'allow_expression': allow_expression_test,
                        'readonly_expression': readonly_expression_test,
                        'storage_name': storage_name_test}),
            content_type='application/json'
        )

        request.user = self.anon
        with nt.assert_raises(PermissionDenied):
            views.SaveInstitutionalStorageView.as_view()(request)

    def test_permission_normal_user(self):
        region = RegionFactory()
        region._id = self.institution._id
        region.save()
        storage_name_test = region.name + 'test'
        allow_test = True
        readonly_test = False
        allow_expression_test = '1&&2'
        readonly_expression_test = '!1'
        request = RequestFactory().post(
            'custom_storage_location:save_institutional_storage',
            json.dumps({'region_id': region.id,
                        'allow': allow_test,
                        'readonly': readonly_test,
                        'allow_expression': allow_expression_test,
                        'readonly_expression': readonly_expression_test,
                        'storage_name': storage_name_test}),
            content_type='application/json'
        )

        request.user = self.normal_user
        with nt.assert_raises(PermissionDenied):
            views.SaveInstitutionalStorageView.as_view()(request)

    def test_permission_super(self):
        region = RegionFactory()
        region._id = self.institution._id
        region.save()
        storage_name_test = region.name + 'test'
        allow_test = True
        readonly_test = False
        allow_expression_test = '1&&2'
        readonly_expression_test = '!1'
        request = RequestFactory().post(
            'custom_storage_location:save_institutional_storage',
            json.dumps({'region_id': region.id,
                        'allow': allow_test,
                        'readonly': readonly_test,
                        'allow_expression': allow_expression_test,
                        'readonly_expression': readonly_expression_test,
                        'storage_name': storage_name_test}),
            content_type='application/json'
        )

        request.user = self.superuser
        with nt.assert_raises(PermissionDenied):
            views.SaveInstitutionalStorageView.as_view()(request)

    def test_permission_admin_without_inst(self):
        region = RegionFactory()
        region._id = self.institution._id
        region.save()
        storage_name_test = region.name + 'test'
        allow_test = True
        readonly_test = False
        allow_expression_test = '1&&2'
        readonly_expression_test = '!1'
        request = RequestFactory().post(
            'custom_storage_location:save_institutional_storage',
            json.dumps({'region_id': region.id,
                        'allow': allow_test,
                        'readonly': readonly_test,
                        'allow_expression': allow_expression_test,
                        'readonly_expression': readonly_expression_test,
                        'storage_name': storage_name_test}),
            content_type='application/json'
        )

        request.user = self.admin_not_inst
        with nt.assert_raises(PermissionDenied):
            views.SaveInstitutionalStorageView.as_view()(request)

    def test_permission_admin_without_body(self):
        self.request = RequestFactory().post(
            'custom_storage_location:save_institutional_storage',
            json.dumps({}),
            content_type='application/json'
        )

        self.view = views.SaveInstitutionalStorageView()
        self.view = setup_user_view(self.view, self.request, user=self.anon)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)

    def test_permission_admin_with_invalid_body(self):
        self.request = RequestFactory().post(
            'custom_storage_location:save_institutional_storage',
            'example',
            content_type='application/json'
        )

        self.view = views.SaveInstitutionalStorageView()
        self.view = setup_user_view(self.view, self.request, user=self.anon)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)

    def test_save_institutional_storage_with_invalid_region_id(self):
        self.request = RequestFactory().post(
            'custom_storage_location:save_institutional_storage',
            json.dumps({'region_id': 'demo',
                        'allow': True,
                        'readonly': False,
                        'allow_expression': '',
                        'readonly_expression': ''}),
            content_type='application/json'
        )

        self.view = views.SaveInstitutionalStorageView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)

    def test_save_institutional_storage_with_invalid_allow(self):
        self.request = RequestFactory().post(
            'custom_storage_location:save_institutional_storage',
            json.dumps({'region_id': self.region.id,
                        'allow': 'demo',
                        'readonly': False,
                        'allow_expression': '',
                        'readonly_expression': ''}),
            content_type='application/json'
        )

        self.view = views.SaveInstitutionalStorageView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 400)


class TestInstitutionalStorageBaseView(AdminTestCase):

    def setUp(self):
        self.user = AuthUserFactory()
        self.institution = InstitutionFactory()
        self.user.is_staff = True
        self.user.affiliated_institutions.add(self.institution)
        self.user.save()

        self.anon = AnonymousUser()

        self.normal_user = AuthUserFactory(fullname='normal_user')
        self.normal_user.is_staff = False
        self.normal_user.is_superuser = False
        self.normal_user.save()

        self.superuser = AuthUserFactory(fullname='superuser')
        self.superuser.is_staff = True
        self.superuser.is_superuser = True
        self.superuser.save()

        self.admin_not_inst = AuthUserFactory(fullname='admin_without_ins')
        self.admin_not_inst.is_staff = True
        self.admin_not_inst.save()

        self.request = RequestFactory().get('/fake_path')
        self.view = views.InstitutionalStorageBaseView()

    def test__test_func_anonymous(self):
        nt.assert_false(setup_user_view(self.view, self.request, user=self.anon).test_func())

    def test__test_func_normal_user(self):
        nt.assert_false(setup_user_view(self.view, self.request, user=self.normal_user).test_func())

    def test__test_func_super_user(self):
        nt.assert_false(setup_user_view(self.view, self.request, user=self.superuser).test_func())

    def test__test_func_admin_not_inst(self):
        nt.assert_false(setup_user_view(self.view, self.request, user=self.admin_not_inst).test_func())

    def test__test_func_admin_has_inst(self):
        nt.assert_true(setup_user_view(self.view, self.request, user=self.user).test_func())      


class TestCheckExistingStorageView(AdminTestCase):

    def setUp(self):
        self.user = AuthUserFactory()
        self.institution = InstitutionFactory()
        self.user.is_staff = True
        self.user.affiliated_institutions.add(self.institution)
        self.user.save()

        self.anon = AnonymousUser()

        self.normal_user = AuthUserFactory(fullname='normal_user')
        self.normal_user.is_staff = False
        self.normal_user.is_superuser = False
        self.normal_user.save()

        self.superuser = AuthUserFactory(fullname='superuser')
        self.superuser.is_staff = True
        self.superuser.is_superuser = True
        self.superuser.save()

        self.admin_not_inst = AuthUserFactory(fullname='admin_without_ins')
        self.admin_not_inst.is_staff = True
        self.admin_not_inst.save()

    def test_permission_anonymous(self):
        request = RequestFactory().post(
            'custom_storage_location:check_existing_storage',
            json.dumps({'provider': 'osfstorage'}),
            content_type='application/json'
        )

        request.user = self.anon
        with nt.assert_raises(PermissionDenied):
            views.CheckExistingStorage.as_view()(request)

    def test_permission_normal_user(self):
        request = RequestFactory().post(
            'custom_storage_location:check_existing_storage',
            json.dumps({'provider': 'osfstorage'}),
            content_type='application/json'
        )

        request.user = self.normal_user
        with nt.assert_raises(PermissionDenied):
            views.CheckExistingStorage.as_view()(request)

    def test_permission_super(self):
        request = RequestFactory().post(
            'custom_storage_location:check_existing_storage',
            json.dumps({'provider': 'osfstorage'}),
            content_type='application/json'
        )

        request.user = self.superuser
        with nt.assert_raises(PermissionDenied):
            views.CheckExistingStorage.as_view()(request)

    def test_permission_admin_without_inst(self):
        request = RequestFactory().post(
            'custom_storage_location:check_existing_storage',
            json.dumps({'provider': 'osfstorage'}),
            content_type='application/json'
        )

        request.user = self.admin_not_inst
        with nt.assert_raises(PermissionDenied):
            views.CheckExistingStorage.as_view()(request)

    def test_permission_admin_success(self):
        config = {
            'storage': {
                'provider': 'osfstorage',
                'container': 'osf_storage',
                'use_public': True,
            }
        }
        region = RegionFactory(waterbutler_settings=config)
        region._id = self.institution._id
        self.request = RequestFactory().post(
            'custom_storage_location:check_existing_storage',
            json.dumps({'provider': 's3'}),
            content_type='application/json'
        )
        self.view = views.CheckExistingStorage()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        response = self.view.post(self.request)
        nt.assert_equal(response.status_code, 200)

    def test_permission_admin_conflict(self):
        config = {
            'storage': {
                'provider': 'osfstorage',
                'container': 'osf_storage',
                'use_public': True,
            }
        }
        region = RegionFactory(waterbutler_settings=config)
        region._id = self.institution._id
        request = RequestFactory().post(
            'custom_storage_location:check_existing_storage',
            json.dumps({'provider': 'osfstorage'}),
            content_type='application/json'
        )
        self.view = views.CheckExistingStorage()
        self.view = setup_user_view(self.view, request, user=self.user)
        response = self.view.post(request)
        nt.assert_equal(response.status_code, 409)
