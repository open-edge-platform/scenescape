# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import unittest
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

from controller.scene_controller import SceneController
from scene_common.mqtt import PubSub


class TestSceneControllerHandleMovingObjectMessage(unittest.TestCase):

  def test_forwards_topic_payload_and_timestamp(self):
    controller = SceneController.__new__(SceneController)
    controller._processIncomingDetection = Mock()
    message = SimpleNamespace(topic="test/topic", payload=b"payload")

    with patch("controller.scene_controller.time.time_ns", return_value=123456789):
      controller.handleMovingObjectMessage(None, None, message)

    controller._processIncomingDetection.assert_called_once_with(
        "test/topic", b"payload", 123456789
    )

  def test_passes_through_non_bytes_payload_and_topic(self):
    controller = SceneController.__new__(SceneController)
    controller._processIncomingDetection = Mock()
    payload = {"objects": [1, 2, 3]}
    message = SimpleNamespace(topic="scene/alpha", payload=payload)

    with patch("controller.scene_controller.time.time_ns", return_value=7):
      controller.handleMovingObjectMessage(object(), object(), message)

    controller._processIncomingDetection.assert_called_once_with(
        "scene/alpha", payload, 7
    )

  def test_reads_fresh_time_ns_on_each_invocation(self):
    controller = SceneController.__new__(SceneController)
    controller._processIncomingDetection = Mock()
    message = SimpleNamespace(topic="topic/a", payload=b"p")

    with patch("controller.scene_controller.time.time_ns", side_effect=[101, 202]):
      controller.handleMovingObjectMessage(None, None, message)
      controller.handleMovingObjectMessage(None, None, message)

    self.assertEqual(controller._processIncomingDetection.call_count, 2)
    self.assertEqual(
        controller._processIncomingDetection.call_args_list,
        [
            unittest.mock.call("topic/a", b"p", 101),
            unittest.mock.call("topic/a", b"p", 202),
        ],
    )

  def test_propagates_processing_exception(self):
    controller = SceneController.__new__(SceneController)
    controller._processIncomingDetection = Mock(side_effect=RuntimeError("boom"))
    message = SimpleNamespace(topic="topic/x", payload=b"payload")

    with patch("controller.scene_controller.time.time_ns", return_value=11):
      with self.assertRaisesRegex(RuntimeError, "boom"):
        controller.handleMovingObjectMessage(None, None, message)


class TestSceneControllerProcessMessageCore(unittest.TestCase):
  """Unit tests for _processMessageCore."""

  def setUp(self):
    """Initialize a minimal SceneController for testing."""
    self.controller = SceneController.__new__(SceneController)
    self.controller.rewrite_all_time = False
    self.controller.rewrite_bad_time = False
    self.controller.max_lag = 5.0
    self.controller._startup_time = 0  # Far in the past
    self.controller._startup_grace_sec = 1.0
    self.controller.schema_val = Mock()
    self.controller.cache_manager = Mock()
    self.controller._worker_route_log_count = 0

  def test_schema_validation_failure_returns_none(self):
    """Test that failed schema validation returns None."""
    self.controller.schema_val.validateMessage.return_value = False
    topic_str = "scenescape/data/camera/cam1"
    jdata = {"id": "cam1", "objects": {}}

    result = self.controller._processMessageCore(topic_str, jdata, 1000.0, 100, 200)

    self.assertIsNone(result)
    self.controller.schema_val.validateMessage.assert_called_once_with("detector", jdata)

  def test_updatecamera_skip_returns_none(self):
    """Test that updatecamera in jdata causes early return."""
    topic_str = "scenescape/data/camera/cam1"
    jdata = {"id": "cam1", "objects": {}, "updatecamera": True}

    result = self.controller._processMessageCore(topic_str, jdata, 1000.0, 100, 200)

    self.assertIsNone(result)

  def test_rewrite_all_time_updates_timestamp(self):
    """Test that rewrite_all_time overwrites jdata timestamp."""
    self.controller.rewrite_all_time = True
    self.controller.schema_val.validateMessage.return_value = True

    scene_mock = Mock()
    scene_mock.uid = "scene1"
    scene_mock.tracker.trackers = {"person": Mock()}
    scene_mock.processCameraData.return_value = True

    self.controller.cache_manager.sceneWithCameraID.return_value = scene_mock
    self.controller.cache_manager.refreshScenesForCamParams = Mock()

    topic_str = "scenescape/data/camera/cam1"
    jdata = {"id": "cam1", "objects": {"person": []}, "timestamp": "2020-01-01T00:00:00.000Z"}

    with patch("controller.scene_controller.get_iso_time", return_value="2026-06-24T12:00:00.000Z"):
      result = self.controller._processMessageCore(topic_str, jdata, 1000.0, 100, 200)

    self.assertIsNotNone(result)
    self.assertEqual(jdata["timestamp"], "2026-06-24T12:00:00.000Z")

  def test_lag_exceeds_max_lag_without_rewrite_bad_time_returns_none(self):
    """Test that excessive lag without rewrite_bad_time causes drop."""
    self.controller.rewrite_all_time = False
    self.controller.rewrite_bad_time = False
    self.controller.max_lag = 5.0
    self.controller.schema_val.validateMessage.return_value = True
    self.controller.cache_manager.refreshScenesForCamParams = Mock()

    topic_str = "scenescape/data/camera/cam1"
    jdata = {"id": "cam1", "objects": {}, "timestamp": "2020-01-01T00:00:00.000Z"}
    now = 1000.0

    with patch("controller.scene_controller.get_epoch_time", return_value=100.0):
      result = self.controller._processMessageCore(topic_str, jdata, now, 100, 200)

    self.assertIsNone(result)

  def test_lag_startup_grace_accepts_stale_frame(self):
    """Test that startup grace period accepts stale frames."""
    self.controller.rewrite_all_time = False
    self.controller.rewrite_bad_time = False
    self.controller.max_lag = 5.0
    self.controller._startup_grace_sec = 100.0  # Far in future
    self.controller.schema_val.validateMessage.return_value = True

    scene_mock = Mock()
    scene_mock.uid = "scene1"
    scene_mock.tracker.trackers = {"person": Mock()}
    scene_mock.processCameraData.return_value = True

    self.controller.cache_manager.sceneWithCameraID.return_value = scene_mock
    self.controller.cache_manager.refreshScenesForCamParams = Mock()

    topic_str = "scenescape/data/camera/cam1"
    jdata = {"id": "cam1", "objects": {"person": []}, "timestamp": "2020-01-01T00:00:00.000Z"}
    now = 1000.0

    with patch("controller.scene_controller.get_epoch_time", return_value=100.0):
      with patch("controller.scene_controller.get_iso_time", return_value="2026-06-24T12:00:00.000Z"):
        with patch("controller.scene_controller.time.time", return_value=0):
          result = self.controller._processMessageCore(topic_str, jdata, now, 100, 200)

    self.assertIsNotNone(result)
    self.assertEqual(jdata["timestamp"], "2026-06-24T12:00:00.000Z")

  def test_lag_rewrite_bad_time_overwrites_timestamp(self):
    """Test that rewrite_bad_time accepts stale frames and restamps them."""
    self.controller.rewrite_all_time = False
    self.controller.rewrite_bad_time = True
    self.controller.max_lag = 5.0
    self.controller._startup_grace_sec = 0.1
    self.controller.schema_val.validateMessage.return_value = True

    scene_mock = Mock()
    scene_mock.uid = "scene1"
    scene_mock.tracker.trackers = {"person": Mock()}
    scene_mock.processCameraData.return_value = True

    self.controller.cache_manager.sceneWithCameraID.return_value = scene_mock
    self.controller.cache_manager.refreshScenesForCamParams = Mock()

    topic_str = "scenescape/data/camera/cam1"
    jdata = {"id": "cam1", "objects": {"person": []}, "timestamp": "2020-01-01T00:00:00.000Z"}
    now = 1000.0

    with patch("controller.scene_controller.get_epoch_time", return_value=100.0):
      with patch("controller.scene_controller.get_iso_time", return_value="2026-06-24T12:00:00.000Z"):
        with patch("controller.scene_controller.time.time", return_value=1000):
          result = self.controller._processMessageCore(topic_str, jdata, now, 100, 200)

    self.assertIsNotNone(result)
    self.assertEqual(jdata["timestamp"], "2026-06-24T12:00:00.000Z")

  def test_child_scene_external_routing(self):
    """Test routing for external child scene data."""
    self.controller.schema_val.validateMessage.return_value = True
    self.controller.cache_manager.refreshScenesForCamParams = Mock()
    self.controller._handleChildSceneObject = Mock(return_value=(True, Mock(uid="parent_scene")))

    topic_str = "scenescape/data/external/child_id/detection"
    jdata = {"id": "cam1", "objects": {}, "timestamp": "2026-06-24T12:00:00.000Z"}

    with patch("controller.scene_controller.PubSub.parseTopic", return_value={"_topic_id": PubSub.DATA_EXTERNAL, "scene_id": "child_id", "thing_type": "detection"}):
      with patch("controller.scene_controller.get_epoch_time", return_value=1000.0):
        result = self.controller._processMessageCore(topic_str, jdata, 1000.0, 100, 200)

    self.assertIsNotNone(result)
    self.controller._handleChildSceneObject.assert_called_once()

  def test_camera_routing_success(self):
    """Test successful camera data processing."""
    self.controller.schema_val.validateMessage.return_value = True
    self.controller.cache_manager.refreshScenesForCamParams = Mock()

    scene_mock = Mock()
    scene_mock.uid = "scene1"
    scene_mock.tracker.trackers = {"person": Mock()}
    scene_mock.processCameraData.return_value = True

    self.controller.cache_manager.sceneWithCameraID.return_value = scene_mock

    topic_str = "scenescape/data/camera/cam1"
    jdata = {"id": "cam1", "objects": {"person": []}, "timestamp": "2026-06-24T12:00:00.000Z"}

    with patch("controller.scene_controller.get_epoch_time", return_value=1000.0):
      result = self.controller._processMessageCore(topic_str, jdata, 1000.0, 100, 200)

    self.assertIsNotNone(result)
    self.assertEqual(result["scene"], scene_mock)
    self.assertEqual(result["camera_id"], "cam1")
    self.assertEqual(result["detection_types"], ["person"])
    scene_mock.processCameraData.assert_called_once()

  def test_camera_routing_unknown_sender_returns_none(self):
    """Test that unknown camera sender causes drop."""
    self.controller.schema_val.validateMessage.return_value = True
    self.controller.cache_manager.refreshScenesForCamParams = Mock()
    self.controller.cache_manager.sceneWithCameraID.return_value = None

    topic_str = "scenescape/data/camera/unknown_cam"
    jdata = {"id": "unknown_cam", "objects": {}, "timestamp": "2026-06-24T12:00:00.000Z"}

    with patch("controller.scene_controller.get_epoch_time", return_value=1000.0):
      result = self.controller._processMessageCore(topic_str, jdata, 1000.0, 100, 200)

    self.assertIsNone(result)

  def test_empty_detection_types_populated_from_tracker(self):
    """Test that empty detection_types are populated from tracker."""
    self.controller.schema_val.validateMessage.return_value = True
    self.controller.cache_manager.refreshScenesForCamParams = Mock()

    scene_mock = Mock()
    scene_mock.uid = "scene1"
    scene_mock.tracker.trackers = {"person": Mock(), "car": Mock()}
    scene_mock.processCameraData.return_value = True

    self.controller.cache_manager.sceneWithCameraID.return_value = scene_mock

    topic_str = "scenescape/data/camera/cam1"
    jdata = {"id": "cam1", "objects": {}, "timestamp": "2026-06-24T12:00:00.000Z"}  # Empty detection types

    with patch("controller.scene_controller.get_epoch_time", return_value=1000.0):
      result = self.controller._processMessageCore(topic_str, jdata, 1000.0, 100, 200)

    self.assertIsNotNone(result)
    self.assertEqual(set(result["detection_types"]), {"person", "car"})
    self.assertEqual(set(jdata["objects"].keys()), {"person", "car"})

  def test_process_camera_data_failure_returns_none(self):
    """Test that failed processCameraData causes drop."""
    self.controller.schema_val.validateMessage.return_value = True
    self.controller.cache_manager.refreshScenesForCamParams = Mock()

    scene_mock = Mock()
    scene_mock.uid = "scene1"
    scene_mock.tracker.trackers = {"person": Mock()}
    scene_mock.processCameraData.return_value = False  # Failure

    self.controller.cache_manager.sceneWithCameraID.return_value = scene_mock

    topic_str = "scenescape/data/camera/cam1"
    jdata = {"id": "cam1", "objects": {"person": []}, "timestamp": "2026-06-24T12:00:00.000Z"}

    with patch("controller.scene_controller.get_epoch_time", return_value=1000.0):
      result = self.controller._processMessageCore(topic_str, jdata, 1000.0, 100, 200)

    self.assertIsNone(result)
    self.controller.cache_manager.invalidate.assert_called_once()

  def test_debug_fields_populated(self):
    """Test that debug profiling fields are set."""
    self.controller.schema_val.validateMessage.return_value = True
    self.controller.cache_manager.refreshScenesForCamParams = Mock()

    scene_mock = Mock()
    scene_mock.uid = "scene1"
    scene_mock.tracker.trackers = {"person": Mock()}
    scene_mock.processCameraData.return_value = True

    self.controller.cache_manager.sceneWithCameraID.return_value = scene_mock

    topic_str = "scenescape/data/camera/cam1"
    jdata = {"id": "cam1", "objects": {"person": []}, "timestamp": "2026-06-24T12:00:00.000Z"}
    now = 1000.0
    t_handler_start = 100
    t_parse = 200

    with patch("controller.scene_controller.get_epoch_time", return_value=now):
      result = self.controller._processMessageCore(topic_str, jdata, now, t_handler_start, t_parse)

    self.assertIsNotNone(result)
    self.assertEqual(jdata["debug_hmo_start_time"], now)
    self.assertEqual(jdata["_profile_handler_start"], t_handler_start)
    self.assertEqual(jdata["_profile_parse_done"], t_parse)


class TestSceneControllerDatabaseUpdates(unittest.TestCase):

  def test_handle_database_message_marks_cache_dirty_before_async_update(self):
    controller = SceneController.__new__(SceneController)
    controller.cache_manager = Mock()

    message = SimpleNamespace(payload=b"update")
    started_thread = Mock()

    with patch("controller.scene_controller.threading.Thread", return_value=started_thread) as thread_ctor:
      controller.handleDatabaseMessage(None, None, message)

    controller.cache_manager.markDirty.assert_called_once_with()
    thread_ctor.assert_called_once()
    started_thread.start.assert_called_once_with()

  def test_worker_handle_database_message_marks_cache_dirty_before_async_update(self):
    controller = SceneController.__new__(SceneController)
    controller.cache_manager = Mock()

    message = SimpleNamespace(payload=b"update")
    started_thread = Mock()

    with patch("controller.scene_controller.threading.Thread", return_value=started_thread) as thread_ctor:
      controller._workerHandleDatabaseMessage(None, None, message)

    controller.cache_manager.markDirty.assert_called_once_with()
    thread_ctor.assert_called_once()
    started_thread.start.assert_called_once_with()

  def test_worker_database_update_forces_refresh(self):
    controller = SceneController.__new__(SceneController)
    controller._db_update_lock = threading.Lock()
    controller.cache_manager = Mock()
    controller.scenes = [Mock()]
    controller.cache_manager.allScenes.return_value = [Mock()]
    controller.updateObjectClasses = Mock()

    controller._workerDatabaseUpdateAsync()

    controller.cache_manager.allScenes.assert_called_once_with(force_refresh=True)
    controller.updateObjectClasses.assert_called_once_with()
