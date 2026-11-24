# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django import template

from manager.pipeline_runtime import describe_camera_instance

register = template.Library()


@register.simple_tag
def dlsps_instance_status(cam):
  """Live DLSPS state of the camera's recorded instance, or None when there is none."""
  return describe_camera_instance(cam)
