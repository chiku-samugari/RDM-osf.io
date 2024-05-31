import os
from django.core.urlresolvers import reverse
from django.db import connection
from django.http import HttpResponse, Http404
from django.shortcuts import redirect
from django.views.generic import ListView, View
from mimetypes import MimeTypes
from operator import itemgetter

from addons.osfstorage.models import Region
from admin.base import settings
from admin.institutions.views import QuotaUserStorageList
from admin.rdm.utils import RdmPermissionMixin
from admin.rdm_custom_storage_location import utils
from osf.models import Institution, OSFUser, UserStorageQuota
from django.contrib.auth.mixins import UserPassesTestMixin
from admin.base.utils import render_bad_request_response


class IconView(RdmPermissionMixin, UserPassesTestMixin, View):
    raise_exception = True

    def test_func(self):
        """check user permissions"""
        # login check
        if not self.is_authenticated:
            return False

        return self.is_super_admin or self.is_admin and \
            self.request.user.affiliated_institutions.exists()

    def get(self, request, *args, **kwargs):
        addon_name = kwargs['addon_name']
        addon = utils.get_addon_by_name(addon_name)
        if addon:
            # get addon's icon
            image_path = os.path.join('addons', addon_name, 'static', addon.icon)
            if os.path.exists(image_path):
                with open(image_path, 'rb') as f:
                    image_data = f.read()
                    content_type = MimeTypes().guess_type(addon.icon)[0]
                    return HttpResponse(image_data, content_type=content_type)
        raise Http404


class ProviderListByInstitution(RdmPermissionMixin, UserPassesTestMixin, ListView):
    paginate_by = 25
    template_name = 'institutional_storage_quota_control/list_provider_of_institution.html'
    raise_exception = True
    model = Institution
    allow_empty = False
    order_by = 'order_id'
    direction = 'desc'
    institution = None
    view_name = 'institutional_storages'

    def test_func(self):
        """check user permissions"""
        if self.request.resolver_match.url_name == self.view_name:
            institution_id = self.kwargs.get('institution_id')
            return self.has_auth(institution_id)
        else:
            # for only admin, url_name = 'affiliated_institutional_storages'
            return self.is_admin and self.request.user.affiliated_institutions.exists()

    def get_order_by(self):
        order_by = self.request.GET.get('order_by', 'order_id')
        if order_by not in ['provider', 'name']:
            return 'order_id'
        return order_by

    def get_direction(self):
        direction = self.request.GET.get('status', 'desc')
        if direction not in ['asc', 'desc']:
            return 'desc'
        return direction

    def get_institution(self):
        if self.request.resolver_match.url_name == self.view_name:
            institution_id = self.kwargs.get('institution_id')
            institution = Institution.objects.filter(id=institution_id).first()
        else:
            # for only admin, url_name = 'affiliated_institutional_storages'
            institution = self.request.user.affiliated_institutions.first()
        if institution is None:
            raise Http404
        return institution

    def get(self, request, *args, **kwargs):
        self.institution = self.get_institution()
        self.order_by = self.get_order_by()
        self.direction = self.get_direction()
        self.object_list = self.get_queryset()

        if len(self.object_list) == 1:
            return redirect(
                'institutional_storage_quota_control:institution_user_list',
                institution_id=self.institution.id, region_id=self.object_list[0]['region_id']
            )

        context = self.get_context_data()
        return self.render_to_response(context)

    def get_queryset(self):
        list_provider = []
        number_id = 0

        institution_id = self.institution.id
        institution_guid = self.institution._id
        list_region = Region.objects.filter(_id=institution_guid)

        for region in list_region:
            list_provider.append({
                'order_id': number_id,
                'region_id': region.id,
                'institution_id': institution_id,
                'name': region.name,
                'provider': region.provider_full_name,
                'icon_url_admin': reverse('institutional_storage_quota_control:icon',
                                          kwargs={
                                              'addon_name': region.provider_short_name,
                                              'icon_filename': 'comicon.png'
                                          }),
            })

        order_by = self.get_order_by()
        direction = self.direction != 'asc'
        list_provider.sort(key=itemgetter(order_by), reverse=direction)
        for provider in list_provider:
            number_id = number_id + 1
            provider['order_id'] = number_id
        return list_provider

    def get_context_data(self, **kwargs):
        # Handles pagination on object list by method of parent class
        kwargs['institution'] = self.institution
        kwargs['order_by'] = self.order_by
        kwargs['direction'] = self.direction
        return super(ProviderListByInstitution, self).get_context_data(**kwargs)


class InstitutionStorageList(RdmPermissionMixin, UserPassesTestMixin, ListView):
    paginate_by = 25
    template_name = 'institutional_storage_quota_control/list_institution_storage.html'
    ordering = 'name'
    raise_exception = True
    model = Institution

    def test_func(self):
        """check user permissions"""
        # login check
        if not self.is_authenticated:
            return False

        return self.is_super_admin or self.is_admin \
              and self.request.user.affiliated_institutions.exists()

    def merge_data(self, institutions):
        """ merge all institution storage names into the list of organization names

        :param list institutions: List of institution
        :return list: List of merged institution
        """
        _merged_inst = []
        for inst in institutions:
            # check institution is not merged
            if not [item for item in _merged_inst if item.institution_id == inst.institution_id]:
                # name attr to list of string
                inst.name = [inst.name]
                # add to merged list
                _merged_inst.append(inst)
            else:
                # get existing institution
                _inst = [item for item in _merged_inst if item.institution_id == inst.institution_id][0]
                _inst.name.append(inst.name)
        return _merged_inst

    def get(self, request, *args, **kwargs):
        count = 0
        query_set = self.get_queryset()
        self.object_list = query_set

        for item in query_set:
            if item.institution_id:
                count += 1
            else:
                self.object_list = self.object_list.exclude(id=item.id)

        ctx = self.get_context_data()
        return self.render_to_response(ctx)

    def get_queryset(self):
        if self.is_super_admin:
            query = ('select {} '
                     'from osf_institution '
                     'where addons_osfstorage_region._id = osf_institution._id')
            return Region.objects.extra(
                select={
                    'institution_id': query.format('id'),
                    'institution_name': query.format('name'),
                    'institution_logo_name': query.format('logo_name'),
                }
            ).order_by('institution_name', self.ordering)
        elif self.is_admin:
            user_id = self.request.user.id
            query = ('select {} '
                     'from osf_institution '
                     'where addons_osfstorage_region._id = _id '
                     'and id in ('
                     '    select institution_id '
                     '    from osf_osfuser_affiliated_institutions '
                     '    where osfuser_id = {}'
                     ')')
            return Region.objects.extra(
                select={
                    'institution_id': query.format('id', user_id),
                    'institution_name': query.format('name', user_id),
                    'institution_logo_name': query.format('logo_name', user_id),
                }
            )

    def get_context_data(self, **kwargs):
        object_list = self.merge_data(self.object_list)
        query_set = kwargs.pop('object_list', object_list)
        page_size = self.get_paginate_by(query_set)
        paginator, page, query_set, is_paginated = self.paginate_queryset(
            query_set,
            page_size
        )
        kwargs.setdefault('institutions', query_set)
        kwargs.setdefault('page', page)
        kwargs.setdefault('logohost', settings.OSF_URL)
        return super(InstitutionStorageList, self).get_context_data(**kwargs)


class UserListByInstitutionStorageID(RdmPermissionMixin, UserPassesTestMixin, QuotaUserStorageList):
    template_name = 'institutional_storage_quota_control/list_institute.html'
    raise_exception = True
    paginate_by = 25
    institution_id = None
    institution = None
    region_id = None
    region = None

    def test_func(self):
        """check user permissions"""
        # login check
        if not self.is_authenticated:
            return False

        # Get institution information
        self.institution_id = int(self.kwargs.get('institution_id'))
        self.institution = Institution.objects.filter(id=self.institution_id, is_deleted=False).first()
        if not self.institution:
            raise Http404(f'Institution with id "{self.institution_id}" not found. Please double check.')

        # Get region information
        self.region_id = int(self.kwargs.get('region_id'))
        self.region = Region.objects.filter(id=self.region_id).first()
        if not self.region:
            raise Http404(f'Region with id "{self.region_id}" not found. Please double check.')

        return self.institution._id == self.region._id and self.has_auth(self.institution_id)

    def get_institution(self):
        region = self.get_region()
        query = ('select name '
                 'from addons_osfstorage_region '
                 'where addons_osfstorage_region._id = osf_institution._id '
                 'and addons_osfstorage_region.id = {region_id}').format(region_id=region.id)
        institution = Institution.objects.filter(
            id=self.institution_id
        ).extra(
            select={
                'storage_name': query,
            }
        )
        return institution.first()

    def get_user_list(self):
        user_list = []
        for user in OSFUser.objects.filter(
                affiliated_institutions=self.institution_id
        ):
            user_list.append(self.get_user_storage_quota_info(user))
        return user_list

    def get_region(self):
        return self.region


class UpdateQuotaUserListByInstitutionStorageID(RdmPermissionMixin, UserPassesTestMixin, View):
    raise_exception = True
    institution_id = None
    institution = None

    def test_func(self):
        """check user permissions"""
        # login check
        if not self.is_authenticated:
            return False

        self.institution_id = int(self.kwargs.get('institution_id'))
        self.institution = Institution.objects.filter(id=self.institution_id, is_deleted=False).first()
        if not self.institution:
            raise Http404(f'Institution with id "{self.institution_id}" not found. Please double check.')
        return self.has_auth(self.institution_id)

    def post(self, request, *args, **kwargs):
        min_value, max_value = connection.ops.integer_field_range('IntegerField')
        region_id = self.request.POST.get('region_id', None)
        try:
            region = Region.objects.get(id=int(region_id))
        except (ValueError, TypeError):
            return render_bad_request_response(request, error_msgs='The region id must be a integer')
        except Region.DoesNotExist:
            raise Http404(f'Region with id "{region_id}" not found. Please double check.')

        if self.institution._id != region._id:
            return render_bad_request_response(request, error_msgs='The region not same institution')
        try:
            max_quota = min(int(self.request.POST.get('maxQuota')), max_value)
        except (ValueError, TypeError):
            return render_bad_request_response(request=request, error_msgs='maxQuota must be a integer')

        for user in OSFUser.objects.filter(
                affiliated_institutions=self.institution_id):
            UserStorageQuota.objects.update_or_create(
                user=user,
                region=region,
                defaults={'max_quota': max_quota}
            )

        return redirect(
            'institutional_storage_quota_control:institution_user_list',
            institution_id=self.institution_id, region_id=region_id
        )
