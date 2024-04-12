#!/usr/bin/env python3
# encoding: utf-8
from django.apps import apps
from django.utils import timezone
from factory import SubFactory, post_generation, Sequence
from factory.django import DjangoModelFactory

from addons.osfstorage.models import NodeSettings
from osf import models
from osf_tests.factories import AuthUserFactory, RegionFactory, ExternalAccountFactory

settings = apps.get_app_config('addons_osfstorage')


generic_location = {
    'service': 'cloud',
    settings.WATERBUTLER_RESOURCE: 'resource',
    'object': '1615307',
}


class FileVersionFactory(DjangoModelFactory):
    class Meta:
        model = models.FileVersion

    creator = SubFactory(AuthUserFactory)
    modified = timezone.now()
    location = generic_location
    identifier = 0

    @post_generation
    def refresh(self, create, extracted, **kwargs):
        if not create:
            return
        self.reload()


class OsfStorageNodeSettingsFactory(DjangoModelFactory):
    class Meta:
        model = NodeSettings

    region = SubFactory(RegionFactory)


class OsfStorageAccountFactory(ExternalAccountFactory):
    provider = 'osfstorage'
    provider_id = Sequence(lambda n: 'id-{0}'.format(n))
    oauth_key = Sequence(lambda n: 'key-{0}'.format(n))
    display_name = 'abc'
