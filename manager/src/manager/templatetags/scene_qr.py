# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django import template
from django.utils.safestring import mark_safe

from manager.scene_pairing import pairing_uri, qr_svg

register = template.Library()


@register.simple_tag
def scene_pairing_uri(scene, user, request):
  return pairing_uri(request.get_host(), user.username, scene.name, scene.id)


@register.simple_tag
def scene_qr_svg(scene, user, request):
  uri = pairing_uri(request.get_host(), user.username, scene.name, scene.id)
  return mark_safe(qr_svg(uri))
