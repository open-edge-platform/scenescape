#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time

from controller.scene import Scene
from scene_common.timestamp import get_iso_time


def _build_person(person_id, x, y):
  return {
    "id": person_id,
    "category": "person",
    "confidence": 0.99,
    "bounding_box": {
      "x": x,
      "y": y,
      "width": 0.18,
      "height": 0.42,
    },
  }


def _build_frame(camera_id, timestamp, persons):
  return {
    "id": camera_id,
    "timestamp": get_iso_time(timestamp),
    "objects": {
      "person": persons,
    },
    "rate": 20.0,
  }


def _wait_for_count(scene, expected_count, timeout_secs):
  deadline = time.time() + timeout_secs
  while time.time() < deadline:
    if "person" in scene.tracker.trackers:
      scene.tracker.trackers["person"].waitForComplete()

    if len(scene.tracker.currentObjects("person")) == expected_count:
      return True

    time.sleep(0.05)

  return False


def test_time_chunking_three_objects_simultaneous_exit(camera_obj):
  frame_interval = 0.05
  scene = Scene(
    "time_chunking_exit_test",
    "sample_data/HazardZoneSceneLarge.png",
    max_unreliable_time=0.2,
    non_measurement_time_dynamic=0.2,
    non_measurement_time_static=0.2,
    effective_object_update_rate=20,
    time_chunking_enabled=True,
    time_chunking_rate_fps=20,
    suspended_track_timeout_secs=2.0,
  )
  scene.cameras[camera_obj.cameraID] = camera_obj

  start = time.time()

  try:
    # Warm-up with 3 tracked objects across multiple frames.
    for i in range(10):
      persons = [
        _build_person(101, 0.16, 0.10 + (i * 0.003)),
        _build_person(102, 0.40, 0.22 + (i * 0.003)),
        _build_person(103, 0.64, 0.34 + (i * 0.003)),
      ]
      frame = _build_frame(camera_obj.cameraID, start + (i * frame_interval), persons)
      assert scene.processCameraData(frame)
      time.sleep(frame_interval)

    assert _wait_for_count(scene, 3, timeout_secs=4.0), (
      "Expected 3 tracked objects before simultaneous exit"
    )

    # Simulate simultaneous exit by publishing empty detections for the same category.
    for i in range(10):
      frame = _build_frame(camera_obj.cameraID, start + ((10 + i) * frame_interval), [])
      assert scene.processCameraData(frame)
      time.sleep(frame_interval)

    assert _wait_for_count(scene, 0, timeout_secs=4.0), (
      "Expected all 3 tracks to retire after simultaneous exit under time chunking"
    )

  finally:
    scene.tracker.join()
