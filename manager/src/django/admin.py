# Copyright (C) 2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

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
