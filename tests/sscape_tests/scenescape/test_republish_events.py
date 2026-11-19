# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Controller parent-event republish edge cases."""

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import orjson
import pytest

from controller.scene_controller import SceneController
from scene_common.mqtt import PubSub


def _controller():
  ctrl = SceneController.__new__(SceneController)
  ctrl.cache_manager = MagicMock()
  ctrl.pubsub = MagicMock()
  return ctrl


class TestRepublishEvents:

  def _message(self, child_id, region_id='roi-1', payload=None):
    topic = PubSub.formatTopic(
      PubSub.EVENT, region_type='region', event_type='objects',
      scene_id=child_id, region_id=region_id)
    body = payload or {
      'objects': [{'id': 'o1', 'translation': [1.0, 2.0, 0.0]}],
      'entered': [],
      'exited': [],
      'metadata': {},
    }
    return SimpleNamespace(topic=topic, payload=orjson.dumps(body))

  def test_unknown_sender_returns_without_publish(self):
    ctrl = _controller()
    ctrl.cache_manager.sceneWithID.return_value = None
    ctrl.cache_manager.sceneWithRemoteChildID.return_value = None

    ctrl.republishEvents(None, None, self._message('child-1'))

    ctrl.pubsub.publish.assert_not_called()

  def test_unknown_parent_returns_without_publish(self):
    ctrl = _controller()
    child = SimpleNamespace(parent=None)
    ctrl.cache_manager.sceneWithID.return_value = child

    ctrl.republishEvents(None, None, self._message('child-1'))

    ctrl.pubsub.publish.assert_not_called()

  def test_success_republishes_on_parent_topic_with_child_metadata(self):
    ctrl = _controller()
    child = SimpleNamespace(parent='parent-1', name='Demo', cameraPose=object())
    parent = SimpleNamespace(uid='parent-1')
    ctrl.cache_manager.sceneWithID.side_effect = (
      lambda sid: child if sid == 'child-1' else parent)
    ctrl.transformObjectsinEvent = MagicMock()

    with patch('controller.scene_controller.applyChildTransform',
               side_effect=lambda meta, _pose: dict(meta)):
      ctrl.republishEvents(None, None, self._message('child-1'))

    ctrl.pubsub.publish.assert_called_once()
    topic, payload = ctrl.pubsub.publish.call_args[0]
    assert 'parent-1' in topic
    msg = orjson.loads(payload)
    assert msg['metadata']['from_child_scene'] == 'Demo'

  def test_malformed_json_is_dropped_without_raising(self):
    ctrl = _controller()
    message = SimpleNamespace(topic=self._message('child-1').topic, payload=b'{not json')

    ctrl.republishEvents(None, None, message)

    ctrl.cache_manager.sceneWithID.assert_not_called()
    ctrl.pubsub.publish.assert_not_called()

  def test_non_object_payload_is_dropped_without_raising(self):
    ctrl = _controller()

    ctrl.republishEvents(None, None, self._message('child-1', payload=[1, 2]))

    ctrl.pubsub.publish.assert_not_called()


class TestWrapCallback:

  def test_exception_in_callback_is_contained(self):
    pubsub = PubSub.__new__(PubSub)
    seen = []

    def callback(client, userdata, message):
      seen.append(client)
      raise ValueError("boom")

    wrapped = pubsub.wrapCallback(callback)

    assert wrapped(None, None, SimpleNamespace(topic='a/b')) is None
    assert seen == [pubsub]


class TestProcessMovingObjectMessageParsing:

  def _message(self, payload):
    topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id='cam-1')
    return SimpleNamespace(topic=topic, payload=payload)

  @pytest.mark.parametrize("payload", [
    b'{not json',
    b'\xff\xfe\x00',
    b'[1, 2, 3]',
    b'"text"',
    b'42',
    b'null',
  ])
  def test_bad_payload_is_dropped_and_next_valid_message_processed(self, payload):
    ctrl = _controller()
    ctrl.schema_val = MagicMock()
    ctrl.schema_val.validateMessage.return_value = False
    valid = {'id': 'cam-1', 'timestamp': '2026-01-01T00:00:00.000Z', 'objects': {}}

    with patch('controller.scene_controller.metrics'):
      ctrl._processMovingObjectMessage(None, None, self._message(payload))
      ctrl.schema_val.validateMessage.assert_not_called()
      ctrl.cache_manager.sceneWithID.assert_not_called()

      ctrl._processMovingObjectMessage(None, None, self._message(orjson.dumps(valid)))

    ctrl.schema_val.validateMessage.assert_called_once_with('detector', valid)


def _lockIsFreeForOtherThread(condition):
  """Condition uses an RLock, so only another thread can detect a leaked lock."""
  result = []

  def attempt():
    acquired = condition.acquire(timeout=0.5)
    if acquired:
      condition.release()
    result.append(acquired)

  thread = threading.Thread(target=attempt)
  thread.start()
  thread.join()
  return result[0]


class TestMalformedChunkReleasesCondition:

  def test_malformed_chunk_releases_condition(self):
    pubsub = PubSub.__new__(PubSub)
    pubsub.receivedCondition = threading.Condition()

    wrapped = pubsub.wrapCallback(pubsub.chunkReceived)
    wrapped(None, None, SimpleNamespace(topic='t', payload=b'\x00'))

    assert _lockIsFreeForOtherThread(pubsub.receivedCondition)
