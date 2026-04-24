#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for tracker replacement and shutdown behavior in Scene/Tracking."""

from controller.scene import Scene
from controller.tracking import STREAMING_MODE, Tracking


class FakeTracker:
  created_instances = []
  active_instances = 0

  def __init__(self, *args):
    self.args = args
    self.join_called = False
    self.shutdown_complete = False
    self._active = True
    FakeTracker.created_instances.append(self)
    FakeTracker.active_instances += 1

  def join(self):
    if self._active:
      self.join_called = True
      # Simulate complete resource teardown performed by real tracker.join().
      self.shutdown_complete = True
      self._active = False
      FakeTracker.active_instances -= 1

  def updateReidConfig(self, reid_config_data=None):
    self.reid_config_data = reid_config_data if reid_config_data else {}


class FakeQueue:
  def __init__(self):
    self.items = []

  def put(self, item):
    self.items.append(item)


class FakeUUIDManager:
  def __init__(self):
    self.shutdown_called = False

  def shutdown(self):
    self.shutdown_called = True


class FakeChildTracker:
  def __init__(self):
    self.queue = FakeQueue()
    self.wait_complete_called = False
    self.join_called = False
    self.uuid_manager = FakeUUIDManager()

  def waitForComplete(self):
    self.wait_complete_called = True

  def join(self):
    self.join_called = True


def _build_minimal_scene(monkeypatch):
  """Create a Scene instance with only fields needed for update tests."""
  monkeypatch.setattr(Scene, "trs_xyz_to_lla", property(lambda self: None))

  scene = Scene.__new__(Scene)
  scene.available_trackers = {"intel_labs": FakeTracker}
  scene.trackerType = "intel_labs"
  scene.max_unreliable_time = 1.0
  scene.non_measurement_time_dynamic = 2.0
  scene.non_measurement_time_static = 3.0
  scene.ref_camera_frame_rate = 10
  scene.time_chunking_rate_fps = 10
  scene.suspended_track_timeout_secs = 5
  scene.reid_config_data = {"similarity_threshold": 0.4}
  scene.tracker = FakeTracker(
      scene.max_unreliable_time,
      scene.non_measurement_time_dynamic,
      scene.non_measurement_time_static,
      scene.ref_camera_frame_rate,
      scene.suspended_track_timeout_secs,
      scene.reid_config_data,
  )

  scene.uid = "scene-1"
  scene.parent = None
  scene.cameraPose = None
  scene.use_tracker = True
  scene.output_lla = False
  scene.map_corners_lla = None
  scene.regions = {}
  scene.tripwires = {}
  scene.sensors = {}
  scene.name = "scene-1"
  scene.scale = 1.0
  scene.regulated_rate = None
  scene.external_update_rate = None

  scene._updateChildren = lambda _children: None
  scene.updateCameras = lambda _cameras: None
  scene._updateRegions = lambda _dst, _src: None
  scene._updateTripwires = lambda _tripwires: None
  scene._invalidate_trs_xyz_to_lla = lambda: None

  return scene


class TestSceneTrackerReplacementFlow:
  def setup_method(self):
    FakeTracker.created_instances = []
    FakeTracker.active_instances = 0

  def test_update_tracker_replaces_old_tracker_and_joins_old_instance(self, monkeypatch):
    scene = _build_minimal_scene(monkeypatch)
    old_tracker = scene.tracker

    scene.updateTracker(4.0, 5.0, 6.0)

    assert scene.tracker is not old_tracker
    assert old_tracker.join_called is True
    assert old_tracker.shutdown_complete is True
    assert scene.max_unreliable_time == 4.0
    assert scene.non_measurement_time_dynamic == 5.0
    assert scene.non_measurement_time_static == 6.0

  def test_reid_config_change_updates_runtime_behavior_without_reinitialization(self, monkeypatch):
    scene = _build_minimal_scene(monkeypatch)
    old_tracker = scene.tracker

    monkeypatch.setattr(
        "controller.scene.ControllerMode.isAnalyticsOnly",
        lambda: False,
    )

    scene.updateScene({
        "name": "scene-1",
        "children": [],
        "cameras": [],
        "regions": [],
        "tripwires": [],
        "sensors": [],
        "use_tracker": True,
        "reid_config_data": {"similarity_threshold": 0.7},
    })

    assert scene.tracker is old_tracker
    assert old_tracker.join_called is False
    assert old_tracker.shutdown_complete is False
    assert old_tracker.reid_config_data == {"similarity_threshold": 0.7}
    assert scene.reid_config_data == {"similarity_threshold": 0.7}

  def test_repeated_reinitialization_does_not_leak_tracker_instances(self, monkeypatch):
    scene = _build_minimal_scene(monkeypatch)

    monkeypatch.setattr(
        "controller.scene.ControllerMode.isAnalyticsOnly",
        lambda: False,
    )

    for idx in range(1, 11):
      scene.updateScene({
          "name": "scene-1",
          "children": [],
          "cameras": [],
          "regions": [],
          "tripwires": [],
          "sensors": [],
          "use_tracker": True,
          "reid_config_data": {"similarity_threshold": 0.4 + (0.01 * idx)},
      })

    # ReID-only updates should not create or replace tracker instances.
    assert len(FakeTracker.created_instances) == 1
    assert scene.tracker is FakeTracker.created_instances[0]

    # Exactly one active tracker should remain: the current scene tracker.
    assert FakeTracker.active_instances == 1

    # Explicitly tear down the currently active tracker and verify no survivors.
    scene.tracker.join()
    assert FakeTracker.active_instances == 0


class TestTrackingJoinShutdown:
  def test_join_shuts_down_child_and_parent_uuid_managers(self):
    parent_tracker = Tracking.__new__(Tracking)
    child_tracker = FakeChildTracker()
    parent_tracker.trackers = {"person": child_tracker}
    parent_tracker.uuid_manager = FakeUUIDManager()

    Tracking.join(parent_tracker)

    assert child_tracker.queue.items == [(None, None, None, STREAMING_MODE)]
    assert child_tracker.wait_complete_called is True
    assert child_tracker.join_called is True
    assert child_tracker.uuid_manager.shutdown_called is True
    assert parent_tracker.uuid_manager.shutdown_called is True
