# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from controller.scene_controller import SceneController


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
