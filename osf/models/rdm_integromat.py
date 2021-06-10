# -*- coding: utf-8 -*-

from django.db import models
from osf.utils.fields import EncryptedTextField

class RdmWorkflows(models.Model):
    id = models.AutoField(primary_key=True)
    workflow_description = models.CharField(max_length=256, unique=True)
    workflow_apps = models.CharField(max_length=256, unique=True)
    webhook_url = EncryptedTextField(blank=True, null=True)

class RdmWebMeetingApps(models.Model):
    id = models.AutoField(primary_key=True)
    app_name = models.CharField(max_length=128, unique=True)
