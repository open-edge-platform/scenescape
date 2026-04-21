#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import copy
import json
import threading
import time

import numpy as np

from scene_common import log
from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from scene_common.timestamp import get_iso_time

MAX_WAIT = 3


class ChildSceneTest:
  """Manages shared state and common operations for child-scene event tests.

  Attributes hold scene/region IDs, accumulated MQTT event messages, and the
  connection flag so that tests interact with instance state rather than
  module-level globals.
  """

  _FRAME_RATE = 10
  _NUM_PUBLISH_ITERATIONS = 3
  _PERSON = "person"
  _REGION = "region"
  _TRIPWIRE = "tripwire"

  # Object bounding-box y-sweep that produces world-coordinate trajectories
  # crossing both the ROI and the tripwire defined in setup_scenes().
  # Range matches FunctionalTest.getLocations() used by tc_tripwire_mqtt.py.
  _STEP = 0.02
  _OBJ_Y_LOCATIONS = np.concatenate([
    np.arange(-0.5, 0.6, _STEP),
    np.flip(np.arange(-0.5, 0.6, _STEP))[2:],
  ])

  def __init__(self, params):
    """Initialise helper with test parameters dict (from conftest ``params`` fixture)."""
    self.params = params

    # Scene / region IDs populated by setup_scenes()
    self.parent_id = None
    self.child_id = None
    self.roi_uid = None
    self.tripwire_uid = None
    self.sensor_uid = None

    # Tracks whether the child has already been unlinked (so teardown skips it)
    self.child_unlinked = False

    # MQTT connection flag
    self.connected = False

    # Accumulated event messages keyed by category
    self.parent_roi_events = []
    self.parent_tripwire_events = []
    self.parent_sensor_events = []
    self.child_roi_events = []
    self.child_tripwire_events = []
    self.child_sensor_events = []

    # Monotonic timestamp of the first event received into each accumulator
    self._first_received_at = {}

  def make_rest_client(self):
    """Return an authenticated :class:`RESTClient` instance."""
    rest_client = RESTClient(self.params["resturl"], rootcert=self.params["rootcert"])
    assert rest_client.authenticate(self.params["user"], self.params["password"])
    return rest_client

  def setup_scenes(self, rest_client, link=True):
    """Create parent scene, optionally link Demo as child, create ROI, tripwire, sensor.

    Populates instance attributes with all created UIDs.  When *link* is
    ``False`` the child is located but not linked to the parent, and
    :attr:`child_unlinked` is set so :meth:`teardown_scenes` skips the
    unlink step.

    @param    rest_client   An authenticated :class:`RESTClient`.
    @param    link          Whether to link the child scene to the parent (default ``True``).
    """
    # Create parent scene
    parent_scene = rest_client.createScene({"name": "parent_event_test"})
    assert parent_scene.statusCode == 201, (
      f"Expected 201 creating parent scene, got {parent_scene.statusCode}: {parent_scene.errors}")
    self.parent_id = parent_scene["uid"]
    log.info(f"[SETUP] Parent scene uid={self.parent_id}")

    # Locate the Demo child scene (it has a registered camera)
    scenes = rest_client.getScenes({"name": "Demo"})
    assert scenes["count"] > 0, "Demo scene not found – required for child camera"
    self.child_id = scenes["results"][0]["uid"]
    log.info(f"[SETUP] Child scene uid={self.child_id}")

    # Link Demo as child of parent (skipped when link=False)
    if link:
      res = rest_client.updateScene(self.child_id, {"parent": self.parent_id})
      assert res.statusCode == 200, (
        f"Expected 200 linking child to parent, got {res.statusCode}: {res.errors}")
      log.info("[SETUP] Linked child to parent")

      # Verify link
      res = rest_client.getChildScene({"parent": self.parent_id})
      assert res.statusCode == 200, (
        f"Expected 200 fetching child scenes, got {res.statusCode}: {res.errors}")
    else:
      self.child_unlinked = True
      log.info("[SETUP] Child NOT linked to parent (link=False)")

    # Create ROI in child scene – spans most of the floor plan
    roi_points = ((1.38, 5.94), (1.17, 0.8), (7.41, 0.83), (7.35, 6.01))
    roi_res = rest_client.createRegion({
      "scene": self.child_id,
      "name": "TestROI_child",
      "points": roi_points,
    })
    assert roi_res.statusCode == 201, (
      f"Expected 201 creating ROI, got {roi_res.statusCode}: {roi_res.errors}")
    self.roi_uid = roi_res["uid"]
    log.info(f"[SETUP] ROI uid={self.roi_uid}")

    # Create tripwire in child scene using the same centre-horizontal geometry
    # as tc_tripwire_mqtt.py (create_tripwire_by_ratio with x_ratio=0.8).
    # Demo scene: width=900 px, height=643 px, scale=100 px/m → cx=4.5, cy=3.215
    _demo_cx = 900 / (2 * 100)   # 4.5 m
    _demo_cy = 643 / (2 * 100)   # 3.215 m
    _demo_dx = _demo_cx * 0.8    # 3.6 m
    tw_res = rest_client.createTripwire({
      "scene": self.child_id,
      "name": "TestTripwire_child",
      "points": ((_demo_cx - _demo_dx, _demo_cy), (_demo_cx + _demo_dx, _demo_cy)),
    })
    assert tw_res.statusCode == 201, (
      f"Expected 201 creating tripwire, got {tw_res.statusCode}: {tw_res.errors}")
    self.tripwire_uid = tw_res["uid"]
    log.info(f"[SETUP] Tripwire uid={self.tripwire_uid}")

    # Create sensor in child scene
    sensor_res = rest_client.createSensor({
      "scene": self.child_id,
      "name": "TestSensor_child",
      "area": "circle",
      "radius": 3.21,
      "center": (4.5, 3.22),
    })
    assert sensor_res.statusCode == 201, (
      f"Expected 201 creating sensor, got {sensor_res.statusCode}: {sensor_res.errors}")
    self.sensor_uid = sensor_res["uid"]
    log.info(f"[SETUP] Sensor uid={self.sensor_uid}")

  def teardown_scenes(self, rest_client):
    """Remove created analytics objects, unlink child, and delete parent scene.

    All steps are attempted regardless of individual failures so that cleanup
    is as complete as possible.  Unexpected status codes are logged at ERROR
    level (including ``res.errors``) so failures are visible without masking
    the original test result.

    @param    rest_client   An authenticated :class:`RESTClient`.
    """
    for uid, label, fn in [
      (self.roi_uid, "ROI", rest_client.deleteRegion),
      (self.tripwire_uid, "Tripwire", rest_client.deleteTripwire),
      (self.sensor_uid, "Sensor", rest_client.deleteSensor),
    ]:
      if uid:
        res = fn(uid)
        if res.statusCode in (200, 204):
          log.info(f"[TEARDOWN] Deleted {label} uid={uid}: {res.statusCode}")
        else:
          log.error(f"[TEARDOWN] Failed to delete {label} uid={uid}: "
                    f"{res.statusCode} {res.errors}")

    if self.child_id and not self.child_unlinked:
      res = rest_client.deleteChildSceneLink(self.child_id)
      if res.statusCode == 200:
        log.info(f"[TEARDOWN] Unlinked child uid={self.child_id}: {res.statusCode}")
      else:
        log.error(f"[TEARDOWN] Failed to unlink child uid={self.child_id}: "
                  f"{res.statusCode} {res.errors}")

    if self.parent_id:
      res = rest_client.deleteScene(self.parent_id)
      if res.statusCode in (200, 204):
        log.info(f"[TEARDOWN] Deleted parent scene uid={self.parent_id}: {res.statusCode}")
      else:
        log.error(f"[TEARDOWN] Failed to delete parent scene uid={self.parent_id}: "
                  f"{res.statusCode} {res.errors}")

  def unlink_child(self, rest_client):
    """Unlink the child scene from its parent and record that it has been done.

    Calling this mid-test means :meth:`teardown_scenes` will skip the unlink
    step, avoiding a double-unlink error.

    @param    rest_client   An authenticated :class:`RESTClient`.
    """
    res = rest_client.deleteChildSceneLink(self.child_id)
    assert res.statusCode == 200, (
      f"Expected 200 deleting child link, got {res.statusCode}: {res.errors}")
    self.child_unlinked = True
    log.info(f"Unlinked child uid={self.child_id}: {res.statusCode}")

  def _subscribe_event(self, mqttc, label, region_type, scene_id, region_id):
    """Format an EVENT topic, subscribe, and log the subscription."""
    t = PubSub.formatTopic(PubSub.EVENT, region_type=region_type, event_type="+",
                           scene_id=scene_id, region_id=region_id)
    mqttc.subscribe(t)
    log.info(f"Subscribed {label}: {t}")

  def _on_connect(self, mqttc, obj, flags, rc):
    """Subscribe to all relevant event topics once connected."""
    if rc != 0:
      log.error(f"MQTT connect failed with rc={rc}")
      return

    log.info("MQTT connected")
    self.connected = True

    self._subscribe_event(mqttc, "child ROI events", self._REGION, self.child_id, self.roi_uid)
    self._subscribe_event(mqttc, "child tripwire events", self._TRIPWIRE, self.child_id, self.tripwire_uid)
    if self.sensor_uid:
      self._subscribe_event(mqttc, "child sensor events", self._REGION, self.child_id, self.sensor_uid)

    # Parent equivalents (republished by controller)
    self._subscribe_event(mqttc, "parent ROI events", self._REGION, self.parent_id, self.roi_uid)
    self._subscribe_event(mqttc, "parent tripwire events", self._TRIPWIRE, self.parent_id, self.tripwire_uid)
    if self.sensor_uid:
      self._subscribe_event(mqttc, "parent sensor events", self._REGION, self.parent_id, self.sensor_uid)

  def _on_message(self, mqttc, obj, msg):
    """Route incoming MQTT messages to the correct accumulator list."""
    topic = PubSub.parseTopic(msg.topic)
    if topic is None:
      return

    try:
      data = json.loads(msg.payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
      log.warning(f"Failed to decode MQTT payload on {msg.topic}: {exc}")
      return

    scene_id = topic.get("scene_id")
    region_id = topic.get("region_id")
    region_type = topic.get("region_type")

    if topic.get("_topic_id") != PubSub.EVENT:
      return

    if scene_id == self.child_id and region_id == self.roi_uid and region_type == self._REGION:
      self.child_roi_events.append(data)
      self._first_received_at.setdefault("child_roi_events", time.monotonic())
      log.info(f"Child ROI event received: {len(self.child_roi_events)} total")

    elif scene_id == self.child_id and region_id == self.tripwire_uid and region_type == self._TRIPWIRE:
      self.child_tripwire_events.append(data)
      self._first_received_at.setdefault("child_tripwire_events", time.monotonic())
      log.info(f"Child tripwire event received: {len(self.child_tripwire_events)} total")

    elif (scene_id == self.child_id and self.sensor_uid
          and region_id == self.sensor_uid and region_type == self._REGION):
      self.child_sensor_events.append(data)
      self._first_received_at.setdefault("child_sensor_events", time.monotonic())
      log.info(f"Child sensor event received: {len(self.child_sensor_events)} total")

    elif scene_id == self.parent_id and region_id == self.roi_uid and region_type == self._REGION:
      self.parent_roi_events.append(data)
      self._first_received_at.setdefault("parent_roi_events", time.monotonic())
      log.info(f"Parent ROI event received: {len(self.parent_roi_events)} total")

    elif scene_id == self.parent_id and region_id == self.tripwire_uid and region_type == self._TRIPWIRE:
      self.parent_tripwire_events.append(data)
      self._first_received_at.setdefault("parent_tripwire_events", time.monotonic())
      log.info(f"Parent tripwire event received: {len(self.parent_tripwire_events)} total")

    elif (scene_id == self.parent_id and self.sensor_uid
          and region_id == self.sensor_uid and region_type == self._REGION):
      self.parent_sensor_events.append(data)
      self._first_received_at.setdefault("parent_sensor_events", time.monotonic())
      log.info(f"Parent sensor event received: {len(self.parent_sensor_events)} total")

  def connect_mqtt(self):
    """Create a :class:`PubSub` client, attach callbacks, connect, and wait.

    @return   The connected :class:`PubSub` client.
    """
    client = PubSub(self.params["auth"], None, self.params["rootcert"],
                    self.params["broker_url"], self.params["broker_port"])
    client.onConnect = self._on_connect
    client.onMessage = self._on_message
    client.connect()
    client.loopStart()

    start = time.time()
    while not self.connected and time.time() - start < MAX_WAIT:
      time.sleep(0.5)
    assert self.connected, "MQTT client failed to connect within timeout"
    return client

  def _send_detections(self, client, obj_data, y_locations, stop_event):
    """Publish person detections through a y-sweep to trigger enter/exit events.

    Stops early if *stop_event* is set.  Called internally by
    :meth:`start_detection_thread`.

    @param    client        Connected :class:`PubSub` client.
    @param    obj_data      Detection payload dict (modified in-place).
    @param    y_locations   Iterable of bounding-box y values.
    @param    stop_event    :class:`threading.Event`, publishing stops when set.
    """
    cam_id = obj_data["id"]
    obj_data = copy.deepcopy(obj_data)
    topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=cam_id)
    for _ in range(self._NUM_PUBLISH_ITERATIONS):
      for y in y_locations:
        if stop_event.is_set():
          return
        obj_data["timestamp"] = get_iso_time()
        obj_data["objects"][self._PERSON][0]["bounding_box"]["y"] = float(y)
        obj_data["objects"][self._PERSON][0]["category"] = self._PERSON
        client.publish(topic, json.dumps(obj_data))
        time.sleep(1.0 / self._FRAME_RATE)

  def send_sensor_value(self, client, sensor_name, value):
    """Publish a singleton sensor reading to DATA_SENSOR topic.

    @param    client        Connected :class:`PubSub` client.
    @param    sensor_name   Sensor identifier string.
    @param    value         Sensor reading value.
    """
    message = {
      "timestamp": get_iso_time(),
      "id": sensor_name,
      "value": value,
    }
    topic = PubSub.formatTopic(PubSub.DATA_SENSOR, sensor_id=sensor_name)
    client.publish(topic, json.dumps(message))
    log.info(f"Published sensor value: id={sensor_name}, value={value}")

  def start_detection_thread(self, client, obj_data, stop_event, y_locations=None):
    """Spawn and start a daemon thread that publishes detections.

    @param    client        Connected :class:`PubSub` client.
    @param    obj_data      Detection payload dict.
    @param    stop_event    :class:`threading.Event` to stop publishing.
    @param    y_locations   Y-sweep values, defaults to :attr:`_OBJ_Y_LOCATIONS`.
    @return   The started :class:`threading.Thread`.
    """
    if y_locations is None:
      y_locations = self._OBJ_Y_LOCATIONS
    thread = threading.Thread(
      target=self._send_detections,
      args=(client, obj_data, y_locations, stop_event),
      daemon=True,
    )
    thread.start()
    return thread

  def first_received_at(self, attr):
    """Return the monotonic time at which the first event arrived in the named accumulator.

    @param    attr    Name of the list attribute (e.g. ``"child_roi_events"``).
    @return   Monotonic timestamp (float), or ``None`` if no events received yet.
    """
    return self._first_received_at.get(attr)

  def wait_for_events(self, attr, timeout=MAX_WAIT):
    """Block until at least one event is present in the named attribute.

    @param    attr      Name of the list attribute to poll (e.g. ``"parent_roi_events"``).
    @param    timeout   Maximum seconds to wait.
    @return   ``True`` if events arrived within *timeout*, ``False`` otherwise.
    """
    start = time.time()
    while time.time() - start < timeout:
      if getattr(self, attr):
        return True
      time.sleep(0.5)
    return False
