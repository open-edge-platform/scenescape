#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
E2E functional test wrappers.

Each entry maps to an existing Makefile target in tests/Makefile.functional.
The test scripts run locally from the venv — the orchestration (compose
lifecycle, readiness, cleanup) is handled by pytest fixtures.
"""

import os

import pytest

from conftest import FuncTestSpec
from utils.profiles import (
  BROKER_AND_DB,
  BROKER_VDMS_DB,
  FULL_STACK,
  FULL_STACK_CALIBRATION,
  FULL_STACK_WITH_VIDEO,
  FULL_STACK_WITH_VIDEO_AND_RETAIL,
  FULL_STACK_WITH_VIDEO_NO_NTP,
  REID,
  REID_DATA_FLOW,
  REID_SEMANTIC,
  SCENE_NO_DB,
  WEB_ONLY,
)


# ---------------------------------------------------------------------------
# Functional test specifications
# ---------------------------------------------------------------------------

FUNCTIONAL_TESTS = [
  # --- WEB_ONLY (pgserver + web) ---
  FuncTestSpec(
    id="rest_test",
    profile=WEB_ONLY,
    script="manager/tests/tc_rest_test.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="different_formats_maps_api",
    profile=WEB_ONLY,
    script="manager/tests/tc_different_formats_maps_api.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="scene_import_api",
    profile=WEB_ONLY,
    script="manager/tests/tc_scene_import_api.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="scenes_summary_api",
    profile=WEB_ONLY,
    script="manager/tests/tc_scenes_summary_api.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="object_crud_api",
    profile=WEB_ONLY,
    script="manager/tests/tc_object_crud_api.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="add_delete_3d_object_api",
    profile=WEB_ONLY,
    script="manager/tests/tc_add_delete_3d_object_api.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="upload_3d_glb_file_api",
    profile=WEB_ONLY,
    script="manager/tests/tc_upload_3d_glb_file_api.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="upload_only_3d_glb_files_api",
    profile=WEB_ONLY,
    script="manager/tests/tc_upload_only_3d_glb_files_api.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="sensor_area_api",
    profile=WEB_ONLY,
    script="manager/tests/tc_sensor_area_api.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="superuser_crud_operations_api",
    profile=WEB_ONLY,
    script="manager/tests/tc_superuser_crud_operations_api.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="sensor_location_api",
    profile=WEB_ONLY,
    script="manager/tests/tc_sensor_location_api.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="sensor_scene_api",
    profile=WEB_ONLY,
    script="manager/tests/tc_sensor_scene_api.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="calibrate_all_sensor_types_api",
    profile=WEB_ONLY,
    script="manager/tests/tc_calibrate_all_sensor_types_api.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="api_large_strings",
    profile=WEB_ONLY,
    script="manager/tests/tc_api_large_strings.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="manual_camera_calibration_api",
    profile=WEB_ONLY,
    script="manager/tests/tc_manual_camera_calibration_api.py",
    auth="/run/secrets/controller.auth",
  ),

  # --- FULL_STACK (broker + ntp + pgserver + scene + web) ---
  FuncTestSpec(
    id="mqtt_roi",
    profile=FULL_STACK,
    script="tests/functional/tc_roi_mqtt.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="mqtt_tripwire",
    profile=FULL_STACK,
    script="tests/functional/tc_tripwire_mqtt.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="mqtt_sensor_roi",
    profile=FULL_STACK,
    script="tests/functional/tc_mqtt_sensor_roi.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="mqtt_slow_sensor_roi",
    profile=FULL_STACK,
    script="tests/functional/tc_mqtt_slow_sensor_roi.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="add_orphaned_cameras",
    profile=FULL_STACK,
    script="tests/functional/tc_add_orphaned_cameras.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="child_scenes",
    profile=FULL_STACK,
    script="tests/functional/tc_child_scenes.py",
    auth="/run/secrets/controller.auth",

  ),
  FuncTestSpec(
    id="camera_deletion_api",
    profile=FULL_STACK,
    script="tests/functional/tc_camera_deletion_api.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="camera_intrinsics_api",
    profile=FULL_STACK,
    script="tests/functional/tc_camera_intrinsics_api.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="delete_roi_mqtt",
    profile=FULL_STACK,
    script="tests/functional/tc_delete_roi_mqtt.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="delete_sensor_mqtt_api",
    profile=FULL_STACK,
    script="tests/functional/tc_delete_sensor_mqtt_api.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="delete_sensor_scene_api",
    profile=FULL_STACK,
    script="tests/functional/tc_delete_sensor_scene_api.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="delete_sensors_api",
    profile=FULL_STACK,
    script="tests/functional/tc_delete_sensors_api.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="delete_tripwire_mqtt",
    profile=FULL_STACK,
    script="tests/ui/tc_delete_tripwire_mqtt.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="geospatial_ingest_publish",
    profile=FULL_STACK,
    script="tests/functional/tc_geospatial_ingest_publish.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="orphaned_sensor",
    profile=FULL_STACK,
    script="tests/functional/tc_orphaned_sensor.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="sensors_send_events",
    profile=FULL_STACK,
    script="tests/functional/tc_sensors_send_mqtt_messages.py",
    auth="/run/secrets/controller.auth",
  ),

  # --- BROKER_AND_DB (no containers to wait for) ---
  FuncTestSpec(
    id="mqtt_auth",
    profile=BROKER_AND_DB,
    script="tests/security/system/negative_mqtt_insecure_auth.py",
    require_password=False,
    auth="",
  ),
  FuncTestSpec(
    id="mqtt_cert",
    profile=BROKER_AND_DB,
    script="tests/security/system/negative_mqtt_insecure_cert.py",
    require_password=False,
    auth="",
  ),

  # --- SCENE_NO_DB ---
  FuncTestSpec(
    id="scene_import_json",
    profile=SCENE_NO_DB,
    script="controller/tests/tc_scene_import_json.py",
    auth="/run/secrets/controller.auth",
  ),

  # --- FULL_STACK_WITH_VIDEO ---
  FuncTestSpec(
    id="out_of_box",
    profile=FULL_STACK_WITH_VIDEO,
    script="tests/ui/tc_out_of_box.py",
    auth="/run/secrets/browser.auth",
  ),
  FuncTestSpec(
    id="out_of_box_no_ntp",
    profile=FULL_STACK_WITH_VIDEO_NO_NTP,
    script="tests/ui/tc_out_of_box.py",
    auth="/run/secrets/browser.auth",
  ),
  FuncTestSpec(
    id="visibility_regulated",
    profile=FULL_STACK_WITH_VIDEO,
    script="tests/functional/tc_camera_bound_visibility_regulated.py",
    auth="/run/secrets/browser.auth",
    extra_args=["--visibility_topic", "regulated"],
  ),
  FuncTestSpec(
    id="visibility_unregulated",
    profile=FULL_STACK_WITH_VIDEO,
    script="tests/functional/tc_camera_bound_visibility_unregulated.py",
    auth="/run/secrets/browser.auth",
    extra_args=["--visibility_topic", "unregulated"],
  ),
  FuncTestSpec(
    id="visibility_none",
    profile=FULL_STACK_WITH_VIDEO,
    script="tests/functional/tc_camera_bound_visibility_none.py",
    auth="/run/secrets/browser.auth",
    extra_args=["--visibility_topic", "none"],
  ),
  FuncTestSpec(
    id="bounding_box",
    profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
    script="tests/ui/tc_bounding_box.py",
    auth="/run/secrets/browser.auth",
  ),
  FuncTestSpec(
    id="scene_details_api",
    profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
    script="tests/functional/tc_scene_details_api.py",
    auth="/run/secrets/controller.auth",
  ),
  FuncTestSpec(
    id="scene_import",
    profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
    script="tests/ui/tc_scene_import.py",
    auth="/run/secrets/controller.auth",
  ),

  # --- FULL_STACK_CALIBRATION ---
  FuncTestSpec(
    id="auto_calibration_api",
    profile=FULL_STACK_CALIBRATION,
    script="tests/functional/tc_auto_calibration_api.py",
    auth="/run/secrets/browser.auth",
    exampledb="tests/calibrationdb.tar.bz2",
  ),

  # --- REID ---
  FuncTestSpec(
    id="reid_performance_degradation",
    profile=REID,
    script="tests/functional/tc_reid_performance_degradation.py",

  ),
  FuncTestSpec(
    id="reid_unique_count",
    profile=REID,
    script="tests/functional/tc_reid_unique_count.py",

  ),
  FuncTestSpec(
    id="reid_data_flow",
    profile=REID_DATA_FLOW,
    script="tests/functional/tc_reid_data_flow.py",

  ),
  FuncTestSpec(
    id="reid_semantic_unique_count",
    profile=REID_SEMANTIC,
    script="tests/functional/tc_reid_semantic_unique_count.py",

  ),

  # --- BROKER_VDMS_DB ---
  FuncTestSpec(
    id="vdms_similarity_search",
    profile=BROKER_VDMS_DB,
    script="tests/functional/tc_vdms_similarity_search.py",
    auth="/run/secrets/controller.auth",

  ),

  # --- FULL_STACK_WITH_VIDEO_AND_RETAIL (full stack with video) ---
  FuncTestSpec(
    id="live_view_button",
    profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
    script="tests/ui/tc_live_button_works.py",
    require_password=True,
    auth="",
  ),
  FuncTestSpec(
    id="show_telemetry_button",
    profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
    script="tests/ui/tc_show_telemetry_button.py",
    auth="/run/secrets/controller.auth",
  ),

  # --- System stability (long-running; uses STABILITY_HOURS env var) ---
  FuncTestSpec(
    id="system_stability",
    profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
    script="tests/system/stability/tc_sscape_stability.py",
    require_password=False,
    auth="",
    extra_args=["--hours", os.environ.get("STABILITY_HOURS", "24")],
  ),
]


# ---------------------------------------------------------------------------
# Parametrized test function
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def test_spec(request):
  """Extract the TestSpec from the parametrize marker."""
  return request.param


@pytest.mark.parametrize(
  "test_spec,scenescape_env",
  [(s, s) for s in FUNCTIONAL_TESTS],
  ids=[s.id for s in FUNCTIONAL_TESTS],
  indirect=True,
)
def test_func(scenescape_env, run_test, test_spec):
  """Run a functional test end-to-end.

  Each parametrized entry starts its own compose stack, runs the test
  script locally from the venv, and tears down on completion.
  """
  rc = run_test(test_spec)
  assert rc == 0, f"Test {test_spec.id} failed with exit code {rc}"
