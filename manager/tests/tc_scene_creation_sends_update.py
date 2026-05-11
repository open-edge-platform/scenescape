#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Test that scene creation and updates trigger CMD_DATABASE update notifications.

When a scene is created or updated via REST API, the Manager publishes an "update"
message to scenescape/cmd/database so that the cache manager (or other services)
can synchronize with the new scene configuration.
"""

import threading
import uuid

from tests.functional import FunctionalTest
from http import HTTPStatus
from scene_common.rest_client import RESTClient
from scene_common.mqtt import PubSub


TEST_NAME = "NEX-SCENE-CRUD-MQTT-UPDATE"


class SceneCrudSendsUpdateTest(FunctionalTest):
  """Test that scene create and update operations publish CMD_DATABASE notifications."""

  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.rest = RESTClient(self.params["resturl"], rootcert=self.params["rootcert"])
    assert self.rest.authenticate(self.params["user"], self.params["password"])

  def _wait_for_update(self, pubsub, timeout=5):
    """Wait for CMD_DATABASE update notification."""
    db_received = threading.Event()
    db_topic = PubSub.formatTopic(PubSub.CMD_DATABASE)
    
    def on_db_update(mqttc, obj, msg):
      """Callback when database update notification arrives."""
      db_received.set()
    
    pubsub.addCallback(db_topic, on_db_update)
    received = db_received.wait(timeout)
    pubsub.removeCallback(db_topic)
    
    return received

  def runTest(self):
    """Test scene creation and update both trigger CMD_DATABASE notifications."""
    scene_name = f"test_scene_{uuid.uuid4().hex[:8]}"
    
    # Set up MQTT subscription
    pubsub = PubSub(
        self.params["auth"],
        None,
        self.params["rootcert"],
        self.params["broker_url"],
        self.params["broker_port"]
    )
    pubsub.connect()
    pubsub.loopStart()
    
    try:
      # Test 1: Scene creation triggers CMD_DATABASE update
      print("=" * 60)
      print("Test 1: Scene creation sends CMD_DATABASE update")
      print("=" * 60)
      
      scene_data = {
        "name": scene_name,
        "scale": 1000.0
      }
      create_response = self.rest.createScene(scene_data)
      assert create_response.statusCode in (HTTPStatus.OK, HTTPStatus.CREATED), \
        f"Failed to create scene: {create_response.errors}"
      scene_uid = create_response["uid"]
      print(f"Scene '{scene_name}' created with UID: {scene_uid}")
      
      # Wait for CMD_DATABASE notification on creation
      assert self._wait_for_update(pubsub, timeout=5), \
        "Timed out waiting for CMD_DATABASE notification after scene creation"
      print("✓ CMD_DATABASE update notification received for scene creation\n")
      
      # Test 2: Scene update triggers CMD_DATABASE update
      print("=" * 60)
      print("Test 2: Scene update sends CMD_DATABASE update")
      print("=" * 60)
      
      update_data = {
        "scale": 2000.0,
        "use_tracker": False
      }
      update_response = self.rest.updateScene(scene_uid, update_data)
      assert update_response.statusCode == HTTPStatus.OK, \
        f"Failed to update scene: {update_response.errors}"
      print(f"Scene '{scene_name}' updated with new scale and tracker settings")
      
      # Wait for CMD_DATABASE notification on update
      assert self._wait_for_update(pubsub, timeout=5), \
        "Timed out waiting for CMD_DATABASE notification after scene update"
      print("✓ CMD_DATABASE update notification received for scene update\n")
      
      # Cleanup: Delete the scene
      print("=" * 60)
      print("Cleanup: Deleting test scene")
      print("=" * 60)
      delete_response = self.rest.deleteScene(scene_uid)
      assert delete_response.statusCode in (HTTPStatus.OK, HTTPStatus.NO_CONTENT), \
        f"Failed to delete scene: {delete_response.errors}"
      print(f"Scene '{scene_name}' deleted successfully")
      
    finally:
      pubsub.loopStop()
    
    return True


def test_scene_crud_sends_update(request, record_xml_attribute):
  """Pytest entry point for scene CRUD update test."""
  test = SceneCrudSendsUpdateTest(TEST_NAME, request, record_xml_attribute)
  assert test.runTest()
  return
