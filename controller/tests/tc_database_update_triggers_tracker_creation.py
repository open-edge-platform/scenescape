#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Verify database update handling refreshes scenes and creates trackers."""

from unittest.mock import Mock, patch

from controller.controller_mode import ControllerMode
from controller.scene import Scene
from controller.scene_controller import SceneController


class _FakeDataSource:
  def getChildScenes(self, scene_uid):
    return {"results": []}


class _FakeCacheManager:
  def __init__(self):
    self.invalidate_called = False
    self.all_scenes_called = False
    self.created_scenes = []
    self.data_source = _FakeDataSource()
    self.cached_child_transforms_by_uid = {}

  def invalidate(self):
    self.invalidate_called = True

  def allScenes(self):
    self.all_scenes_called = True
    scene_data = {
      "uid": "db-update-scene-1",
      "name": "db_update_scene",
      "map": None,
      "scale": 1000.0,
      "cameras": [],
      "regions": [],
      "tripwires": [],
      "sensors": [],
      "children": [],
    }
    scene = Scene.deserialize(scene_data)
    self.created_scenes = [scene]
    return self.created_scenes


class TestDatabaseUpdateTrackerCreation:
  """Validate cmd/database update path triggers tracker creation."""

  def test_handle_database_update_creates_tracker_for_new_scene(self):
    if not ControllerMode._initialized:
      ControllerMode.initialize(analytics_only=False)
    ControllerMode._analytics_only_mode = False

    controller = SceneController.__new__(SceneController)
    controller.cache_manager = _FakeCacheManager()
    controller.pubsub = Mock()
    controller.subscribed = set()
    controller.subscribed_children = {}
    controller.root_cert = None

    controller.updateObjectClasses = Mock()
    controller.updateCameras = Mock()
    controller.updateRegulateCache = Mock()
    controller.updateTRSMatrix = Mock()

    mqtt_message = Mock()
    mqtt_message.payload = b"update"

    def _fake_set_tracker(scene, tracker_type):
      scene.trackerType = tracker_type
      scene.tracker = Mock(name="tracker")

    with patch.object(Scene, "_setTracker", autospec=True) as mock_set_tracker:
      mock_set_tracker.side_effect = _fake_set_tracker

      controller.handleDatabaseMessage(None, None, mqtt_message)

      assert controller.cache_manager.invalidate_called is True
      assert controller.cache_manager.all_scenes_called is True
      assert len(controller.cache_manager.created_scenes) == 1
      assert controller.cache_manager.created_scenes[0].tracker is not None
      assert mock_set_tracker.called
