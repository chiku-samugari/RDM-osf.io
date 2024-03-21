from unittest import mock

import pytest
from addons.osfstorage.models import Region
from admin.institutional_storage_quota_control import views
from django.http import Http404
from django.test import RequestFactory
from django.urls import reverse
from osf.models.user_storage_quota import UserStorageQuota
from nose import tools as nt
from osf.models import UserQuota
from admin_tests.utilities import setup_view, setup_user_view
from osf_tests.factories import (
    AuthUserFactory,
    InstitutionFactory,
    RegionFactory,
    RegionExtraFactory
)
from tests.base import AdminTestCase
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBadRequest


pytestmark = pytest.mark.django_db


class TestUpdateQuotaUserListByInstitutionStorageID(AdminTestCase):
    def setUp(self):
        super(TestUpdateQuotaUserListByInstitutionStorageID, self).setUp()
        self.user1 = AuthUserFactory(fullname='fullname1')
        self.institution = InstitutionFactory()
        self.region = RegionFactory(_id=self.institution._id, name='Storage')
        self.user1.affiliated_institutions.add(self.institution)
        self.user1.is_staff = True
        self.user1.is_superuser = True
        self.user1.save()

        self.view = views.UpdateQuotaUserListByInstitutionStorageID.as_view()

        self.institution_1 = InstitutionFactory()
        self.institution_2 = InstitutionFactory()
        self.region_1 = RegionFactory(_id=self.institution_1._id, name='Storage')

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

        self.institution1_admin = AuthUserFactory(fullname='admin001_inst01')
        self.institution1_admin.is_staff = True
        self.institution1_admin.affiliated_institutions.add(self.institution_1)
        self.institution1_admin.save()

        self.institution2_admin = AuthUserFactory(fullname='admin001_inst02')
        self.institution2_admin.is_staff = True
        self.institution2_admin.affiliated_institutions.add(self.institution_2)
        self.institution2_admin.save()

    def test_post_create_quota(self):
        max_quota = 50
        request = RequestFactory().post(
            reverse(
                'institutional_storage_quota_control'
                ':update_quota_institution_user_list',
                kwargs={'institution_id': self.institution.id}),
            {'maxQuota': max_quota, 'region_id': self.region.id})
        request.user = self.user1

        response = self.view(
            request,
            institution_id=self.institution.id
        )

        nt.assert_equal(response.status_code, 302)
        user_quota = UserStorageQuota.objects.filter(
            user=self.user1, region_id=self.region.id
        ).first()
        nt.assert_is_not_none(user_quota)
        nt.assert_equal(user_quota.max_quota, max_quota)

    def test_post_update_quota_exits(self):
        max_quota = 50
        request = RequestFactory().post(
            reverse(
                'institutional_storage_quota_control:update_quota_institution_user_list',
                kwargs={'institution_id': self.institution.id}),
            {'maxQuota': max_quota, 'region_id': self.region.id})
        request.user = self.user1
        init_user_quota = UserQuota.objects.create(
            user=self.user1, storage_type=UserQuota.CUSTOM_STORAGE, max_quota=300
        )
        UserStorageQuota.objects.create(
            user=self.user1, region=self.region, used=22, max_quota=150
        )
        response = self.view(
            request,
            institution_id=self.institution.id
        )

        nt.assert_equal(response.status_code, 302)
        user_quota = UserQuota.objects.filter(
            user=self.user1, storage_type=UserQuota.CUSTOM_STORAGE
        ).first()
        user_storage_quota = UserStorageQuota.objects.filter(
            user=self.user1, region=self.region
        ).first()
        nt.assert_is_not_none(user_quota)
        nt.assert_equal(user_quota.max_quota, init_user_quota.max_quota)
        nt.assert_is_not_none(user_storage_quota)
        nt.assert_equal(user_storage_quota.max_quota, max_quota)

    def test_post_update_quota_less_than_zero(self):
        max_quota = 50
        request = RequestFactory().post(
            reverse(
                'institutional_storage_quota_control:update_quota_institution_user_list',
                kwargs={'institution_id': self.institution.id}),
            {'maxQuota': max_quota, 'region_id': self.region.id})
        request.user = self.user1
        UserStorageQuota.objects.create(
            user=self.user1, region=self.region, max_quota=150, used=22
        )
        response = self.view(
            request,
            institution_id=self.institution.id
        )

        nt.assert_equal(response.status_code, 302)
        user_storage_quota = UserStorageQuota.objects.filter(
            user=self.user1, region=self.region
        ).first()
        nt.assert_is_not_none(user_storage_quota)
        nt.assert_equal(user_storage_quota.max_quota, max_quota)

    def test_post_create_quota_not_found(self):
        max_quota = 50
        request = RequestFactory().post(
            reverse(
                'institutional_storage_quota_control'
                ':update_quota_institution_user_list',
                kwargs={'institution_id': self.institution.id}),
            {'maxQuota': max_quota, 'region_id': 0})
        request.user = self.user1

        with pytest.raises(Http404):
            self.view(
                request,
                institution_id=self.institution.id
            )

    def test__anonymous(self):
        max_quota = 50
        request = RequestFactory().post(
            reverse(
                'institutional_storage_quota_control:update_quota_institution_user_list',
                kwargs={'institution_id': self.institution.id}),
            {'maxQuota': max_quota, 'region_id': self.region.id})
        request.user = self.anon
        with self.assertRaises(PermissionDenied):
            self.view(request, institution_id=self.institution.id)

    def test__normal_user(self):
        max_quota = 50
        request = RequestFactory().post(
            reverse(
                'institutional_storage_quota_control:update_quota_institution_user_list',
                kwargs={'institution_id': self.institution.id}),
            {'maxQuota': max_quota, 'region_id': self.region.id})
        request.user = self.normal_user
        with self.assertRaises(PermissionDenied):
            self.view(request, institution_id=self.institution.id)

    def test__admin_without_institution(self):
        max_quota = 50
        request = RequestFactory().post(
            reverse(
                'institutional_storage_quota_control:update_quota_institution_user_list',
                kwargs={'institution_id': self.institution.id}),
            {'maxQuota': max_quota, 'region_id': self.region.id})
        request.user = self.admin_not_inst
        with self.assertRaises(PermissionDenied):
            self.view(request, institution_id=self.institution.id)

    def test__admin_without_permission(self):
        max_quota = 50
        request = RequestFactory().post(
            reverse(
                'institutional_storage_quota_control:update_quota_institution_user_list',
                kwargs={'institution_id': self.institution_1.id}),
            {'maxQuota': max_quota, 'region_id': self.region.id})
        request.user = self.institution2_admin
        with self.assertRaises(PermissionDenied):
            self.view(request, institution_id=self.institution_1.id)

    def test__admin_has_permission(self):
        max_quota = 50
        request = RequestFactory().post(
            reverse(
                'institutional_storage_quota_control'
                ':update_quota_institution_user_list',
                kwargs={'institution_id': self.institution_1.id}),
            {'maxQuota': max_quota, 'region_id': self.region_1.id})
        request.user = self.institution1_admin
        self.view.institution_id = self.institution_1.id
        self.view.institution = self.institution_1
        response = self.view(
            request,
            institution_id=self.institution_1.id
        )

        nt.assert_equal(response.status_code, 302)
        user_quota = UserStorageQuota.objects.filter(
            user=self.institution1_admin, region_id=self.region_1.id
        ).first()
        nt.assert_is_not_none(user_quota)
        nt.assert_equal(user_quota.max_quota, max_quota)

    @mock.patch('admin.institutional_storage_quota_control.views.render_bad_request_response')
    def test__post_region_invalid(self, mock_render):
        mock_render.return_value = HttpResponseBadRequest(content='fake')
        max_quota = 50
        request = RequestFactory().post(
            reverse(
                'institutional_storage_quota_control:update_quota_institution_user_list',
                kwargs={'institution_id': self.institution_1.id}),
            {'maxQuota': max_quota, 'region_id': 'abc'})
        request.user = self.superuser
        response = self.view(
            request,
            institution_id=self.institution_1.id
        )
        nt.assert_equal(response.status_code, 400)

    @mock.patch('admin.institutional_storage_quota_control.views.render_bad_request_response')
    def test__post_region_not_same_institution(self, mock_render):
        mock_render.return_value = HttpResponseBadRequest(content='fake')
        max_quota = 50
        request = RequestFactory().post(
            reverse(
                'institutional_storage_quota_control:update_quota_institution_user_list',
                kwargs={'institution_id': self.institution_1.id}),
            {'maxQuota': max_quota, 'region_id': self.region.id})
        request.user = self.superuser
        response = self.view(
            request,
            institution_id=self.institution_1.id
        )
        nt.assert_equal(response.status_code, 400)

    def test__post_institution_not_exist(self):
        max_quota = 50
        request = RequestFactory().post(
            reverse(
                'institutional_storage_quota_control'
                ':update_quota_institution_user_list',
                kwargs={'institution_id': 0}),
            {'maxQuota': max_quota, 'region_id': self.region.id})
        request.user = self.user1

        with pytest.raises(Http404):
            self.view(
                request,
                institution_id=0
            )


class TestUserListByInstitutionStorageID(AdminTestCase):
    def setUp(self):
        super(TestUserListByInstitutionStorageID, self).setUp()
        self.user = AuthUserFactory(fullname='fullname')
        self.institution = InstitutionFactory()
        self.region = RegionFactory(_id=self.institution._id, name='Storage')
        self.user.affiliated_institutions.add(self.institution)
        self.user.is_staff = True
        self.user.save()

        self.view = views.UserListByInstitutionStorageID()

        self.institution_1 = InstitutionFactory()
        self.institution_2 = InstitutionFactory()
        self.region_1 = RegionFactory(_id=self.institution_1._id, name='Storage')

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

        self.institution1_admin = AuthUserFactory(fullname='admin001_inst01')
        self.institution1_admin.is_staff = True
        self.institution1_admin.affiliated_institutions.add(self.institution_1)
        self.institution1_admin.save()

        self.institution2_admin = AuthUserFactory(fullname='admin001_inst02')
        self.institution2_admin.is_staff = True
        self.institution2_admin.affiliated_institutions.add(self.institution_2)
        self.institution2_admin.save()

    @mock.patch('admin.institutional_storage_quota_control.views.UserListByInstitutionStorageID.get_region')
    @mock.patch('admin.institutions.views.QuotaUserStorageList.get_user_storage_quota_info')
    @mock.patch('admin.institutions.views.QuotaUserList.get_queryset')
    def test_get_user_list(self, mock_get_queryset, mock_quota, mock_region):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:institution_user_list',
                kwargs={'institution_id': self.institution.id, 'region_id': self.region.id})
        )
        mock_region.return_value = self.region
        mock_quota.return_value = {}
        mock_get_queryset.return_value = []
        request.user = self.user

        view = setup_view(self.view, request,
                          institution_id=self.institution.id)
        user_list = view.get_user_list()

        nt.assert_equal(len(user_list), 3)

    @mock.patch('admin.institutional_storage_quota_control.views.UserListByInstitutionStorageID.get_region')
    def test_get_institution(self, mock_region):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:institution_user_list',
                kwargs={'institution_id': self.institution.id, 'region_id': self.region.id})
        )
        mock_region.return_value = self.region
        request.user = self.user

        view = setup_view(self.view, request,
                          institution_id=self.institution.id)
        view.institution_id = self.institution.id
        view.region_id = self.region.id
        view.region = self.region
        institution = view.get_institution()

        nt.assert_equal(institution.storage_name, self.region.name)

    @mock.patch('admin.institutional_storage_quota_control.views.UserListByInstitutionStorageID.get_region')
    @mock.patch('admin.institutions.views.QuotaUserStorageList.get_user_storage_quota_info')
    @mock.patch('admin.institutions.views.QuotaUserList.get_queryset')
    def test_get_context_data_has_storage_name(self, mock_get_queryset, mock_quota, mock_region):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:institution_user_list',
                kwargs={'institution_id': self.institution.id, 'region_id': self.region.id})
        )
        mock_quota.return_value = {}
        mock_get_queryset.return_value = []
        mock_region.return_value = self.region
        request.user = self.user
        view = setup_view(self.view, request,
                          institution_id=self.institution.id)
        view.institution_id = self.institution.id
        view.region_id = self.region.id
        view.region = self.region
        view.object_list = view.get_queryset()
        res = view.get_context_data()

        nt.assert_is_instance(res, dict)
        nt.assert_equal(res['institution_storage_name'], self.region.name)

    @mock.patch('admin.institutional_storage_quota_control.views.UserListByInstitutionStorageID.get_region')
    def test_get_institution_not_found(self, mock_region):
        region = RegionFactory()
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:institution_user_list',
                kwargs={'institution_id': self.institution.id, 'region_id': region.id})
        )
        mock_region.return_value = region
        request.user = self.user
        view = setup_view(self.view, request,
                          institution_id=self.institution.id)
        view.institution_id = self.institution.id
        view.region_id = self.region.id
        view.region = self.region
        institution = view.get_institution()
        nt.assert_equal(institution.storage_name, None)

    def test__anonymous(self):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:institution_user_list',
                kwargs={'institution_id': self.institution.id, 'region_id': self.region.id})
        )
        request.user = self.anon
        with nt.assert_raises(PermissionDenied):
            views.UserListByInstitutionStorageID.as_view()(request)

    def test__normal_user(self):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:institution_user_list',
                kwargs={'institution_id': self.institution.id, 'region_id': self.region.id})
        )
        request.user = self.normal_user
        with nt.assert_raises(PermissionDenied):
            views.UserListByInstitutionStorageID.as_view()(request, institution_id=self.institution.id, region_id=self.region.id)

    def test__super(self):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:institution_user_list',
                kwargs={'institution_id': self.institution.id, 'region_id': self.region.id})
        )
        request.user = self.superuser
        view = views.UserListByInstitutionStorageID.as_view()(request, institution_id=self.institution.id, region_id=self.region.id)
        nt.assert_equals(view.status_code, 200)

    def test__admin_without_inst(self):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:institution_user_list',
                kwargs={'institution_id': self.institution.id, 'region_id': self.region.id})
        )
        request.user = self.admin_not_inst
        with nt.assert_raises(PermissionDenied):
            views.UserListByInstitutionStorageID.as_view()(request, institution_id=self.institution.id, region_id=self.region.id)

    def test__admin_without_permission(self):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:institution_user_list',
                kwargs={'institution_id': self.institution.id, 'region_id': self.region.id})
        )
        request.user = self.institution1_admin
        with nt.assert_raises(PermissionDenied):
            views.UserListByInstitutionStorageID.as_view()(request, institution_id=self.institution.id, region_id=self.region.id)

    def test__not_same_institution(self):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:institution_user_list',
                kwargs={'institution_id': self.institution.id, 'region_id': self.region_1.id})
        )
        request.user = self.superuser
        with nt.assert_raises(PermissionDenied):
            views.UserListByInstitutionStorageID.as_view()(request, institution_id=self.institution.id, region_id=self.region_1.id)

    def test__not_exist_institution(self):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:institution_user_list',
                kwargs={'institution_id': 0, 'region_id': self.region_1.id})
        )
        request.user = self.superuser
        with nt.assert_raises(Http404):
            views.UserListByInstitutionStorageID.as_view()(request, institution_id=0, region_id=self.region.id)

    def test__not_exist_region(self):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:institution_user_list',
                kwargs={'institution_id': self.institution.id, 'region_id': 0})
        )
        request.user = self.superuser
        with nt.assert_raises(Http404):
            views.UserListByInstitutionStorageID.as_view()(request, institution_id=self.institution.id, region_id=0)


class TestInstitutionStorageListByAdmin(AdminTestCase):
    def setUp(self):
        super(TestInstitutionStorageListByAdmin, self).setUp()
        self.user = AuthUserFactory(fullname='fullname')
        self.user.is_registered = True
        self.user.is_active = True
        self.user.is_staff = True
        self.user.is_superuser = False
        self.institution = InstitutionFactory()
        self.region = RegionFactory(_id=self.institution._id, name='Storage')
        self.user.affiliated_institutions.add(self.institution)
        self.user.save()

        self.view = views.InstitutionStorageList.as_view()

        self.anon = AnonymousUser()

        self.normal_user = AuthUserFactory(fullname='normal_user')
        self.normal_user.is_staff = False
        self.normal_user.is_superuser = False
        self.normal_user.save()

        self.admin_not_inst = AuthUserFactory(fullname='admin_without_ins')
        self.admin_not_inst.is_staff = True
        self.admin_not_inst.save()

    def test_get_redirect_to_user_list(self):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:list_institution_storage'
            )
        )
        request.user = self.user

        response = self.view(
            request,
            institution_id=self.institution.id
        )

        nt.assert_equal(response.status_code, 200)

    def test_get_render_response(self):
        inst1 = InstitutionFactory()
        inst2 = InstitutionFactory()
        region1 = RegionFactory(_id=inst1._id, name='Storage1')
        region2 = RegionFactory(_id=inst2._id, name='Storage2')
        self.user.affiliated_institutions.add(inst1)
        self.user.save()

        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:list_institution_storage'
            )
        )
        request.user = self.user

        response = self.view(
            request,
        )

        nt.assert_equal(response.status_code, 200)
        nt.assert_is_not_none(Region.objects.filter(id=region1.id))
        nt.assert_is_not_none(Region.objects.filter(id=region2.id))
        nt.assert_is_instance(
            response.context_data['view'],
            views.InstitutionStorageList
        )

    def test_get_query_set(self):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:list_institution_storage'
            )
        )
        request.user = self.user
        view = views.InstitutionStorageList()
        view = setup_view(view, request)
        query_set = view.get_queryset()

        nt.assert_equal(query_set.exists(), True)

    def test_get_context_data(self):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:list_institution_storage'
            )
        )
        request.user = self.user
        view = views.InstitutionStorageList()
        view = setup_view(view, request)
        view.object_list = view.get_queryset()

        res = view.get_context_data()

        nt.assert_is_instance(res, dict)
        nt.assert_is_instance(res['view'], views.InstitutionStorageList)

    def test_merge_data(self):
        view = views.InstitutionStorageList()
        institution_1 = InstitutionFactory()
        region_1 = RegionExtraFactory(institution_id=institution_1._id, name='Storage_1')
        institution_2 = InstitutionFactory()
        region_2 = RegionExtraFactory(institution_id=institution_2._id, name='Storage_2')
        region_3 = RegionExtraFactory(institution_id=institution_1._id, name='Storage_1_1')
        input_data = [region_1, region_2, region_3]
        res = view.merge_data(input_data)
        assert len(res) == 2
        assert res[0].institution_id == institution_1._id
        assert res[1].institution_id == institution_2._id

    def test_permission_anonymous(self):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:list_institution_storage'
            )
        )
        request.user = self.anon

        with nt.assert_raises(PermissionDenied):
            self.view(
                request,
                institution_id=self.institution.id
            )

    def test_permission_normal_user(self):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:list_institution_storage'
            )
        )
        request.user = self.normal_user

        with nt.assert_raises(PermissionDenied):
            self.view(
                request,
                institution_id=self.institution.id
            )

    def test_permission_admin_without_inst(self):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:list_institution_storage'
            )
        )
        request.user = self.admin_not_inst

        with nt.assert_raises(PermissionDenied):
            self.view(
                request,
                institution_id=self.institution.id
            )


class TestInstitutionStorageListBySuperUser(AdminTestCase):
    def setUp(self):
        super(TestInstitutionStorageListBySuperUser, self).setUp()
        self.user = AuthUserFactory(fullname='fullname')
        self.user.is_registered = True
        self.user.is_active = True
        self.user.is_superuser = True
        self.institution = InstitutionFactory()
        self.institution_1 = InstitutionFactory()
        self.region = RegionFactory(_id=self.institution._id, name='Storage')
        self.region_1 = RegionFactory(_id=self.institution_1._id,
                                      name='Storage_1')
        self.user.affiliated_institutions.add(self.institution)
        self.user.save()

        self.view = views.InstitutionStorageList.as_view()

    def test_get_render_response(self):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:list_institution_storage'
            )
        )
        request.user = self.user

        response = self.view(
            request,
        )

        nt.assert_equal(response.status_code, 200)
        nt.assert_is_instance(
            response.context_data['view'],
            views.InstitutionStorageList
        )

    def test_get_query_set(self):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:list_institution_storage'
            )
        )
        request.user = self.user
        view = views.InstitutionStorageList()
        view = setup_view(view, request)
        query_set = view.get_queryset()

        nt.assert_equal(query_set.exists(), True)
        nt.assert_equal(len(query_set), 3)


class TestIconView(AdminTestCase):
    def setUp(self):
        super(TestIconView, self).setUp()
        self.user = AuthUserFactory()
        self.user.is_active = True
        self.user.is_staff = True
        self.institution = InstitutionFactory()
        self.user.affiliated_institutions.add(self.institution)
        self.user.save()

        self.request = RequestFactory().get('/fake_path')

        self.view = views.IconView()
        self.view = setup_user_view(self.view, self.request, user=self.user)
        self.view.kwargs = {'addon_name': 's3'}

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

    def tearDown(self):
        super(TestIconView, self).tearDown()
        self.user.delete()

    def test_valid_get(self, *args, **kwargs):
        res = self.view.get(self.request, *args, **self.view.kwargs)
        nt.assert_equal(res.status_code, 200)

    def test_get_icon_view_not_found(self):
        with pytest.raises(Http404):
            request = RequestFactory().get('/fake_path')
            view = setup_user_view(views.IconView.as_view(), request, user=self.user)
            view(request, addon_name='test_addon_name')

    def test_permission_anonymous(self):
        with nt.assert_raises(PermissionDenied):
            request = RequestFactory().get('/fake_path')
            view = setup_user_view(views.IconView.as_view(), request, user=self.anon)
            view(request, addon_name='test_addon_name')

    def test_permission_normal_user(self):
        with nt.assert_raises(PermissionDenied):
            request = RequestFactory().get('/fake_path')
            view = setup_user_view(views.IconView.as_view(), request, user=self.normal_user)
            view(request, addon_name='test_addon_name')

    def test_permission_super(self, *args, **kwargs):
        request = RequestFactory().get('/fake_path')
        request.user = self.superuser
        res = self.view.get(request, *args, **self.view.kwargs)
        nt.assert_equal(res.status_code, 200)

    def test_permission_admin_without_inst(self):
        with nt.assert_raises(PermissionDenied):
            request = RequestFactory().get('/fake_path')
            view = setup_user_view(views.IconView.as_view(), request, user=self.admin_not_inst)
            view(request, addon_name='test_addon_name')

    def test_permission_admin_has_permission(self, *args, **kwargs):
        request = RequestFactory().get('/fake_path')
        request.user = self.user
        res = self.view.get(request, *args, **self.view.kwargs)
        nt.assert_equal(res.status_code, 200)


class TestProviderListByInstitution(AdminTestCase):
    def setUp(self):
        super(TestProviderListByInstitution, self).setUp()
        self.user = AuthUserFactory(fullname='fullname')
        self.user.is_registered = True
        self.user.is_active = True
        self.user.is_superuser = True
        self.institution = InstitutionFactory()
        self.institution_1 = InstitutionFactory()
        self.institution_2 = InstitutionFactory()
        self.region = RegionFactory(_id=self.institution._id, name='Storage')
        self.region_1 = RegionFactory(_id=self.institution_1._id,
                                      name='Storage_1')
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

        self.institution1_admin = AuthUserFactory(fullname='admin001_inst01')
        self.institution1_admin.is_staff = True
        self.institution1_admin.affiliated_institutions.add(self.institution_1)
        self.institution1_admin.save()

        self.institution2_admin = AuthUserFactory(fullname='admin001_inst02')
        self.institution2_admin.is_staff = True
        self.institution2_admin.affiliated_institutions.add(self.institution_2)
        self.institution2_admin.save()

        self.view = views.ProviderListByInstitution.as_view()

    def test_get_context_data(self):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:institutional_storages',
                kwargs={'institution_id': self.institution.id}
            )
        )
        request.user = self.user
        self.view(
            request,
            institution_id=self.institution.id
        )

    def test_get_order_by(self):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:institutional_storages',
                kwargs={'institution_id': self.institution.id}
            ),
            {'order_by': 'provider', 'status': 'abc'}
        )
        request.user = self.user
        self.view(
            request,
            institution_id=self.institution.id
        )

    def test_permission_anonymous(self):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:institutional_storages',
                kwargs={'institution_id': self.institution.id}
            )
        )
        request.user = self.anon
        with nt.assert_raises(PermissionDenied):
            self.view(
                request,
                institution_id=self.institution.id
            )

    def test_permission_normal_user(self):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:institutional_storages',
                kwargs={'institution_id': self.institution.id}
            )
        )
        request.user = self.normal_user
        with nt.assert_raises(PermissionDenied):
            self.view(
                request,
                institution_id=self.institution.id
            )

    def test_permission_super(self):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:institutional_storages',
                kwargs={'institution_id': self.institution.id}
            )
        )
        request.user = self.superuser
        response = self.view(
            request,
            institution_id=self.institution.id
        )
        nt.assert_equal(response.status_code, 302)

    def test_permission_admin_without_inst(self):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:institutional_storages',
                kwargs={'institution_id': self.institution.id}
            )
        )
        request.user = self.admin_not_inst
        with nt.assert_raises(PermissionDenied):
            self.view(
                request,
                institution_id=self.institution.id
            )

    def test_permission_admin_not_permission(self):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:institutional_storages',
                kwargs={'institution_id': self.institution_2.id}
            )
        )
        request.user = self.institution1_admin
        with nt.assert_raises(PermissionDenied):
            self.view(
                request,
                institution_id=self.institution_2.id
            )

    def test_permission_admin_has_permission(self):
        request = RequestFactory().get(
            reverse(
                'institutional_storage_quota_control:institutional_storages',
                kwargs={'institution_id': self.institution_1.id}
            )
        )
        request.user = self.institution1_admin
        response = self.view(
            request,
            institution_id=self.institution_1.id
        )
        nt.assert_equal(response.status_code, 302)
