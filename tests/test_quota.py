# -*- coding: utf-8 -*-
import datetime
import mock
from nose.tools import *  # noqa (PEP8 asserts)
import pytest

from addons.osfstorage.models import OsfStorageFileNode
from api.base import settings as api_settings
from api.base.settings import NII_STORAGE_REGION_ID, ADDON_METHOD_PROVIDER
from api_tests.utils import create_test_file
from framework.auth import signing
from framework.exceptions import HTTPError
from tests.base import OsfTestCase
from osf.models import (
    FileLog, FileInfo, TrashedFileNode, TrashedFolder, UserQuota, ProjectStorageType, BaseFileNode,
    AbstractNode,
    UserStorageQuota,
)
from osf_tests.factories import (
    AuthUserFactory, ProjectFactory, UserFactory, InstitutionFactory, RegionFactory,
)
from tests.test_websitefiles import TestFolder, TestFile
from website.util import web_url_for, quota
from website.util.quota import get_region_id_of_institutional_storage_by_path


@pytest.mark.enable_implicit_clean
@pytest.mark.enable_quickfiles_creation
class TestQuotaProfileView(OsfTestCase):
    def setUp(self):
        super(TestQuotaProfileView, self).setUp()
        self.user = AuthUserFactory()
        self.quota_text = '{}%, {}[{}] / {}[GB]'

    def tearDown(self):
        super(TestQuotaProfileView, self).tearDown()

    @mock.patch('website.util.quota.used_quota')
    def test_default_quota(self, mock_usedquota):
        mock_usedquota.return_value = 0

        response = self.app.get(
            web_url_for('profile_view_id', uid=self.user._id),
            auth=self.user.auth
        )
        expected = self.quota_text.format(0.0, 0, 'B', api_settings.DEFAULT_MAX_QUOTA)
        assert_in(expected, response.body.decode())
        assert_in('Usage of NII storage', response.body.decode())

    def test_custom_quota(self):
        UserQuota.objects.create(
            storage_type=UserQuota.NII_STORAGE,
            user=self.user,
            max_quota=200,
            used=0
        )
        response = self.app.get(
            web_url_for('profile_view_id', uid=self.user._id),
            auth=self.user.auth
        )
        assert_in(self.quota_text.format(0.0, 0, 'B', 200), response.body.decode())
        assert_in('Usage of NII storage', response.body.decode())

    @mock.patch('website.util.quota.used_quota')
    def test_institution_default_quota(self, mock_usedquota):
        mock_usedquota.return_value = 0

        institution = InstitutionFactory()
        self.user.affiliated_institutions.add(institution)
        RegionFactory(_id=institution._id)

        response = self.app.get(
            web_url_for('profile_view_id', uid=self.user._id),
            auth=self.user.auth
        )
        expected = self.quota_text.format(0.0, 0, 'B', api_settings.DEFAULT_MAX_QUOTA)
        assert_in(expected, response.body.decode())
        assert_in('Usage of Institutional storage', response.body.decode())

    def test_institution_custom_quota(self):
        institution = InstitutionFactory()
        self.user.affiliated_institutions.add(institution)
        RegionFactory(_id=institution._id)

        UserQuota.objects.create(
            storage_type=UserQuota.CUSTOM_STORAGE,
            user=self.user,
            max_quota=200,
            used=100 * api_settings.SIZE_UNIT_GB
        )
        response = self.app.get(
            web_url_for('profile_view_id', uid=self.user._id),
            auth=self.user.auth
        )
        assert_in(self.quota_text.format(50.0, 100.0, 'GB', 200), response.body.decode())
        assert_in('Usage of Institutional storage', response.body.decode())

    def test_used_quota_bytes(self):
        UserQuota.objects.create(user=self.user, max_quota=100, used=560)
        response = self.app.get(
            web_url_for('profile_view_id', uid=self.user._id),
            auth=self.user.auth
        )
        assert_in(self.quota_text.format(0.0, 560, 'B', 100), response.body.decode())

    def test_used_quota_giga(self):
        UserQuota.objects.create(user=self.user, max_quota=100, used=5.2 * api_settings.SIZE_UNIT_GB)
        response = self.app.get(
            web_url_for('profile_view_id', uid=self.user._id),
            auth=self.user.auth
        )
        assert_in(self.quota_text.format(5.2, 5.2, 'GB', 100), response.body.decode())

    def test_used_quota_storage_icon_ok(self):
        UserQuota.objects.create(user=self.user, max_quota=100, used=0)
        response = self.app.get(
            web_url_for('profile_view_id', uid=self.user._id),
            auth=self.user.auth
        )
        assert_in('storage_ok.png', response.body.decode())

    def test_used_quota_storage_icon_warning(self):
        UserQuota.objects.create(user=self.user, max_quota=100, used=95 * api_settings.SIZE_UNIT_GB)
        response = self.app.get(
            web_url_for('profile_view_id', uid=self.user._id),
            auth=self.user.auth
        )
        assert_in('storage_warning.png', response.body.decode())

    def test_used_quota_storage_icon_error(self):
        UserQuota.objects.create(user=self.user, max_quota=100, used=105 * api_settings.SIZE_UNIT_GB)
        response = self.app.get(
            web_url_for('profile_view_id', uid=self.user._id),
            auth=self.user.auth
        )
        assert_in('storage_error.png', response.body.decode())


class TestAbbreviateSize(OsfTestCase):
    def setUp(self):
        super(TestAbbreviateSize, self).setUp()

    def tearDown(self):
        super(TestAbbreviateSize, self).tearDown()

    def test_abbreviate_byte(self):
        abbr_size = quota.abbreviate_size(512)
        assert_equal(abbr_size[0], 512)
        assert_equal(abbr_size[1], 'B')

    def test_abbreviate_kilobyte(self):
        abbr_size = quota.abbreviate_size(512 * api_settings.BASE_FOR_METRIC_PREFIX)
        assert_equal(abbr_size[0], 512)
        assert_equal(abbr_size[1], 'KB')

    def test_abbreviate_megabyte(self):
        abbr_size = quota.abbreviate_size(512 * api_settings.BASE_FOR_METRIC_PREFIX ** 2)
        assert_equal(abbr_size[0], 512)
        assert_equal(abbr_size[1], 'MB')

    def test_abbreviate_gigabyte(self):
        abbr_size = quota.abbreviate_size(512 * api_settings.BASE_FOR_METRIC_PREFIX ** 3)
        assert_equal(abbr_size[0], 512)
        assert_equal(abbr_size[1], 'GB')

    def test_abbreviate_terabyte(self):
        abbr_size = quota.abbreviate_size(512 * api_settings.BASE_FOR_METRIC_PREFIX ** 4)
        assert_equal(abbr_size[0], 512)
        assert_equal(abbr_size[1], 'TB')


class TestUsedQuota(OsfTestCase):
    def setUp(self):
        super(TestUsedQuota, self).setUp()
        self.user = UserFactory()
        self.node = [
            ProjectFactory(creator=self.user),
            ProjectFactory(creator=self.user)
        ]

    def tearDown(self):
        super(TestUsedQuota, self).tearDown()

    def test_calculate_used_quota(self):
        file_list = []

        # No files
        assert_equal(quota.used_quota(self.user._id, storage_type=UserQuota.NII_STORAGE), 0)
        assert_equal(quota.used_quota(self.user._id, storage_type=UserQuota.CUSTOM_STORAGE), 0)

        # Add a file to node[0]
        file_list.append(OsfStorageFileNode.create(
            target=self.node[0],
            name='file0'
        ))
        file_list[0].save()
        FileInfo.objects.create(file=file_list[0], file_size=500)
        assert_equal(quota.used_quota(self.user._id, storage_type=UserQuota.NII_STORAGE), 500)
        assert_equal(quota.used_quota(self.user._id, storage_type=UserQuota.CUSTOM_STORAGE), 0)

        # Add a file to node[1]
        file_list.append(OsfStorageFileNode.create(
            target=self.node[1],
            name='file1'
        ))
        file_list[1].save()
        FileInfo.objects.create(file=file_list[1], file_size=1000)

        assert_equal(quota.used_quota(self.user._id, storage_type=UserQuota.NII_STORAGE), 1500)
        assert_equal(quota.used_quota(self.user._id, storage_type=UserQuota.CUSTOM_STORAGE), 0)

    def test_calculate_used_quota_custom_storage(self):
        file_list = []

        institution = InstitutionFactory()
        self.user.affiliated_institutions.add(institution)
        RegionFactory(_id=institution._id)
        ProjectStorageType.objects.filter(node__in=[self.node[0], self.node[1]]).update(
            storage_type=ProjectStorageType.CUSTOM_STORAGE
        )

        # No files
        assert_equal(quota.used_quota(self.user._id, storage_type=UserQuota.NII_STORAGE), 0)
        assert_equal(quota.used_quota(self.user._id, storage_type=UserQuota.CUSTOM_STORAGE), 0)

        # Add a file to node[0]
        file_list.append(OsfStorageFileNode.create(
            target=self.node[0],
            name='file0'
        ))
        file_list[0].save()
        FileInfo.objects.create(file=file_list[0], file_size=500)
        assert_equal(quota.used_quota(self.user._id, storage_type=UserQuota.NII_STORAGE), 0)
        assert_equal(quota.used_quota(self.user._id, storage_type=UserQuota.CUSTOM_STORAGE), 500)

        # Add a file to node[1]
        file_list.append(OsfStorageFileNode.create(
            target=self.node[1],
            name='file1'
        ))
        file_list[1].save()
        FileInfo.objects.create(file=file_list[1], file_size=1000)

        assert_equal(quota.used_quota(self.user._id, storage_type=UserQuota.NII_STORAGE), 0)
        assert_equal(quota.used_quota(self.user._id, storage_type=UserQuota.CUSTOM_STORAGE), 1500)

    def test_calculate_used_quota_deleted_file(self):
        # Add a (deleted) file to node[0]
        file_node = OsfStorageFileNode.create(
            target=self.node[0],
            name='file0',
            deleted_on=datetime.datetime.now(),
            deleted_by=self.user
        )
        file_node.save()
        FileInfo.objects.create(file=file_node, file_size=500)

        assert_equal(quota.used_quota(self.user._id, storage_type=UserQuota.NII_STORAGE), 0)
        assert_equal(quota.used_quota(self.user._id, storage_type=UserQuota.CUSTOM_STORAGE), 0)


class TestUserStorageQuota(OsfTestCase):
    def setUp(self):
        super(TestUserStorageQuota, self).setUp()
        self.user = UserFactory()
        self.node = [
            ProjectFactory(creator=self.user),
            ProjectFactory(creator=self.user)
        ]
        ProjectStorageType.objects.filter(node=self.node[0]).update(storage_type=UserQuota.CUSTOM_STORAGE)
        ProjectStorageType.objects.filter(node=self.node[1]).update(storage_type=UserQuota.CUSTOM_STORAGE)
        file_1 = create_test_file(target=self.node[0], user=self.user)
        file_2 = create_test_file(target=self.node[1], user=self.user)
        FileInfo.objects.create(file=file_1, file_size=400)
        FileInfo.objects.create(file=file_2, file_size=500)

    def tearDown(self):
        super(TestUserStorageQuota, self).tearDown()

    def test_recalculate_used_quota_by_user(self):
        UserStorageQuota.objects.create(user=self.user, region_id=1)
        quota.recalculate_used_quota_by_user(self.user.id, storage_type=UserQuota.CUSTOM_STORAGE)
        user_storage_quota = UserStorageQuota.objects.get(user=self.user, region_id=1)
        assert_equal(user_storage_quota.used, 900)

    def test_recalculate_used_quota_by_user_not_found(self):
        res = quota.recalculate_used_quota_by_user(self.user.id, storage_type=UserQuota.CUSTOM_STORAGE)
        assert_is_none(res)

    def test_get_file_ids_by_institutional_storage(self):
        node = ProjectFactory(creator=self.user)
        files_ids = []
        res = quota.get_file_ids_by_institutional_storage(files_ids, node.id, None)
        assert_is_none(res)

    @mock.patch('website.util.quota.BaseFileNode.objects.filter')
    def test_get_file_ids_by_institutional_storage_not_found(self, mock_base_file_node):
        mock_base_file_node.return_value = None
        node = ProjectFactory(creator=self.user)
        files_ids = []
        res = quota.get_file_ids_by_institutional_storage(files_ids, node.id, '')
        assert_is_none(res)


class TestSaveFileInfo(OsfTestCase):
    def setUp(self):
        super(TestSaveFileInfo, self).setUp()
        self.user = UserFactory()
        self.project_creator = UserFactory()
        self.node = ProjectFactory(creator=self.project_creator)
        self.file = OsfStorageFileNode.create(
            target=self.node,
            path='/testfile',
            _id='testfile',
            name='testfile',
            materialized_path='/testfile'
        )
        self.file.save()
        self.storage_max_quota = api_settings.DEFAULT_MAX_QUOTA
        self.region = RegionFactory()

    def test_add_file_info(self):
        file_info_query = FileInfo.objects.filter(file=self.file)
        assert_false(file_info_query.exists())

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_ADDED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': '/' + self.file._id,
                    'kind': 'file',
                    'size': 1000,
                    'created_utc': '',
                    'modified_utc': '',
                    'extra': {'version': '1'}
                }
            }
        )

        file_info_list = FileInfo.objects.filter(file=self.file).all()
        assert_equal(file_info_list.count(), 1)
        file_info = file_info_list.first()
        assert_equal(file_info.file_size, 1000)

    @mock.patch('website.util.quota.get_project_storage_type')
    @mock.patch('website.util.quota.AbstractNode.objects.get')
    def test_file_move(self, mock_abstractnode, mock_storage_type):
        mock_storage_type.return_value = ProjectStorageType.CUSTOM_STORAGE
        mock_abstractnode.return_value = AbstractNode.objects.get(id=self.node.id)
        file_info_query = FileInfo.objects.filter(file=self.file)
        assert_false(file_info_query.exists())
        UserQuota.objects.create(user=self.project_creator, storage_type=UserQuota.CUSTOM_STORAGE, max_quota=200)
        res = quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_MOVED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': '/' + self.file._id,
                    'kind': 'file',
                    'size': 1000,
                    'created_utc': '',
                    'modified_utc': '',
                    'extra': {'version': '1'}
                },
                'destination': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'size': 1000,
                    'extra': {'version': '1'}
                },
                'source': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'size': 1000,
                    'extra': {'version': '1'},
                    'nid': self.node.id,
                    'old_root_id': '/'
                },
            }
        )
        assert_equal(res, None)

    @mock.patch('website.util.quota.get_project_storage_type')
    def test_file_move_with_size_less_than_zero(self, mock_storage_type):
        mock_storage_type.return_value = ProjectStorageType.CUSTOM_STORAGE
        file_info_query = FileInfo.objects.filter(file=self.file)
        assert_false(file_info_query.exists())

        res = quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_MOVED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': '/' + self.file._id,
                    'kind': 'file',
                    'size': 1000,
                    'created_utc': '',
                    'modified_utc': '',
                    'extra': {'version': '1'}
                },
                'destination': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'size': -1,
                    'extra': {'version': '1'}
                }
            }
        )

        assert_equal(res, None)

    @mock.patch('website.util.quota.get_project_storage_type')
    @mock.patch('website.util.quota.AbstractNode.objects.get')
    @mock.patch('osf.models.mixins.AddonModelMixin.get_addon')
    def test_get_addon_osfstorage_by_path_not_node_addon(self, mock_node_addon, mock_abstractnode, mock_storage_type):
        mock_node_addon.return_value = None
        mock_storage_type.return_value = ProjectStorageType.CUSTOM_STORAGE
        mock_abstractnode.return_value = AbstractNode.objects.get(id=self.node.id)
        file_info_query = FileInfo.objects.filter(file=self.file)
        assert_false(file_info_query.exists())
        UserQuota.objects.create(user=self.project_creator, storage_type=UserQuota.CUSTOM_STORAGE, max_quota=200)
        with pytest.raises(HTTPError) as e:
            quota.update_used_quota(
                self=None,
                target=self.node,
                user=self.user,
                event_type=FileLog.FILE_MOVED,
                payload={
                    'provider': 'osfstorage',
                    'metadata': {
                        'provider': 'osfstorage',
                        'name': 'testfile',
                        'materialized': '/filename',
                        'path': '/' + self.file._id,
                        'kind': 'file',
                        'size': 1000,
                        'created_utc': '',
                        'modified_utc': '',
                        'extra': {'version': '1'}
                    },
                    'destination': {
                        'provider': 'osfstorage',
                        'name': 'testfile',
                        'materialized': '/filename',
                        'path': self.file._id,
                        'kind': 'file',
                        'size': 1000,
                        'extra': {'version': '1'}
                    },
                    'source': {
                        'provider': 'osfstorage',
                        'name': 'testfile',
                        'materialized': '/filename',
                        'path': self.file._id,
                        'kind': 'file',
                        'size': 1000,
                        'extra': {'version': '1'},
                        'nid': self.node.id,
                        'old_root_id': '/'
                    },
                }
            )

        assert e.value.code == 400

    @mock.patch('website.util.quota.get_project_storage_type')
    @mock.patch('website.util.quota.AbstractNode.objects.get')
    @mock.patch('website.util.quota.get_root_institutional_storage')
    def test_get_addon_osfstorage_by_path_root_folder_id_none(self, mock_root_id, mock_abstractnode, mock_storage_type):
        parent = TestFolder(
            _path='aparent',
            name='parent',
            target=self.node,
            provider='osf_storage',
            materialized_path='/long/path/to/name',
            is_root=True,
        )
        parent.save()
        file_child = TestFile(
            _path='afile',
            name='child',
            target=self.node,
            parent_id=parent.id,
            provider='osf_storage',
            materialized_path='/long/path/to/name',
        )
        file_child.save()
        mock_root_id.return_value = file_child
        mock_storage_type.return_value = ProjectStorageType.CUSTOM_STORAGE
        mock_abstractnode.return_value = AbstractNode.objects.get(id=self.node.id)
        file_info_query = FileInfo.objects.filter(file=self.file)
        assert_false(file_info_query.exists())
        UserQuota.objects.create(user=self.project_creator, storage_type=UserQuota.CUSTOM_STORAGE, max_quota=200)
        res = quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_MOVED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': '/' + self.file._id,
                    'kind': 'file',
                    'size': 1000,
                    'created_utc': '',
                    'modified_utc': '',
                    'extra': {'version': '1'}
                },
                'destination': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'size': 1000,
                    'extra': {'version': '1'}
                },
                'source': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'size': 1000,
                    'extra': {'version': '1'},
                    'nid': self.node.id,
                    'old_root_id': '/'
                },
            }
        )
        assert_equal(res, None)

    def test_update_institutional_storage_used_quota(self):
        UserStorageQuota.objects.create(user=self.project_creator, region=self.region, max_quota=self.storage_max_quota,
                                        used=1000)
        quota.update_institutional_storage_used_quota(self.project_creator, self.region, 2000, True)
        user_storage_quota = UserStorageQuota.objects.filter(user=self.project_creator, region=self.region).first()

        assert_is_not_none(user_storage_quota)
        assert_equal(user_storage_quota.used, 3000)

    def test_update_institutional_storage_used_quota_used_less_than_zero(self):
        UserStorageQuota.objects.create(
            user=self.project_creator,
            region=self.region,
            max_quota=self.storage_max_quota,
            used=-1
        )
        quota.update_institutional_storage_used_quota(self.project_creator, self.region, -1, True)
        user_storage_quota = UserStorageQuota.objects.filter(user=self.project_creator, region=self.region).first()

        assert_is_not_none(user_storage_quota)
        assert_equal(user_storage_quota.used, 0)

    def test_update_file_info(self):
        file_info = FileInfo(file=self.file, file_size=1000)
        file_info.save()

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_UPDATED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'size': 2500,
                    'created_utc': '',
                    'modified_utc': '',
                    'extra': {'version': '2'}
                }
            }
        )

        file_info = FileInfo.objects.get(file=self.file)
        assert_equal(file_info.file_size, 2500)

    def test_file_info_when_not_osfstorage(self):
        file_info_query = FileInfo.objects.filter(file=self.file)
        assert_false(file_info_query.exists())

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_ADDED,
            payload={
                'provider': 'github',
                'metadata': {
                    'provider': 'github',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': '/' + self.file._id,
                    'kind': 'file',
                    'size': 1000,
                    'created_utc': '',
                    'modified_utc': '',
                    'extra': {'version': '1'}
                }
            }
        )

        assert_false(file_info_query.exists())


class TestSaveUsedQuota(OsfTestCase):
    def __init__(self, method_name: str = ...):
        super().__init__(method_name)
        self.addon_provider = ADDON_METHOD_PROVIDER[0]

    def setUp(self):
        super(TestSaveUsedQuota, self).setUp()
        self.user = UserFactory()
        self.project_creator = UserFactory()
        self.node = ProjectFactory(creator=self.project_creator)
        self.node_root = TestFolder(
            target=self.node,
            type='osf.osfstoragefolder',
            provider='osf_storage',
            name='root',
            path='/root',
            materialized_path='/long/path/to/name',
            is_root=True,
        )
        self.node_root.save()
        self.file = OsfStorageFileNode.create(
            target=self.node,
            parent_id=self.node_root.id,
            provider='osf_storage',
            name='osfstoragefile',
            path='/osfstoragefile',
            materialized_path='/osfstoragefile'
        )
        self.file.save()

        self.base_folder_node = TestFolder.create(
            target=self.node,
            parent_id=self.node_root.id,
            provider=self.addon_provider,
            type=f'osf.{self.addon_provider}folder',
            name=f'{self.addon_provider}folder',
            path=f'/{self.addon_provider}folder',
            materialized_path=f'/{self.addon_provider}folder',
        )
        self.base_file_node = TestFile.create(
            target=self.node,
            parent_id=self.node_root.id,
            provider=self.addon_provider,
            type=f'osf.{self.addon_provider}file',
            name=f'{self.addon_provider}file',
            path=f'/{self.addon_provider}file',
            materialized_path=f'/{self.addon_provider}file',
        )

    def test_update_default_storage(self):
        user = self.user
        institution = InstitutionFactory()
        user.affiliated_institutions.add(institution)
        RegionFactory(_id=institution._id)
        res = quota.update_default_storage(user)
        assert_equal(res, None)

    def test_update_default_storage_no_region(self):
        user = self.user
        institution = InstitutionFactory()
        user.affiliated_institutions.add(institution)
        res = quota.update_default_storage(user)
        assert_equal(res, None)

    def test_add_first_file(self):
        assert_false(UserStorageQuota.objects.filter(
            user=self.project_creator
        ).exists())

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_ADDED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': '/' + self.file._id,
                    'kind': 'file',
                    'size': 1000,
                    'created_utc': '',
                    'modified_utc': '',
                    'extra': {'version': '1'}
                }
            }
        )

        user_quota = UserStorageQuota.objects.filter(
            region_id=1,
            user=self.project_creator
        ).all()
        assert_equal(len(user_quota), 1)
        user_quota = user_quota[0]
        assert_equal(user_quota.used, 1000)

    def test_add_first_file_custom_storage(self):
        assert_false(UserStorageQuota.objects.filter(
            user=self.project_creator
        ).exists())

        institution = InstitutionFactory()
        self.user.affiliated_institutions.add(institution)
        self.region = RegionFactory(_id=institution._id)
        addon_st = self.node.add_addon('osfstorage', auth=None, log=False, region_id=self.region.id)
        addon_st.root_node_id = self.node_root.id
        addon_st.save()

        ProjectStorageType.objects.filter(node=self.node).update(
            storage_type=ProjectStorageType.CUSTOM_STORAGE
        )

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_ADDED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': '/' + self.file._id,
                    'kind': 'file',
                    'size': 1200,
                    'created_utc': '',
                    'modified_utc': '',
                    'extra': {'version': '1'}
                }
            }
        )

        user_quota = UserStorageQuota.objects.filter(
            region=self.region,
            user=self.project_creator
        ).all()
        assert_equal(len(user_quota), 1)
        user_quota = user_quota[0]
        assert_equal(user_quota.used, 1200)

    def test_add_file(self):
        UserStorageQuota.objects.create(
            user=self.project_creator,
            region_id=1,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=5500
        )

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_ADDED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'size': 1000,
                    'created_utc': '',
                    'modified_utc': '',
                    'extra': {'version': '1'}
                }
            }
        )

        user_quota = UserStorageQuota.objects.filter(
            region_id=1,
            user=self.project_creator
        ).all()
        assert_equal(len(user_quota), 1)
        user_quota = user_quota[0]
        assert_equal(user_quota.used, 6500)

    def test_add_file_custom_storage(self):
        institution = InstitutionFactory()
        self.user.affiliated_institutions.add(institution)
        self.region = RegionFactory(_id=institution._id)
        addon_st = self.node.add_addon('osfstorage', auth=None, log=False, region_id=self.region.id)
        addon_st.root_node_id = self.node_root.id
        addon_st.save()

        ProjectStorageType.objects.filter(node=self.node).update(
            storage_type=ProjectStorageType.CUSTOM_STORAGE
        )

        UserStorageQuota.objects.create(
            user=self.project_creator,
            region=self.region,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=5500
        )

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_ADDED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'size': 1200,
                    'created_utc': '',
                    'modified_utc': '',
                    'extra': {'version': '1'}
                }
            }
        )

        user_quota = UserStorageQuota.objects.filter(
            region=self.region,
            user=self.project_creator
        ).all()
        assert_equal(len(user_quota), 1)
        user_quota = user_quota[0]
        assert_equal(user_quota.used, 6700)

    def test_add_file_negative_size(self):
        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_ADDED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'size': -1000,
                    'created_utc': '',
                    'modified_utc': '',
                    'extra': {'version': '1'}
                }
            }
        )
        assert_false(UserStorageQuota.objects.filter(
            region_id=1,
            user=self.project_creator
        ).exists())

    def test_delete_file(self):
        UserStorageQuota.objects.create(
            user=self.project_creator,
            region_id=1,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=5500
        )
        FileInfo.objects.create(file=self.file, file_size=1000)

        self.file.deleted_on = datetime.datetime.now()
        self.file.deleted_by = self.user
        self.file.type = 'osf.trashedfile'
        self.file.save()

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_REMOVED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'extra': {}
                }
            }
        )

        user_quota = UserStorageQuota.objects.get(
            region_id=1,
            user=self.project_creator
        )
        assert_equal(user_quota.used, 4500)

    def test_delete_file_custom_storage(self):
        institution = InstitutionFactory()
        self.user.affiliated_institutions.add(institution)
        self.region = RegionFactory(_id=institution._id)
        addon_st = self.node.add_addon('osfstorage', auth=None, log=False, region_id=self.region.id)
        addon_st.root_node_id = self.node_root.id
        addon_st.save()

        ProjectStorageType.objects.filter(node=self.node).update(
            storage_type=ProjectStorageType.CUSTOM_STORAGE
        )

        UserStorageQuota.objects.create(
            user=self.project_creator,
            region=self.region,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=5500
        )
        FileInfo.objects.create(file=self.file, file_size=1200)

        self.file.deleted_on = datetime.datetime.now()
        self.file.deleted_by = self.user
        self.file.type = 'osf.trashedfile'
        self.file.save()

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_REMOVED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'extra': {}
                }
            }
        )

        user_quota = UserStorageQuota.objects.get(
            region=self.region,
            user=self.project_creator
        )
        assert_equal(user_quota.used, 4300)

    def test_delete_file_lower_used_quota(self):
        UserStorageQuota.objects.create(
            user=self.project_creator,
            region_id=1,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=500
        )
        FileInfo.objects.create(file=self.file, file_size=1000)

        self.file.deleted_on = datetime.datetime.now()
        self.file.deleted_by = self.user
        self.file.type = 'osf.trashedfile'
        self.file.save()

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_REMOVED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'extra': {}
                }
            }
        )

        user_quota = UserStorageQuota.objects.get(
            region_id=1,
            user=self.project_creator
        )
        assert_equal(user_quota.used, 0)

    @mock.patch('website.util.quota.logger')
    def test_delete_file_invalid_file(self, mock_logger):
        UserStorageQuota.objects.create(
            user=self.project_creator,
            region_id=1,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=5500
        )

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_REMOVED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': 'malicioususereditedthis',
                    'kind': 'file',
                    'extra': {}
                }
            }
        )

        user_quota = UserStorageQuota.objects.get(
            region_id=1,
            user=self.project_creator
        )
        assert_equal(user_quota.used, 5500)
        mock_logger.warning.assert_called_with('BaseFileNode not found, cannot update used quota!')

    @mock.patch('website.util.quota.logging')
    def test_delete_file_without_fileinfo(self, mock_logging):
        UserStorageQuota.objects.create(
            user=self.project_creator,
            region_id=1,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=5500
        )

        self.file.deleted_on = datetime.datetime.now()
        self.file.deleted_by = self.user
        self.file.type = 'osf.trashedfile'
        self.file.save()

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_REMOVED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'extra': {}
                }
            }
        )

        user_quota = UserStorageQuota.objects.get(
            region_id=1,
            user=self.project_creator
        )
        assert_equal(user_quota.used, 5500)
        mock_logging.error.assert_called_with('FileInfo not found, cannot update used quota!')

    @mock.patch('website.util.quota.logging')
    def test_delete_file_not_trashed(self, mock_logging):
        UserStorageQuota.objects.create(
            user=self.project_creator,
            region_id=1,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=5500
        )
        FileInfo.objects.create(file=self.file, file_size=1000)

        self.file.deleted_on = datetime.datetime.now()
        self.file.deleted_by = self.user
        self.file.save()

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_REMOVED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'extra': {}
                }
            }
        )

        user_quota = UserStorageQuota.objects.get(
            region_id=1,
            user=self.project_creator
        )
        assert_equal(user_quota.used, 5500)
        mock_logging.error.assert_called_with('FileNode is not trashed, cannot update used quota!')

    def test_delete_file_without_user_storage_quota(self):
        FileInfo.objects.create(file=self.file, file_size=1000)

        self.file.deleted_on = datetime.datetime.now()
        self.file.deleted_by = self.user
        self.file.type = 'osf.trashedfile'
        self.file.save()

        assert_false(UserStorageQuota.objects.filter(
            region_id=1,
            user=self.project_creator
        ).exists())

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_REMOVED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'extra': {}
                }
            }
        )

        assert_true(UserStorageQuota.objects.filter(
            region_id=1,
            user=self.project_creator
        ).exists())

    def test_delete_folder(self):
        UserStorageQuota.objects.create(
            user=self.project_creator,
            region_id=1,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=5500
        )

        folder1 = TrashedFolder(
            target=self.node,
            name='testfolder',
            deleted_on=datetime.datetime.now(),
            deleted_by=self.user
        )
        folder1.save()
        folder2 = TrashedFolder(
            target=self.node,
            name='testfolder',
            parent_id=folder1.id,
            deleted_on=datetime.datetime.now(),
            deleted_by=self.user
        )
        folder2.save()
        file1 = TrashedFileNode.create(
            target=self.node,
            name='testfile1',
            parent_id=folder1.id,
            deleted_on=datetime.datetime.now(),
            deleted_by=self.user
        )
        file1.provider = 'osfstorage'
        file1.save()
        file2 = TrashedFileNode.create(
            target=self.node,
            name='testfile2',
            parent_id=folder2.id,
            deleted_on=datetime.datetime.now(),
            deleted_by=self.user
        )
        file2.provider = 'osfstorage'
        file2.save()

        file1_info = FileInfo(file=file1, file_size=2000)
        file1_info.save()
        file2_info = FileInfo(file=file2, file_size=3000)
        file2_info.save()

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_REMOVED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfolder',
                    'materialized': '/testfolder',
                    'path': '{}/'.format(folder1._id),
                    'kind': 'folder',
                    'extra': {}
                }
            }
        )

        user_quota = UserStorageQuota.objects.get(
            region_id=1,
            user=self.project_creator
        )
        assert_equal(user_quota.used, 500)

    def test_delete_folder_custom_storage(self):
        institution = InstitutionFactory()
        self.user.affiliated_institutions.add(institution)
        self.region = RegionFactory(_id=institution._id)
        addon_st = self.node.add_addon('osfstorage', auth=None, log=False, region_id=self.region.id)
        addon_st.root_node_id = self.node_root.id
        addon_st.save()

        ProjectStorageType.objects.filter(node=self.node).update(
            storage_type=ProjectStorageType.CUSTOM_STORAGE
        )

        UserStorageQuota.objects.create(
            user=self.project_creator,
            region=self.region,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=5500
        )

        folder1 = TrashedFolder(
            target=self.node,
            name='testfolder',
            parent_id=self.node_root.id,
            deleted_on=datetime.datetime.now(),
            deleted_by=self.user
        )
        folder1.save()
        folder2 = TrashedFolder(
            target=self.node,
            name='testfolder',
            parent_id=folder1.id,
            deleted_on=datetime.datetime.now(),
            deleted_by=self.user
        )
        folder2.save()
        file1 = TrashedFileNode.create(
            target=self.node,
            name='testfile1',
            parent_id=folder1.id,
            deleted_on=datetime.datetime.now(),
            deleted_by=self.user
        )
        file1.provider = 'osfstorage'
        file1.save()
        file2 = TrashedFileNode.create(
            target=self.node,
            name='testfile2',
            parent_id=folder2.id,
            deleted_on=datetime.datetime.now(),
            deleted_by=self.user
        )
        file2.provider = 'osfstorage'
        file2.save()

        file1_info = FileInfo(file=file1, file_size=2000)
        file1_info.save()
        file2_info = FileInfo(file=file2, file_size=3000)
        file2_info.save()

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_REMOVED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfolder',
                    'materialized': '/testfolder',
                    'path': '{}/'.format(folder1._id),
                    'kind': 'folder',
                    'extra': {}
                }
            }
        )

        user_quota_quota = UserStorageQuota.objects.get(
            region=self.region,
            user=self.project_creator
        )
        assert_equal(user_quota_quota.used, 500)

    def test_edit_file(self):
        UserStorageQuota.objects.create(
            user=self.project_creator,
            region_id=1,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=5500
        )
        FileInfo.objects.create(file=self.file, file_size=1000)

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_UPDATED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'size': 1500,
                    'created_utc': '',
                    'modified_utc': '',
                    'extra': {'version': '2'}
                }
            }
        )

        user_quota = UserStorageQuota.objects.get(
            region_id=1,
            user=self.project_creator
        )
        assert_equal(user_quota.used, 6000)

    def test_edit_file_custom_storage(self):
        institution = InstitutionFactory()
        self.user.affiliated_institutions.add(institution)
        self.region = RegionFactory(_id=institution._id)
        addon_st = self.node.add_addon('osfstorage', auth=None, log=False, region_id=self.region.id)
        addon_st.root_node_id = self.node_root.id
        addon_st.save()

        ProjectStorageType.objects.filter(node=self.node).update(
            storage_type=ProjectStorageType.CUSTOM_STORAGE
        )

        UserStorageQuota.objects.create(
            user=self.project_creator,
            region=self.region,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=5500
        )
        FileInfo.objects.create(file=self.file, file_size=1000)

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_UPDATED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'size': 1700,
                    'created_utc': '',
                    'modified_utc': '',
                    'extra': {'version': '2'}
                }
            }
        )

        user_quota = UserStorageQuota.objects.get(
            region=self.region,
            user=self.project_creator
        )
        assert_equal(user_quota.used, 6200)

    def test_edit_file_negative_size(self):
        UserStorageQuota.objects.create(
            user=self.project_creator,
            region_id=1,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=5500
        )
        FileInfo.objects.create(file=self.file, file_size=1000)

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_UPDATED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'size': -1500,
                    'created_utc': '',
                    'modified_utc': '',
                    'extra': {'version': '2'}
                }
            }
        )

        user_quota = UserStorageQuota.objects.get(
            region_id=1,
            user=self.project_creator
        )
        assert_equal(user_quota.used, 5500)

    def test_edit_file_without_fileinfo(self):
        UserStorageQuota.objects.create(
            user=self.project_creator,
            region_id=1,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=5500
        )

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_UPDATED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'size': 1500,
                    'created_utc': '',
                    'modified_utc': '',
                    'extra': {'version': '2'}
                }
            }
        )

        user_quota = UserStorageQuota.objects.get(
            region_id=1,
            user=self.project_creator
        )
        assert_equal(user_quota.used, 7000)

    def test_edit_file_lower_used_quota(self):
        UserStorageQuota.objects.create(
            user=self.project_creator,
            region_id=1,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=500
        )
        FileInfo.objects.create(file=self.file, file_size=3000)

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_UPDATED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'size': 2000,
                    'created_utc': '',
                    'modified_utc': '',
                    'extra': {'version': '2'}
                }
            }
        )

        user_quota = UserStorageQuota.objects.get(
            region_id=1,
            user=self.project_creator
        )
        assert_equal(user_quota.used, 0)

    def test_add_file_when_not_osfstorage(self):
        UserStorageQuota.objects.create(
            user=self.project_creator,
            region_id=1,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=5500
        )

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_ADDED,
            payload={
                'provider': 'github',
                'metadata': {
                    'provider': 'github',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'size': 1000,
                    'created_utc': '',
                    'modified_utc': '',
                    'extra': {'version': '1'}
                }
            }
        )

        user_quota = UserStorageQuota.objects.get(
            region_id=1,
            user=self.project_creator
        )
        assert_equal(user_quota.used, 5500)

    def test_move_file(self):
        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_ADDED,
            payload={
                'metadata': {
                    'created_utc': '',
                    'modified_utc': '',
                    'extra': {'version': '1'}
                },
                'source': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'size': 1000,
                    'extra': {'version': '1'}
                },
                'destination': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'size': 1000,
                    'extra': {'version': '1'}
                }
            }
        )

    def test_rename_folder_with_addon_method_provider(self):
        mock_base_file_node = mock.MagicMock()
        mock_base_file_node_orderby = mock.MagicMock()
        mock_base_file_node.objects.filter.return_value = [
            BaseFileNode(
                type=f'osf.{self.addon_provider}folder',
                provider=self.addon_provider,
                _path='/newfoldername',
                _materialized_path='/newfoldername',
                target_object_id=self.node.id,
                target_content_type_id=2
            )
        ]
        mock_base_file_node_orderby.filter.return_value.order_by.return_value.first.return_value = BaseFileNode(
            type=f'osf.{self.addon_provider}folder',
            provider=self.addon_provider,
            _path='/newfoldername',
            _materialized_path='/newfoldername',
            target_object_id=self.node.id,
            target_content_type_id=2
        )

        with mock.patch('website.util.quota.BaseFileNode', mock_base_file_node):
            with mock.patch('website.util.quota.BaseFileNode', mock_base_file_node_orderby):
                quota.update_used_quota(
                    self=None,
                    target=self.node,
                    user=self.user,
                    event_type=FileLog.FILE_RENAMED,
                    payload={
                        'destination': {
                            'provider': self.addon_provider,
                            'path': '/newfoldername',
                            'kind': 'folder',
                        },
                        'source': {
                            'provider': self.addon_provider,
                            'path': '/prefolderename',
                            'kind': 'folder',
                        },
                    }
                )

    def test_rename_file_with_addon_method_provider(self):
        mock_base_file_node = mock.MagicMock()
        mock_base_file_node_orderby = mock.MagicMock()
        mock_base_file_node.objects.filter.return_value = [
            BaseFileNode(
                type=f'osf.{self.addon_provider}file',
                provider=self.addon_provider,
                _path='/newfilename',
                _materialized_path='/newfilename',
                target_object_id=self.node.id,
                target_content_type_id=2
            )
        ]
        mock_base_file_node_orderby.filter.return_value.order_by.return_value.first.return_value = BaseFileNode(
            type=f'osf.{self.addon_provider}file',
            provider=self.addon_provider,
            _path='/newfilename',
            _materialized_path='/newfilename',
            target_object_id=self.node.id,
            target_content_type_id=2
        )

        with mock.patch('website.util.quota.BaseFileNode', mock_base_file_node):
            with mock.patch('website.util.quota.BaseFileNode', mock_base_file_node_orderby):
                quota.update_used_quota(
                    self=None,
                    target=self.node,
                    user=self.user,
                    event_type=FileLog.FILE_RENAMED,
                    payload={
                        'destination': {
                            'provider': self.addon_provider,
                            'path': '/newfilename',
                            'kind': 'file',
                        },
                        'source': {
                            'provider': self.addon_provider,
                            'path': '/prefilename',
                            'kind': 'file',
                        },
                    }
                )

    def test_add_file_with_addon_method_provider(self):
        institution = InstitutionFactory()
        self.project_creator.affiliated_institutions.add(institution)
        self.region = RegionFactory(
            _id=institution._id,
            waterbutler_settings={
                'storage': {
                    'bucket': 'grdm-system-test',
                    'folder': '',
                    'provider': self.addon_provider,
                    'encrypt_uploads': False
                }
            }
        )
        addon_st = self.node.add_addon('nextcloudinstitutions', auth=None, log=False, region_id=self.region.id)
        addon_st.root_node_id = self.node_root.id
        addon_st.save()

        ProjectStorageType.objects.filter(node=self.node).update(
            storage_type=ProjectStorageType.CUSTOM_STORAGE
        )

        UserStorageQuota.objects.create(
            user=self.project_creator,
            region=self.region,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=5000
        )
        self.base_file_node._path = '/' + self.node_root._id + self.base_file_node.materialized_path
        self.base_file_node.parent_id = self.node_root.id
        self.base_file_node.save()
        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.project_creator,
            event_type=FileLog.FILE_ADDED,
            payload={
                'provider': self.addon_provider,
                'root_path': self.node_root._id,
                'metadata': {
                    'provider': self.addon_provider,
                    'name': self.base_file_node.name,
                    'materialized': self.base_file_node.materialized_path,
                    'path': '/' + self.node_root._id + self.base_file_node.materialized_path,
                    'kind': 'file',
                    'size': 1000,
                    'created_utc': '',
                    'modified_utc': '',
                    'extra': {'version': '1'},
                }
            }
        )

        user_quota = UserStorageQuota.objects.filter(
            region=self.region,
            user=self.project_creator
        ).all()
        assert_equal(len(user_quota), 1)
        user_quota = user_quota[0]
        assert_equal(user_quota.used, 6000)

    def test_add_folder_with_addon_method_provider(self):
        institution = InstitutionFactory()
        self.project_creator.affiliated_institutions.add(institution)
        self.user.affiliated_institutions.add(institution)
        self.region = RegionFactory(
            _id=institution._id,
            waterbutler_settings={
                'storage': {
                    'bucket': 'grdm-system-test',
                    'folder': '',
                    'provider': self.addon_provider,
                    'encrypt_uploads': False
                }
            }
        )
        addon_st = self.node.add_addon('osfstorage', auth=None, log=False, region_id=self.region.id)
        addon_st.root_node_id = self.node_root.id
        addon_st.save()

        ProjectStorageType.objects.filter(node=self.node).update(
            storage_type=ProjectStorageType.CUSTOM_STORAGE
        )

        UserStorageQuota.objects.create(
            user=self.project_creator,
            region=self.region,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=5000
        )

        self.base_folder_node.save()

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_ADDED,
            payload={
                'provider': self.addon_provider,
                'action': 'create_folder',
                'metadata': {
                    'provider': self.addon_provider,
                    'name': self.base_folder_node.name,
                    'materialized': self.base_folder_node.materialized_path,
                    'path': self.base_folder_node.materialized_path,
                    'kind': 'folder',
                    'size': 0,
                    'created_utc': '',
                    'modified_utc': '',
                }
            }
        )

        user_quota = UserStorageQuota.objects.filter(
            region=self.region,
            user=self.project_creator
        ).all()
        assert_equal(len(user_quota), 1)
        user_quota = user_quota[0]
        assert_equal(user_quota.used, 5000)

    def test_delete_file_with_addon_method_provider(self):
        institution = InstitutionFactory()
        self.project_creator.affiliated_institutions.add(institution)
        self.user.affiliated_institutions.add(institution)
        self.region = RegionFactory(
            _id=institution._id,
            waterbutler_settings={
                'storage': {
                    'bucket': 'grdm-system-test',
                    'folder': '',
                    'provider': self.addon_provider,
                    'encrypt_uploads': False
                }
            }
        )
        addon_st = self.node.add_addon('nextcloudinstitutions', auth=None, log=False, region_id=self.region.id)
        addon_st.root_node_id = self.node_root.id
        addon_st.save()

        ProjectStorageType.objects.filter(node=self.node).update(
            storage_type=ProjectStorageType.CUSTOM_STORAGE
        )

        self.base_file_node._path = '/' + self.node_root._id + self.base_file_node.materialized_path
        self.base_file_node.parent_id = self.node_root.id
        self.base_file_node.save()
        FileInfo.objects.create(file=self.base_file_node, file_size=1000)

        UserStorageQuota.objects.create(
            user=self.project_creator,
            region=self.region,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=5500
        )

        self.base_file_node.deleted_on = datetime.datetime.now()
        self.base_file_node.deleted_by = self.user
        self.base_file_node.type = 'osf.trashedfile'
        self.base_file_node.save()

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_REMOVED,
            payload={
                'provider': self.addon_provider,
                'root_path': self.node_root._id,
                'metadata': {
                    'provider': self.addon_provider,
                    'name': self.base_file_node.name,
                    'materialized': self.base_file_node.materialized_path,
                    'path': self.base_file_node.materialized_path,
                    'kind': 'file',
                }
            }
        )
        user_quota = UserStorageQuota.objects.get(
            region=self.region,
            user=self.project_creator
        )
        assert_equal(user_quota.used, 4500)

    def test_delete_folder_with_addon_method_provider(self):
        institution = InstitutionFactory()
        self.project_creator.affiliated_institutions.add(institution)
        self.user.affiliated_institutions.add(institution)
        self.region = RegionFactory(
            _id=institution._id,
            waterbutler_settings={
                'storage': {
                    'bucket': 'grdm-system-test',
                    'folder': '',
                    'provider': self.addon_provider,
                    'encrypt_uploads': False
                }
            }
        )
        addon_st = self.node.add_addon('osfstorage', auth=None, log=False, region_id=self.region.id)
        addon_st.root_node_id = self.node_root.id
        addon_st.save()

        ProjectStorageType.objects.filter(node=self.node).update(
            storage_type=ProjectStorageType.CUSTOM_STORAGE
        )

        UserStorageQuota.objects.create(
            user=self.project_creator,
            region=self.region,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=5500
        )

        folder1 = TrashedFolder(
            target=self.node,
            parent_id=self.node_root.id,
            provider=self.addon_provider,
            name=f'{self.addon_provider}folder1',
            path=f'/{self.addon_provider}folder1',
            materialized_path=f'/{self.addon_provider}folder1',
            deleted_on=datetime.datetime.now(),
            deleted_by=self.user
        )
        folder1.save()
        folder2 = TrashedFolder(
            target=self.node,
            parent_id=folder1.id,
            provider=self.addon_provider,
            name=f'{self.addon_provider}folder2',
            path=f'/{self.addon_provider}folder1/{self.addon_provider}folder2',
            materialized_path=f'/{self.addon_provider}folder1/{self.addon_provider}folder2',
            deleted_on=datetime.datetime.now(),
            deleted_by=self.user
        )
        folder2.save()
        file1 = TrashedFileNode.create(
            target=self.node,
            parent_id=folder1.id,
            name=f'{self.addon_provider}file1',
            path=f'/{self.addon_provider}folder1/{self.addon_provider}file1',
            materialized_path=f'/{self.addon_provider}folder1/{self.addon_provider}file1',
            deleted_on=datetime.datetime.now(),
            deleted_by=self.user
        )
        file1.provider = self.addon_provider
        file1.type = 'osf.trashedfile'
        file1.save()
        file2 = TrashedFileNode.create(
            target=self.node,
            parent_id=folder2.id,
            name=f'{self.addon_provider}file2',
            path=f'/{self.addon_provider}folder1/{self.addon_provider}folder2/{self.addon_provider}file2',
            materialized_path=f'/{self.addon_provider}folder1/{self.addon_provider}folder2/{self.addon_provider}file2',
            deleted_on=datetime.datetime.now(),
            deleted_by=self.user
        )
        file2.provider = self.addon_provider
        file2.type = 'osf.trashedfile'
        file2.save()

        file1_info = FileInfo(file=file1, file_size=2000)
        file1_info.save()
        file2_info = FileInfo(file=file2, file_size=3000)
        file2_info.save()

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_REMOVED,
            payload={
                'provider': 'osfstorage',
                'root_path': folder1._id,
                'metadata': {
                    'provider': 'osfstorage',
                    'name': folder1.name,
                    'materialized': folder1.materialized_path,
                    'path': folder1._id + '/',
                    'kind': 'folder',
                    'extra': {},
                }
            }
        )

        user_quota = UserStorageQuota.objects.get(
            region=self.region,
            user=self.project_creator
        )
        assert_equal(user_quota.used, 500)


class TestUpdateUserUsedQuota(OsfTestCase):
    def setUp(self):
        super(TestUpdateUserUsedQuota, self).setUp()
        self.user = UserFactory()
        self.user.save()
        self.user_quota = UserQuota.objects.create(user=self.user, storage_type=UserQuota.NII_STORAGE, max_quota=200,
                                                   used=1000)

    @mock.patch.object(UserQuota, 'save')
    @mock.patch('website.util.quota.used_quota')
    def test_update_user_used_quota_method_with_user_quota_exist(self, mock_used, mock_user_quota_save):
        mock_used.return_value = 500
        quota.update_user_used_quota(
            user=self.user,
            storage_type=UserQuota.NII_STORAGE
        )

        mock_user_quota_save.assert_called()

    @mock.patch('website.util.quota.used_quota')
    def test_update_user_used_quota_method_with_user_quota_not_exist(self, mock_used):
        another_user = UserFactory()
        mock_used.return_value = 500

        quota.update_user_used_quota(
            user=another_user,
            storage_type=UserQuota.NII_STORAGE
        )

        user_quota = UserQuota.objects.filter(
            storage_type=UserQuota.NII_STORAGE,
        ).all()

        assert_equal(len(user_quota), 2)
        user_quota = user_quota.filter(user=another_user)
        assert_equal(len(user_quota), 1)
        user_quota = user_quota[0]
        assert_equal(user_quota.used, 500)


class TestQuotaApiWaterbutler(OsfTestCase):
    def setUp(self):
        super(TestQuotaApiWaterbutler, self).setUp()
        self.user = AuthUserFactory()
        self.node = ProjectFactory(creator=self.user)

    def test_default_values(self):
        ProjectStorageType.objects.filter(node=self.node).delete()
        response = self.app.get(
            '{}?payload={payload}&signature={signature}'.format(
                self.node.api_url_for('waterbutler_creator_quota'),
                **signing.sign_data(signing.default_signer, {})
            )
        )
        assert_equal(response.status_code, 200)
        assert_equal(response.json['max'], api_settings.DEFAULT_MAX_QUOTA * api_settings.SIZE_UNIT_GB)
        assert_equal(response.json['used'], 0)

    def test_used_half_custom_quota(self):
        UserQuota.objects.create(
            storage_type=UserQuota.NII_STORAGE,
            user=self.user,
            max_quota=200,
            used=100 * api_settings.SIZE_UNIT_GB
        )

        response = self.app.get(
            '{}?payload={payload}&signature={signature}'.format(
                self.node.api_url_for('waterbutler_creator_quota'),
                **signing.sign_data(signing.default_signer, {})
            )
        )
        assert_equal(response.status_code, 200)
        assert_equal(response.json['max'], 200 * api_settings.SIZE_UNIT_GB)
        assert_equal(response.json['used'], 100 * api_settings.SIZE_UNIT_GB)

    def test_used_half_custom_institution_quota(self):
        UserQuota.objects.create(
            storage_type=UserQuota.NII_STORAGE,
            user=self.user,
            max_quota=150,
            used=0
        )
        UserQuota.objects.create(
            storage_type=UserQuota.CUSTOM_STORAGE,
            user=self.user,
            max_quota=200,
            used=100 * api_settings.SIZE_UNIT_GB
        )

        institution = InstitutionFactory()
        self.user.affiliated_institutions.add(institution)
        RegionFactory(_id=institution._id)
        ProjectStorageType.objects.filter(node=self.node).update(
            storage_type=ProjectStorageType.CUSTOM_STORAGE
        )

        response = self.app.get(
            '{}?payload={payload}&signature={signature}'.format(
                self.node.api_url_for('waterbutler_creator_quota'),
                **signing.sign_data(signing.default_signer, {})
            )
        )
        assert_equal(response.status_code, 200)
        assert_equal(response.json['max'], 200 * api_settings.SIZE_UNIT_GB)
        assert_equal(response.json['used'], 100 * api_settings.SIZE_UNIT_GB)


class TestQuotaApiBrowser(OsfTestCase):
    def setUp(self):
        super(TestQuotaApiBrowser, self).setUp()
        self.user = AuthUserFactory()
        self.node = ProjectFactory(creator=self.user)

    def test_default_values(self):
        ProjectStorageType.objects.filter(node=self.node).delete()
        response = self.app.get(
            self.node.api_url_for('get_creator_quota'),
            auth=self.user.auth
        )
        assert_equal(response.status_code, 200)
        assert_equal(response.json['max'], api_settings.DEFAULT_MAX_QUOTA * api_settings.SIZE_UNIT_GB)
        assert_equal(response.json['used'], 0)

    def test_used_half_custom_quota(self):
        UserQuota.objects.create(
            storage_type=UserQuota.NII_STORAGE,
            user=self.user,
            max_quota=200,
            used=100 * api_settings.SIZE_UNIT_GB
        )

        response = self.app.get(
            self.node.api_url_for('get_creator_quota'),
            auth=self.user.auth
        )
        assert_equal(response.status_code, 200)
        assert_equal(response.json['max'], 200 * api_settings.SIZE_UNIT_GB)
        assert_equal(response.json['used'], 100 * api_settings.SIZE_UNIT_GB)

    def test_used_half_custom_institution_quota(self):
        UserQuota.objects.create(
            storage_type=UserQuota.NII_STORAGE,
            user=self.user,
            max_quota=150,
            used=0
        )
        UserQuota.objects.create(
            storage_type=UserQuota.CUSTOM_STORAGE,
            user=self.user,
            max_quota=200,
            used=100 * api_settings.SIZE_UNIT_GB
        )

        institution = InstitutionFactory()
        self.user.affiliated_institutions.add(institution)
        RegionFactory(_id=institution._id)
        ProjectStorageType.objects.filter(node=self.node).update(
            storage_type=ProjectStorageType.CUSTOM_STORAGE
        )

        response = self.app.get(
            self.node.api_url_for('get_creator_quota'),
            auth=self.user.auth
        )
        assert_equal(response.status_code, 200)
        assert_equal(response.json['max'], 200 * api_settings.SIZE_UNIT_GB)
        assert_equal(response.json['used'], 100 * api_settings.SIZE_UNIT_GB)


class TestGetRegionIdOfInstitutionalStorageByPath(OsfTestCase):
    def setUp(self):
        self.target = mock.Mock()
        self.provider = 'dropboxbusiness'
        self.path = '/example/path'
        self.storage_type = ProjectStorageType.CUSTOM_STORAGE

    def test_get_region_id_of_institutional_storage_by_path_with_nii_storage_type(self):
        result = get_region_id_of_institutional_storage_by_path(
            self.target,
            'invalid_provider',
            self.path,
            ProjectStorageType.NII_STORAGE
        )

        assert_equal(result, NII_STORAGE_REGION_ID)

    def test_get_region_id_of_institutional_storage_by_path_with_osfstorage_node_setting(self):
        with mock.patch('website.util.quota.get_addon_osfstorage_by_path') as mock_get_addon_osfstorage_by_path:
            region_mock = mock.Mock(id=123)
            osf_node_setting_mock = mock.Mock(region=region_mock)
            mock_get_addon_osfstorage_by_path.return_value = osf_node_setting_mock

            result = get_region_id_of_institutional_storage_by_path(
                self.target,
                'osfstorage',
                self.path,
                self.storage_type
            )

        assert_equal(result, 123)
        mock_get_addon_osfstorage_by_path.assert_called_once_with(
            self.target,
            self.path,
            'osfstorage'
        )

    def test_get_region_id_of_institutional_storage_by_path_with_osfstorage_empty_node_setting(self):
        with mock.patch('website.util.quota.get_addon_osfstorage_by_path') as mock_get_addon_osfstorage_by_path:
            mock_get_addon_osfstorage_by_path.return_value = None

            result = get_region_id_of_institutional_storage_by_path(
                self.target,
                'osfstorage',
                self.path,
                self.storage_type
            )

        assert_is_none(result)

    def test_get_region_id_of_institutional_storage_by_path_with_custom_storage(self):
        region_mock = mock.Mock()
        root_node_mock = mock.Mock()
        root_node_mock.id = 123
        region_mock.id = 456
        institution_mock = mock.Mock()
        institution_mock.affiliated_institutions.first.return_value = institution_mock
        region_filter_mock = mock.Mock()
        region_filter_mock.first.return_value = region_mock
        root_node_filter_mock = mock.Mock()
        root_node_filter_mock.first.return_value = root_node_mock
        addon_st = self.target.add_addon('nextcloudinstitutions', auth=None, log=False, region_id=region_mock.id)
        addon_st.root_node_id = root_node_mock.id
        addon_st.save()

        with mock.patch('website.util.quota.Region.objects.filter') as mock_filter, \
                mock.patch('website.util.quota.BaseFileNode.objects.filter') as mock_base_filter, \
                mock.patch('website.util.quota.get_addon_osfstorage_by_path'):
            mock_filter.return_value = region_filter_mock
            mock_base_filter.return_value = root_node_filter_mock
            self.target.creator.affiliated_institutions.first.return_value = institution_mock
            result = get_region_id_of_institutional_storage_by_path(
                self.target,
                self.provider,
                self.path,
                self.storage_type,
                root_path='123'
            )

        assert_equal(result, 456)
        mock_filter.assert_called_once_with(
            _id=institution_mock._id,
            id=self.target.get_addon().region.id,
            waterbutler_settings__storage__provider=self.provider
        )

    def test_get_region_id_of_institutional_storage_by_path_with_custom_storage_no_region(self):
        root_node_mock = mock.Mock()
        root_node_mock.id = 123
        root_node_filter_mock = mock.Mock()
        root_node_filter_mock.first.return_value = root_node_mock
        institution_mock = mock.Mock()
        institution_mock.affiliated_institutions.first.return_value = institution_mock
        region_filter_mock = mock.Mock()
        region_filter_mock.first.return_value = None

        with mock.patch('website.util.quota.Region.objects.filter') as mock_filter, \
                mock.patch('website.util.quota.BaseFileNode.objects.filter') as mock_base_filter, \
                mock.patch('website.util.quota.get_addon_osfstorage_by_path'):
            mock_filter.return_value = region_filter_mock
            mock_base_filter.return_value = root_node_filter_mock
            self.target.creator.affiliated_institutions.first.return_value = institution_mock

            result = get_region_id_of_institutional_storage_by_path(
                self.target,
                self.provider,
                self.path,
                self.storage_type,
                root_path='123'
            )

        assert_is_none(result)
        mock_base_filter.assert_called_once_with(_id='123')

    def test_get_region_id_of_institutional_storage_by_path_with_custom_storage_no_affiliated_institutions(self):
        with mock.patch('website.util.quota.get_addon_osfstorage_by_path'), \
                mock.patch('website.util.quota.Region.objects.filter'), \
                mock.patch('website.util.quota.get_addon_osfstorage_by_path') as mock_get_addon_osfstorage_by_path:
            self.target.creator.affiliated_institutions.first.return_value = None

            result = get_region_id_of_institutional_storage_by_path(
                self.target,
                self.provider,
                self.path,
                self.storage_type
            )

        assert_is_none(result)

    def test_get_region_id_of_institutional_storage_by_path_with_custom_storage_invalid_provider(self):
        with mock.patch('website.util.quota.get_addon_osfstorage_by_path'), \
                mock.patch('website.util.quota.Region.objects.filter'):
            result = get_region_id_of_institutional_storage_by_path(
                self.target,
                'invalid_provider',
                self.path,
                self.storage_type
            )

        assert_equal(result, NII_STORAGE_REGION_ID)
