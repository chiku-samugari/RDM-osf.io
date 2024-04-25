# -*- coding: utf-8 -*-
from osf.models.region_external_account import RegionExternalAccount


def set_region_external_account(region, account):
    region_external_account = RegionExternalAccount.objects.filter(region=region).first()
    if region_external_account is not None:
        # Account is being updated, so delete the previous one and put the new one
        if region_external_account.external_account != account:
            region_external_account.external_account.delete()
        region_external_account.external_account = account
        region_external_account.save()
    else:
        RegionExternalAccount.objects.create(
            region=region,
            external_account=account,
        )


def set_new_access_token(external_account, region=None):
    if region is None:
        region_externals = RegionExternalAccount.objects.filter(external_account=external_account)
        for region_external in region_externals:
            region = region_external.region
            region.waterbutler_credentials['storage']['token'] = external_account.oauth_key
            region.save()
    else:
        region.waterbutler_credentials['storage']['token'] = external_account.oauth_key
        region.save()


def remove_region_external_account(region):
    region_external_account = RegionExternalAccount.objects.filter(region=region).first()
    if region_external_account is not None:
        region_external_account.external_account.delete()
        region_external_account.delete()

def is_institutional_storage(external_account):
    return RegionExternalAccount.objects.filter(external_account=external_account).exists()
