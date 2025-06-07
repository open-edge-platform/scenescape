# Copyright (C) 2021-2023 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

from django import template
from django.contrib.auth.models import Group

register = template.Library()

@register.filter(name='has_group')
def has_group(user, group_name):
  group = Group.objects.filter(name=group_name)
  if group:
    group = group.first()
    return group in user.groups.all()
  else:
    return False

@register.filter(name='add_class')
def addclass(field, class_attr):
  return field.as_widget(attrs={'class': class_attr})
