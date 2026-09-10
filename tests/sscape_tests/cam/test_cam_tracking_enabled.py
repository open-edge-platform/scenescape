# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Tests for tracking_enabled attribute on Sensor/Camera.
"""

import pytest

from controller.scene_controller import SceneController
from scene_common.camera import Camera


class TestCameraTrackingEnabled:
  """Test Camera class tracking_enabled attribute."""

  def test_camera_tracking_enabled_defaults_to_true(self):
    """Camera should default tracking_enabled to True."""
    camera = Camera('cam1', {'intrinsics': {'fx': 1.0, 'fy': 1.0, 'cx': 320, 'cy': 240}})
    assert camera.tracking_enabled is True

  def test_camera_tracking_enabled_from_info(self):
    """Camera should read tracking_enabled from info dict."""
    camera = Camera('cam1', {
        'intrinsics': {'fx': 1.0, 'fy': 1.0, 'cx': 320, 'cy': 240},
        'tracking_enabled': False
    })
    assert camera.tracking_enabled is False

  def test_camera_tracking_enabled_explicit_true(self):
    """Camera should read explicit tracking_enabled=True."""
    camera = Camera('cam1', {
        'intrinsics': {'fx': 1.0, 'fy': 1.0, 'cx': 320, 'cy': 240},
        'tracking_enabled': True
    })
    assert camera.tracking_enabled is True
