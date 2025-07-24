# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

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
