#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Verify database update handling refreshes scenes and creates trackers."""

import pytest
from unittest.mock import Mock, patch

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


def _make_controller():
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
  return controller


class TestDatabaseUpdateTrackerCreation:
  """Validate cmd/database update path triggers tracker creation."""

  def test_handle_database_update_creates_tracker_for_new_scene(self):
    controller = _make_controller()
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
      scene = controller.cache_manager.created_scenes[0]
      assert scene.tracker is not None
      mock_set_tracker.assert_called_once_with(scene, Scene.DEFAULT_TRACKER)
      controller.updateObjectClasses.assert_called_once()
      controller.updateCameras.assert_called_once()
      controller.updateRegulateCache.assert_called_once()
      controller.updateTRSMatrix.assert_called_once()

  @pytest.mark.parametrize("payload", [b"delete", b"create", b"reload", b""])
  def test_handle_database_non_update_payload_does_nothing(self, payload):
    controller = _make_controller()
    mqtt_message = Mock()
    mqtt_message.payload = payload

    with patch.object(Scene, "_setTracker", autospec=True) as mock_set_tracker:
      controller.handleDatabaseMessage(None, None, mqtt_message)

      assert controller.cache_manager.invalidate_called is False
      assert controller.cache_manager.all_scenes_called is False

      assert not mock_set_tracker.called
      controller.updateObjectClasses.assert_not_called()
      controller.updateCameras.assert_not_called()

  def test_handle_database_update_handles_exception_gracefully(self):
    controller = _make_controller()
    controller.updateSubscriptions = Mock(side_effect=RuntimeError("db unavailable"))
    mqtt_message = Mock()
    mqtt_message.payload = b"update"

    # Should not raise; handleDatabaseMessage catches and logs the exception
    controller.handleDatabaseMessage(None, None, mqtt_message)

    controller.updateSubscriptions.assert_called_once()
