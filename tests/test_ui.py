#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
UI / Selenium test wrappers.

Each entry maps to an existing Makefile target in tests/Makefile.user_interface.
The test scripts run locally from the venv — orchestration
(compose lifecycle, readiness, cleanup) is handled by pytest fixtures.
"""

import pytest

from conftest import FuncTestSpec
from utils.profiles import (
  AUTO_CALIBRATION_UI,
  BROKER_WEB,
  FULL_STACK,
  FULL_STACK_WITH_VIDEO_AND_RETAIL,
)


# ---------------------------------------------------------------------------
# UI / Selenium test specifications
# ---------------------------------------------------------------------------

UI_TESTS = [

  # --- BROKER_WEB (broker + pgserver + web) ---
  FuncTestSpec(
    id="3d_camera_control_panel",
    profile=BROKER_WEB,
    script="tests/ui/tc_camera_control_panel.py",
    require_password=True,
    auth="",
  ),
  FuncTestSpec(
    id="3d_scene_control_panel",
    profile=BROKER_WEB,
    script="tests/ui/tc_scene_control_panel.py",
    require_password=True,
    auth="",
  ),
  FuncTestSpec(
    id="add_delete_3d_object",
    profile=BROKER_WEB,
    script="tests/ui/tc_add_delete_3d_object.py",
    require_password=True,
    auth="",
  ),
  FuncTestSpec(
    id="calibrate_all_sensor_types",
    profile=BROKER_WEB,
    script="tests/ui/tc_calibrate_all_sensor_types.py",
    require_password=True,
    auth="",
  ),
  FuncTestSpec(
    id="camera_deletion",
    profile=BROKER_WEB,
    script="tests/ui/tc_camera_deletion.py",
    require_password=True,
    auth="",
  ),
  FuncTestSpec(
    id="camera_intrinsics",
    profile=BROKER_WEB,
    script="tests/ui/tc_camera_intrinsics.py",
    require_password=True,
    auth="",
  ),
  FuncTestSpec(
    id="camera_perspective",
    profile=BROKER_WEB,
    script="tests/ui/tc_camera_perspective.py",
    require_password=True,
    auth="",
  ),
  FuncTestSpec(
    id="delete_sensor_scene",
    profile=BROKER_WEB,
    script="tests/ui/tc_delete_sensor_scene.py",
    require_password=True,
    auth="",
  ),
  FuncTestSpec(
    id="delete_sensors",
    profile=BROKER_WEB,
    script="tests/ui/tc_delete_sensors.py",
    require_password=True,
    auth="",
  ),
  FuncTestSpec(
    id="different_formats_maps",
    profile=BROKER_WEB,
    script="tests/ui/tc_different_formats_maps.py",
    require_password=True,
    auth="",
  ),
  FuncTestSpec(
    id="timestamp_format",
    profile=BROKER_WEB,
    script="tests/ui/tc_timestamp_format.py",
    require_password=True,
    auth="",
  ),
  FuncTestSpec(
    id="manual_camera_calibration",
    profile=BROKER_WEB,
    script="tests/ui/tc_manual_camera_calibration.py",
    require_password=True,
    auth="",
  ),
  FuncTestSpec(
    id="object_crud",
    profile=BROKER_WEB,
    script="tests/ui/tc_object_crud.py",
    require_password=True,
    auth="",
  ),
  FuncTestSpec(
    id="restricted_media_access",
    profile=BROKER_WEB,
    script="tests/ui/tc_restricted_media_access.py",
    require_password=True,
    auth="",
  ),
  FuncTestSpec(
    id="scenes_summary",
    profile=BROKER_WEB,
    script="tests/ui/tc_scenes_summary.py",
    require_password=True,
    auth="",
  ),
  FuncTestSpec(
    id="sensor_area",
    profile=BROKER_WEB,
    script="tests/ui/tc_sensor_area.py",
    require_password=True,
    auth="",
  ),
  FuncTestSpec(
    id="sensor_location",
    profile=BROKER_WEB,
    script="tests/ui/tc_sensor_location.py",
    require_password=True,
    auth="",
  ),
  FuncTestSpec(
    id="sensor_scene",
    profile=BROKER_WEB,
    script="tests/ui/tc_sensor_scene.py",
    require_password=True,
    auth="",
  ),
  FuncTestSpec(
    id="superuser_crud_operations",
    profile=BROKER_WEB,
    script="tests/ui/tc_superuser_crud_operations.py",
    require_password=True,
    auth="",
  ),
  FuncTestSpec(
    id="upload_3d_glb_file",
    profile=BROKER_WEB,
    script="tests/ui/tc_upload_3d_glb_file.py",
    require_password=True,
    auth="",
  ),
  FuncTestSpec(
    id="upload_only_3d_glb_files",
    profile=BROKER_WEB,
    script="tests/ui/tc_upload_only_3d_glb_files.py",
    require_password=True,
    auth="",
  ),

  # --- FULL_STACK (broker + ntp + pgserver + scene + web) ---
  FuncTestSpec(
    id="delete_sensor_mqtt",
    profile=FULL_STACK,
    script="tests/ui/tc_delete_sensor_mqtt.py",
    require_password=True,
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="view_3d_glb_file",
    profile=FULL_STACK,
    script="tests/ui/tc_view_3d_glb_file.py",
    require_password=True,
    auth="",
  ),
  # NOTE: The two-phase `persistence` test (persistence_navigate + persistence_restart)
  #   is represented as two separate isolated tests. In the original bash approach the
  #   compose stack was kept between phases via CLEANUP_MODE=keep_volumes; in the pytest
  #   model each test spins up a fresh stack, so persistence_restart will not see data
  #   from persistence_navigate.
  FuncTestSpec(
    id="persistence_navigate",
    profile=FULL_STACK,
    script="tests/ui/tc_persistence_on_page_navigate.py",
    require_password=True,
    auth="",
  ),
  FuncTestSpec(
    id="persistence_restart",
    profile=FULL_STACK,
    script="tests/ui/tc_persistence_on_restart.py",
    require_password=True,
    auth="",
  ),

  # --- FULL_STACK_WITH_VIDEO_AND_RETAIL ---
  FuncTestSpec(
    id="3d_ui_calibration_points",
    profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
    script="tests/ui/tc_3d_ui_calibration_points.py",
    require_password=True,
    auth="",
  ),
  FuncTestSpec(
    id="camera_status",
    profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
    script="tests/ui/tc_camera_status.py",
    require_password=True,
    auth="",
  ),
  FuncTestSpec(
    id="scene_details",
    profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
    script="tests/ui/tc_scene_details.py",
    require_password=True,
    auth="",
  ),

  # --- AUTO_CALIBRATION_UI (full stack with autocalibration + retail/queuing video) ---
  FuncTestSpec(
    id="auto_calibration_ui",
    profile=AUTO_CALIBRATION_UI,
    script="tests/ui/tc_auto_calibration_ui.py",
    require_password=True,
    auth="",
    exampledb="sample_data/exampledb.tar.bz2",
  ),
  FuncTestSpec(
    id="calibrate_camera_3d_ui_2d_ui",
    profile=AUTO_CALIBRATION_UI,
    script="tests/ui/tc_calibrate_camera_3d_ui_2d_ui.py",
    require_password=True,
    auth="",
  ),
]


# ---------------------------------------------------------------------------
# Parametrized test function
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def ui_spec(request):
  """Extract the FuncTestSpec from the parametrize marker."""
  return request.param


@pytest.mark.parametrize(
  "ui_spec,scenescape_env",
  [(s, s) for s in UI_TESTS],
  ids=[s.id for s in UI_TESTS],
  indirect=True,
)
def test_ui(scenescape_env, run_test, ui_spec):
  """Run a UI/Selenium test end-to-end.

  Each parametrized entry starts its own compose stack, runs the test
  script locally from the venv, and tears down on completion.
  """
  rc = run_test(ui_spec)
  assert rc == 0, f"UI test {ui_spec.id} failed with exit code {rc}"
