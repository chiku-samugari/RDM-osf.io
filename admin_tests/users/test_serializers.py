from datetime import datetime

from django.utils import timezone
from nose import tools as nt

from tests.base import AdminTestCase
from osf_tests.factories import NodeFactory, UserFactory, PreprintFactory, InstitutionFactory

from admin.users.serializers import serialize_user, serialize_simple_node, serialize_simple_preprint


class TestUserSerializers(AdminTestCase):
    def test_serialize_user(self):
        user = UserFactory()
        info = serialize_user(user)
        nt.assert_is_instance(info, dict)
        nt.assert_equal(info['name'], user.fullname)
        nt.assert_equal(info['id'], user._id)
        nt.assert_equal(list(info['emails']), list(user.emails.values_list('address', flat=True)))
        nt.assert_equal(info['last_login'], user.date_last_login)

    def test_serialize_two_factor(self):
        user = UserFactory()
        info = serialize_user(user)
        nt.assert_false(info['two_factor'])
        user.get_or_add_addon('twofactor')
        info = serialize_user(user)
        nt.assert_is_instance(info, dict)
        nt.assert_equal(info['name'], user.fullname)
        nt.assert_equal(list(info['emails']), list(user.emails.values_list('address', flat=True)))
        nt.assert_equal(info['last_login'], user.date_last_login)
        nt.assert_true(info['two_factor'])

    def test_serialize_account_status(self):
        user = UserFactory()
        info = serialize_user(user)
        nt.assert_equal(info['disabled'], False)
        user.is_disabled = True
        info = serialize_user(user)
        nt.assert_almost_equal(
            int(info['disabled'].strftime('%s')),
            int(timezone.now().strftime('%s')),
            delta=50)
        nt.assert_is_instance(info['disabled'], datetime)

    def test_serialize_simple_node(self):
        user = UserFactory()
        user.affiliated_institutions = [InstitutionFactory()]
        node = NodeFactory(parent=None, creator=user)
        info = serialize_simple_node(node)
        nt.assert_is_instance(info, dict)
        nt.assert_equal(info['id'], node._id)
        nt.assert_equal(info['title'], node.title)
        nt.assert_equal(info['public'], node.is_public)
        nt.assert_equal(info['number_contributors'], len(node.contributors))

    def test_serialize_simple_preprint(self):
        preprint = PreprintFactory()
        info = serialize_simple_preprint(preprint)
        nt.assert_is_instance(info, dict)
        nt.assert_equal(info['id'], preprint._id)
        nt.assert_equal(info['title'], preprint.title)
        nt.assert_equal(info['public'], preprint.verified_publishable)
        nt.assert_equal(info['number_contributors'], len(preprint.contributors))
