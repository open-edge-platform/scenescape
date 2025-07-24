# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from django.contrib import admin
from manager.models import PubSubACL

@admin.register(PubSubACL)
class PubSubACLAdmin(admin.ModelAdmin):
  list_display = ('user', 'topic', 'get_access_display')
  search_fields = ('user__username', 'topic')
  list_filter = ('access', 'user')
  ordering = ('user', 'topic')

  def get_access_display(self, obj):
    return obj.get_access_display()
  get_access_display.short_description = 'Access Level'
  get_access_display.admin_order_field = 'access'
