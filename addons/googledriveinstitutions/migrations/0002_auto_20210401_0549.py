# -*- coding: utf-8 -*-
# Generated by Django 1.11.28 on 2021-04-01 05:49
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('osf', '0215_auto_20210324_0126'),
        ('addons_googledriveinstitutions', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='nodesettings',
            name='external_account',
        ),
        migrations.AddField(
            model_name='nodesettings',
            name='addon_option',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='addons_googledriveinstitutions_node_settings', to='osf.RdmAddonOption'),
        ),
    ]
