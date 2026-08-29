#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for ChildSceneController hierarchy parent signalling."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from controller.child_scene_controller import ChildSceneController
from scene_common.mqtt import PubSub


def _build_child_controller():
  parent = SimpleNamespace(pubsub=MagicMock(), handleMovingObjectMessage=MagicMock(),
                           republishEvents=MagicMock())
  info = {
    'name': 'hier-child1',
    'remote_child_id': 'child-uid-1',
    'uid': 'link-uid-1',
    'host_name': 'child1-broker.scenescape.intel.com',
    'mqtt_username': 'user',
    'mqtt_password': 'pass',
  }
  with patch('controller.child_scene_controller.PubSub') as mock_pubsub_cls:
    client = MagicMock()
    mock_pubsub_cls.return_value = client
    child = ChildSceneController('/ca.pem', info, parent)
  return child, client, parent


class TestChildSceneControllerHierarchyParent:
  def test_on_connect_publishes_retained_attached_on_child_broker(self):
    child, client, parent = _build_child_controller()
    child.onChildConnect(client, None, None, 0)

    expected_topic = PubSub.formatTopic(
      PubSub.SYS_HIERARCHY_PARENT, scene_id='child-uid-1')
    client.publish.assert_any_call(
      expected_topic, PubSub.HIERARCHY_PARENT_ATTACHED, qos=1, retain=True)
    parent.pubsub.publish.assert_any_call(
      PubSub.formatTopic(PubSub.SYS_CHILDSCENE_STATUS, scene_id='child-uid-1'),
      'connected')
    assert child.connected is True

  def test_on_disconnect_publishes_retained_detached_on_child_broker(self):
    child, client, parent = _build_child_controller()
    child.connected = True
    child.onChildDisconnect(client, None, 0)

    expected_topic = PubSub.formatTopic(
      PubSub.SYS_HIERARCHY_PARENT, scene_id='child-uid-1')
    client.publish.assert_called_with(
      expected_topic, PubSub.HIERARCHY_PARENT_DETACHED, qos=1, retain=True)
    parent.pubsub.publish.assert_called_with(
      PubSub.formatTopic(PubSub.SYS_CHILDSCENE_STATUS, scene_id='child-uid-1'),
      'disconnected')
    assert child.connected is False

  def test_loop_stop_publishes_detached_when_still_connected(self):
    child, client, _parent = _build_child_controller()
    child.connected = True
    child.loopStop()

    expected_topic = PubSub.formatTopic(
      PubSub.SYS_HIERARCHY_PARENT, scene_id='child-uid-1')
    client.publish.assert_called_with(
      expected_topic, PubSub.HIERARCHY_PARENT_DETACHED, qos=1, retain=True)
    assert child.connected is False
    client.loopStop.assert_called_once()
