#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import copy
import json
import math
import threading
import time

from scene_common.mqtt import PubSub
from scene_common import log
from scene_common.timestamp import get_iso_time


class RetrackTest:

  FRAME_RATE = 10
  MAX_WAIT = 5
  NUM_PUBLISH_ITERATIONS = 5

  def __init__(self, params):
    """! Initialise an empty helper bound to the given connection parameters.

    @param    params    Dict of functional-test connection parameters from
                        the conftest fixture.
    """
    self.params = params
    self.parent_id = None
    self.child_id = None
    self._lock = threading.Lock()
    self.parent_received = []
    self.child_received = []

  def on_message(self, mqttc, obj, msg):
    """! Default onMessage callback, routes regulated messages into
    parent_received or child_received based on scene_id.

    @param    mqttc   MQTT client object.
    @param    obj     Private user data (unused).
    @param    msg     MQTTMessage instance.
    """
    topic = PubSub.parseTopic(msg.topic)
    if topic is None:
      return
    try:
      data = json.loads(msg.payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
      log.warning(f"Failed to decode MQTT payload on {msg.topic}: {exc}")
      return
    obj_count = len(data.get('objects', []))
    if obj_count == 0:
      return
    with self._lock:
      if topic.get('scene_id') == self.parent_id:
        log.info(f"Parent regulated: {obj_count} objects")
        self.parent_received.append(data)
      elif topic.get('scene_id') == self.child_id:
        log.info(f"Child regulated: {obj_count} objects")
        self.child_received.append(data)

  def setup_scenes(self, rest_client):
    """! Create a fresh parent scene and link the existing Demo scene as
    child with retrack=True (default).

    @param    rest_client     An authenticated RESTClient instance.
    """
    parent_scene = rest_client.createScene({'name': "retrack_parent"})
    assert parent_scene.statusCode == 201, \
      f"Failed to create parent scene: {parent_scene.statusCode}"
    self.parent_id = parent_scene['uid']
    log.info(f"Created parent scene: {self.parent_id}")

    scenes = rest_client.getScenes({'name': 'Demo'})
    assert scenes['count'] > 0, "Demo scene not found – required for retrack tests"
    child_scene = scenes['results'][0]
    self.child_id = child_scene['uid']
    log.info(f"Using Demo as child scene: {self.child_id}")

    res = rest_client.updateScene(self.child_id, {'parent': self.parent_id})
    assert res.statusCode == 200, \
      f"Failed to link child to parent: {res.statusCode}"

    child_links = rest_client.getChildScene({'parent': self.parent_id})
    assert child_links.statusCode == 200 and child_links['count'] == 1, \
      "Child-parent link not found after linking"

  def teardown_scenes(self, rest_client):
    """! Unlink the child scene and delete the parent scene created for
    the test.  The Demo child scene is a fixture and is never deleted.

    @param    rest_client     An authenticated RESTClient instance.
    """
    if self.child_id and self.parent_id:
      try:
        res = rest_client.deleteChildSceneLink(self.child_id)
        errors = getattr(res, 'errors', None)
        if res.statusCode in (200, 204):
          log.info(f"[TEARDOWN] Unlinked child uid={self.child_id}: {res.statusCode}")
        else:
          log.error(
            f"[TEARDOWN] Failed to unlink child uid={self.child_id}: "
            f"status={res.statusCode}, errors={errors}"
          )
      except Exception as exc:
        log.error(f"[TEARDOWN] Exception unlinking child uid={self.child_id}: {exc}")
    if self.parent_id:
      try:
        res = rest_client.deleteScene(self.parent_id)
        errors = getattr(res, 'errors', None)
        if res.statusCode in (200, 204):
          log.info(f"[TEARDOWN] Deleted parent scene uid={self.parent_id}: {res.statusCode}")
        else:
          log.error(
            f"[TEARDOWN] Failed to delete parent scene uid={self.parent_id}: "
            f"status={res.statusCode}, errors={errors}"
          )
      except Exception as exc:
        log.error(f"[TEARDOWN] Exception deleting parent scene uid={self.parent_id}: {exc}")

  def _await_db_notification(self, rest_fn):
    """! Subscribe to CMD_DATABASE, call rest_fn(), then assert the
    notification arrives confirming the controller loaded the change.

    @param    rest_fn     Zero-argument callable that performs the REST update.
    """
    db_received = threading.Event()
    subscribed = threading.Event()
    db_topic = PubSub.formatTopic(PubSub.CMD_DATABASE)

    def _on_db(mqttc, obj, msg):
      db_received.set()

    def _on_connected(mqttc, obj, flags, rc):
      if rc == 0:
        mqttc.addCallback(db_topic, _on_db)

    def _on_subscribed(mqttc, obj, mid, granted_qos):
      subscribed.set()

    tmp = PubSub(self.params["auth"], None, self.params["rootcert"],
                 self.params["broker_url"], self.params["broker_port"])
    tmp.onConnect = _on_connected
    tmp.onSubscribe = _on_subscribed
    tmp.connect()
    tmp.loopStart()
    assert subscribed.wait(self.MAX_WAIT), \
      "Temporary MQTT client failed to subscribe to CMD_DATABASE within timeout"
    try:
      rest_fn()
      assert db_received.wait(self.MAX_WAIT), \
        "Timed out waiting for CMD_DATABASE notification"
    finally:
      tmp.loopStop()

  def set_retrack(self, rest_client, value):
    """! Update the retrack flag on the child scene link and wait for the
    CMD_DATABASE notification confirming the controller has loaded the change.

    @param    rest_client     An authenticated RESTClient instance.
    @param    value           Boolean value for the retrack field.
    """
    def _update():
      res = rest_client.updateChildScene(self.child_id, {'retrack': value})
      assert res.statusCode == 200, \
        f"Failed to set retrack={value}: {res.statusCode}"
      log.info(f"Set retrack={value} on child scene {self.child_id}")
      verify = rest_client.getChildScene({'parent': self.parent_id})
      assert verify.statusCode == 200, \
        f"Failed to read back child scene link after setting retrack={value}"
      assert verify['count'] > 0, \
        f"No child scene link found when verifying retrack={value} (parent={self.parent_id})"
      actual = verify['results'][0]['retrack']
      log.info(f"Verify child link retrack value: {actual}")
      assert actual == value, \
        f"retrack mismatch: expected {value}, got {actual}"
    self._await_db_notification(_update)

  def set_external_rate(self, rest_client, rate):
    """! Update external_update_rate on the child scene and wait for the
    CMD_DATABASE notification confirming the controller has loaded the change.

    @param    rest_client     An authenticated RESTClient instance.
    @param    rate            Float Hz value for external_update_rate.
    """
    def _update():
      res = rest_client.updateScene(self.child_id, {'external_update_rate': rate})
      assert res.statusCode == 200, \
        f"Failed to set external_update_rate={rate}: {res.statusCode}"
      log.info(f"Set external_update_rate={rate} on scene {self.child_id}")
    self._await_db_notification(_update)

  def make_client(self, topics=None, on_msg=None):
    """! Create and start an MQTT PubSub client, subscribe to *topics* on
    connect, and block until the broker confirms connection.

    Defaults to subscribing to DATA_REGULATED for both parent and child
    scenes with self.on_message as the callback when omitted.

    @param    topics    List of MQTT topic strings.  Defaults to
                        DATA_REGULATED for parent_id and child_id.
    @param    on_msg    onMessage callback.  Defaults to self.on_message.
    @return             Connected PubSub instance.
    """
    if topics is None:
      topics = [
        PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=self.parent_id),
        PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=self.child_id),
      ]
    if on_msg is None:
      on_msg = self.on_message
    connected_event = threading.Event()

    def _on_connect(mqttc, obj, flags, rc):
      if rc == 0:
        for t in topics:
          mqttc.subscribe(t)
          log.info(f"Subscribed: {t}")
        connected_event.set()

    client = PubSub(self.params["auth"], None, self.params["rootcert"],
                    self.params["broker_url"], self.params["broker_port"])
    client.onConnect = _on_connect
    client.onMessage = on_msg
    client.connect()
    client.loopStart()
    assert connected_event.wait(self.MAX_WAIT), \
      "MQTT client failed to connect within timeout"
    return client

  def wait_for_messages(self, timeout=None, require_parent=True, require_child=True):
    """! Block until at least one message with objects has arrived on the
    expected topics, or timeout expires.

    @param    timeout         Maximum seconds to wait.  Defaults to MAX_WAIT.
    @param    require_parent  Assert that parent received objects if True.
    @param    require_child   Assert that child received objects if True.
    """
    if timeout is None:
      timeout = self.MAX_WAIT
    start = time.time()
    while time.time() - start < timeout:
      with self._lock:
        parent_ok = (not require_parent) or len(self.parent_received) > 0
        child_ok = (not require_child) or len(self.child_received) > 0
      if parent_ok and child_ok:
        return
      time.sleep(0.5)
    with self._lock:
      parent_count = len(self.parent_received)
      child_count = len(self.child_received)
    if require_parent:
      assert parent_count > 0, \
        f"Timed out after {timeout}s: no objects on parent regulated topic"
    if require_child:
      assert child_count > 0, \
        f"Timed out after {timeout}s: no objects on child regulated topic"

  def reset(self):
    """! Clear both accumulators atomically under the lock."""
    with self._lock:
      self.parent_received.clear()
      self.child_received.clear()

  def snapshot_received(self):
    """! Return a frozen (parent_list, child_list) copy under the lock.

    @return   Tuple of (list, list) – point-in-time snapshots of
              parent_received and child_received.
    """
    with self._lock:
      return list(self.parent_received), list(self.child_received)

  @staticmethod
  def collect_object_ids(messages):
    """! Return the set of object id values from a list of regulated messages.

    @param    messages  List of decoded regulated-data message dicts.
    @return             Set of id strings found in 'objects' lists.
    """
    ids = set()
    for msg in messages:
      for obj in msg.get('objects', []):
        if 'id' in obj:
          ids.add(obj['id'])
    return ids

  @staticmethod
  def publish_data(obj_data, client, obj_category="person"):
    """! Publish simulated object detection data to a camera's MQTT topic.

    @param    obj_data        The object data fixture containing camera id and objects.
    @param    client          The MQTT PubSub client.
    @param    obj_category    The object category to publish (default: "person").
    """
    obj_data = copy.deepcopy(obj_data)
    cam_id = obj_data["id"]
    topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=cam_id)
    for iteration in range(RetrackTest.NUM_PUBLISH_ITERATIONS):
      for i in range(5):
        obj_data["timestamp"] = get_iso_time()
        obj_data["objects"][obj_category][0]["bounding_box"]["y"] = 100 + (i * 20)
        obj_data["objects"][obj_category][0]["category"] = obj_category
        client.publish(topic, json.dumps(obj_data))
        log.info(
          f"Published object via camera {cam_id}: y={100 + (i * 20)} "
          f"(iter {iteration})")
        time.sleep(1.0 / RetrackTest.FRAME_RATE)

  @staticmethod
  def publish_timed(obj_data, client, rate, duration):
    """! Publish camera detections at *rate* Hz for *duration* seconds.

    @param    obj_data    The object data fixture containing camera id and objects.
    @param    client      The MQTT PubSub client.
    @param    rate        Publish rate in Hz.
    @param    duration    Duration in seconds.
    """
    obj_data = copy.deepcopy(obj_data)
    cam_id = obj_data["id"]
    topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=cam_id)
    end = time.time() + duration
    i = 0
    while time.time() < end:
      obj_data["timestamp"] = get_iso_time()
      obj_data["objects"]["person"][0]["bounding_box"]["y"] = 100 + (i % 5) * 20
      obj_data["objects"]["person"][0]["category"] = "person"
      client.publish(topic, json.dumps(obj_data))
      time.sleep(1.0 / rate)
      i += 1

  @staticmethod
  def assert_valid_translation(tr, label):
    """! Assert that *tr* is a list of exactly three finite numeric values.

    @param    tr      The translation value to validate.
    @param    label   Human-readable label used in assertion messages.
    """
    assert isinstance(tr, (list, tuple)), \
      f"{label} 'translation' must be a list or tuple, got {type(tr).__name__}: {tr!r}"
    assert len(tr) == 3, \
      f"{label} 'translation' must have 3 elements, got {len(tr)}"
    for v in tr:
      assert isinstance(v, (int, float)), \
        f"{label} translation element not numeric: {v}"
      assert math.isfinite(v), \
        f"{label} translation element is not finite (NaN/Inf): {v}"
