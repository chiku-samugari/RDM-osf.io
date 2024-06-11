import pytest

from api.base.settings.defaults import API_BASE
from osf_tests.factories import (
    InstitutionFactory,
    UserFactory,
)


@pytest.mark.django_db
@pytest.mark.enable_quickfiles_creation
class TestInstitutionUsersList:

    def test_return_all_users(self, app):
        institution = InstitutionFactory()

        user_one = UserFactory()
        user_one.affiliated_institutions.add(institution)
        user_one.save()

        user_two = UserFactory()
        user_two.affiliated_institutions.add(institution)
        user_two.save()

        url = '/{0}institutions/{1}/users/'.format(API_BASE, institution._id)
        res = app.get(url, expect_errors=True)

        assert res.status_code == 401
