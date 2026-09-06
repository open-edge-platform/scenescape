# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Controller parent-event republish edge cases."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import orjson

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
