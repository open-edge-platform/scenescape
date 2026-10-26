#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""SceneController wiring for PTZ pose consumption: gate, subscriptions, callbacks, clock."""

import json
import queue
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from controller.ptz import provider
from controller.ptz.config import MODE_ENFORCE, PTZSettings
from controller.scene_controller import SceneController
from scene_common.mqtt import PubSub
from scene_common.positioning_config import ConsumerPositioningConfig

CAMERA_ID = "ptz-cam-1"
RESOLVER = "positioning-a"
CONSUMER = ConsumerPositioningConfig(
  max_pose_age_s=0.5, max_clock_offset_s=0.05, max_detection_pipeline_latency_s=1.0,
  max_detection_timestamp_uncertainty_s=0.05)


def _settings(assignments=None):
  return PTZSettings(mode=MODE_ENFORCE, consumer=CONSUMER,
                     assignments={CAMERA_ID: RESOLVER} if assignments is None else assignments)


def _controller():
  controller = SceneController.__new__(SceneController)
  controller.schema_val = MagicMock()
  controller.schema_val.validateMessage.return_value = True
  controller.ntp_server = "ntp"
  controller.ntp_client = MagicMock()
  controller.last_time_sync = None
  controller.time_offset = 0
  controller.max_lag = 3600
  controller.rewrite_all_time = False
  controller.rewrite_bad_time = False
  controller.cache_manager = MagicMock()
  controller.cache_manager.sceneWithID.return_value = None
  controller.publishDetections = MagicMock()
  controller._moving_object_queue = queue.Queue()
  controller._moving_object_stop = threading.Event()
  return controller


class TestClock:
  def test_clock_is_not_synchronized_before_the_first_ntp_sync(self):
    controller = _controller()
    controller.ptz_settings = _settings()
    controller.last_time_sync = None
    assert controller._ptzClock()[1] is False

  @pytest.mark.parametrize("offset,expected", [(0.0, True), (0.05, True), (-0.05, True),
                                               (0.0501, False), (-1.0, False)])
  def test_clock_must_be_within_the_configured_offset(self, offset, expected):
    controller = _controller()
    controller.ptz_settings = _settings()
    controller.last_time_sync = 1.0
    controller.time_offset = offset
    with patch("controller.scene_controller.get_epoch_time", return_value=100.0):
      now_ns, synchronized = controller._ptzClock()
    assert synchronized is expected
    assert now_ns == int(round((100.0 + offset) * 1_000_000_000))


class TestFilter:
  def test_without_ptz_every_message_continues(self):
    controller = _controller()
    assert controller._ptzFilter(MagicMock(), CAMERA_ID, {}, 1.0) == (True, None)

  def test_filter_delegates_to_the_ingress(self):
    controller = _controller()
    controller.ptz_ingress = MagicMock()
    controller.ptz_ingress.filter.return_value = (False, None)
    scene, jdata = MagicMock(), {"id": CAMERA_ID}
    assert controller._ptzFilter(scene, CAMERA_ID, jdata, 2.0) == (False, None)
    controller.ptz_ingress.filter.assert_called_once_with(scene, CAMERA_ID, jdata, 2.0)


class TestCameraMessageGate:
  def _message(self):
    message = MagicMock()
    message.topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=CAMERA_ID)
    message.payload = json.dumps({
      "timestamp": "2026-01-01T00:00:00Z", "id": CAMERA_ID, "objects": {"person": []},
    }).encode("utf-8")
    return message

  def _scene(self):
    scene = MagicMock()
    scene.uid, scene.name = "scene-a", "Scene A"
    scene.processCameraData.return_value = True
    scene.tracker.getUniqueIDCount.return_value = 0
    scene.tracker.currentObjects.return_value = []
    return scene

  def _run(self, controller, scene):
    controller.cache_manager.sceneWithCameraID.return_value = scene
    with patch("controller.scene_controller.metrics") as metrics, \
        patch("controller.scene_controller.adjust_time", return_value=(0.0, None)), \
        patch("controller.scene_controller.get_epoch_time", return_value=100.0):
      controller._processMovingObjectMessage(None, None, self._message())
    return metrics

  def test_rejected_message_is_dropped_before_tracking_and_publishing(self):
    controller, scene = _controller(), self._scene()
    controller._ptzFilter = MagicMock(return_value=(False, None))
    metrics = self._run(controller, scene)
    scene.processCameraData.assert_not_called()
    controller.publishDetections.assert_not_called()
    controller.cache_manager.invalidate.assert_not_called()
    dropped = metrics.inc_dropped.call_args[0][0]
    assert dropped["reason"] == "ptz_dwell"

  def test_admitted_message_is_processed_with_its_pose_context(self):
    controller, scene, context = _controller(), self._scene(), object()
    controller._ptzFilter = MagicMock(return_value=(True, context))
    self._run(controller, scene)
    scene.processCameraData.assert_called_once()
    assert scene.processCameraData.call_args.kwargs["pose_context"] is context
    controller.publishDetections.assert_called()

  def test_message_without_a_context_uses_the_unchanged_static_call(self):
    controller, scene = _controller(), self._scene()
    self._run(controller, scene)
    scene.processCameraData.assert_called_once()
    assert "pose_context" not in scene.processCameraData.call_args.kwargs

  def test_gate_receives_the_scene_camera_and_message_time(self):
    controller, scene = _controller(), self._scene()
    controller._ptzFilter = MagicMock(return_value=(True, None))
    self._run(controller, scene)
    gate_args = controller._ptzFilter.call_args[0]
    assert gate_args[0] is scene and gate_args[1] == CAMERA_ID
    assert gate_args[2]["timestamp"] == "2026-01-01T00:00:00Z" and gate_args[3] == 100.0


class TestCallbacks:
  def _controller(self):
    controller = _controller()
    controller.ptz_registry = MagicMock()
    return controller

  def test_pose_and_status_messages_reach_the_registry(self):
    controller = self._controller()
    message = SimpleNamespace(topic="t", payload=b"{}")
    controller.handlePoseMessage(None, None, message)
    controller.handlePositioningStatusMessage(None, None, message)
    controller.ptz_registry.on_pose_message.assert_called_once_with("t", b"{}")
    controller.ptz_registry.on_status_message.assert_called_once_with("t", b"{}")

  def test_callback_errors_never_escape_to_the_mqtt_thread(self):
    controller = self._controller()
    controller.ptz_registry.on_pose_message.side_effect = RuntimeError("boom")
    controller.ptz_registry.on_status_message.side_effect = RuntimeError("boom")
    message = SimpleNamespace(topic="t", payload=b"{}")
    controller.handlePoseMessage(None, None, message)
    controller.handlePositioningStatusMessage(None, None, message)


class TestSubscriptions:
  def _camera(self, camera_id, ptz=True):
    return SimpleNamespace(
      cameraID=camera_id, ptz_calibration={"calibration_version": "v1"} if ptz else None)

  def _controller_with_scenes(self, assignments, *cameras):
    from controller.ptz.registry import PTZPoseRegistry
    controller = _controller()
    controller.ptz_registry = PTZPoseRegistry(
      _settings(assignments), controller.schema_val, lambda: (0, True))
    controller.scenes = [SimpleNamespace(uid="scene-a", cameras={c.cameraID: c for c in cameras})]
    return controller

  def test_no_ptz_means_no_extra_subscriptions(self):
    controller = _controller()
    need = set()
    controller._addPTZSubscriptions(need)
    assert need == set()

  def test_only_assigned_ptz_cameras_of_loaded_scenes_are_subscribed(self):
    controller = self._controller_with_scenes(
      {CAMERA_ID: RESOLVER, "elsewhere": RESOLVER}, self._camera(CAMERA_ID),
      self._camera("static-1", ptz=False), self._camera("unassigned"))
    need = set()
    controller._addPTZSubscriptions(need)
    topics = {topic for topic, _ in need}
    assert topics == {
      PubSub.formatTopic(PubSub.POSITIONING_POSE, source_id=CAMERA_ID),
      PubSub.formatTopic(PubSub.POSITIONING_STATUS, resolver_id=RESOLVER),
    }
    assert not any("+" in topic or "#" in topic for topic in topics)
    callbacks = {topic: callback for topic, callback in need}
    assert callbacks[PubSub.formatTopic(PubSub.POSITIONING_POSE, source_id=CAMERA_ID)] \
      == controller.handlePoseMessage
    assert callbacks[PubSub.formatTopic(PubSub.POSITIONING_STATUS, resolver_id=RESOLVER)] \
      == controller.handlePositioningStatusMessage

  def test_each_resolver_is_subscribed_once(self):
    controller = self._controller_with_scenes(
      {CAMERA_ID: RESOLVER, "ptz-2": RESOLVER}, self._camera(CAMERA_ID), self._camera("ptz-2"))
    need = set()
    controller._addPTZSubscriptions(need)
    assert len(need) == 3

  def test_a_removed_camera_is_unsubscribed_on_the_next_reconcile(self):
    controller = self._controller_with_scenes({CAMERA_ID: RESOLVER}, self._camera(CAMERA_ID))
    first = set()
    controller._addPTZSubscriptions(first)
    controller.scenes = [SimpleNamespace(uid="scene-a", cameras={})]
    second = set()
    controller._addPTZSubscriptions(second)
    assert len(first) == 2 and second == set()


class TestShutdown:
  def test_shutdown_releases_the_active_registry(self):
    controller = _controller()
    controller.ptz_registry = MagicMock()
    controller.external_source_pose_cache = MagicMock()
    controller.identity_claim_registry = MagicMock()
    controller._moving_object_worker = MagicMock()
    controller._moving_object_worker.is_alive.return_value = False
    provider.set_active_registry(controller.ptz_registry)
    try:
      controller.shutdown()
      assert provider.active_registry() is None
    finally:
      provider.set_active_registry(None)
