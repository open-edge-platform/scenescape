#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Remote child linking helpers for multi-controller hierarchy tests."""

import json
import threading
import time

from scene_common import log
from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient


def load_controller_mqtt_creds(auth_path):
  """Return (username, password) from a controller.auth JSON file."""
  with open(auth_path, encoding="utf-8") as auth_file:
    data = json.load(auth_file)
  return data["user"], data["password"]


def make_mqtt_client(params, topics=None, on_message=None, timeout=10):
  """Connect a PubSub client using *params* and optionally subscribe to *topics*."""
  connected = threading.Event()

  def _on_connect(mqttc, obj, flags, rc):
    if rc == 0:
      for topic in topics or []:
        mqttc.subscribe(topic)
        log.info(f"Subscribed: {topic}")
      connected.set()

  client = PubSub(
    params["auth"], None, params["rootcert"],
    params["broker_url"], params["broker_port"])
  client.onConnect = _on_connect
  if on_message is not None:
    client.onMessage = on_message
  client.connect()
  client.loopStart()
  assert connected.wait(timeout), \
    f"MQTT connect failed for {params['broker_url']}:{params['broker_port']}"
  return client


class RemoteHierarchySetup:
  """Link two remote children to a parent scene and manage teardown."""

  MAX_WAIT = 30

  def __init__(self, params_parent, params_child1, params_child2):
    self.params_parent = params_parent
    self.params_child1 = params_child1
    self.params_child2 = params_child2
    self.parent_id = None
    self.child1_id = None
    self.child2_id = None
    self.child1_camera_id = "camera1"
    self.child2_camera_id = "camera1"
    self.link1_id = None
    self.link2_id = None
    self._rest_parent = None
    self._lock = threading.Lock()
    self.parent_received = []

  def setup(self, retrack=True, separate_children=True):
    """Create parent scene and remote-link per-child scenes.

    Each child stack loads the same fixture Demo UUID, but ``remote_child_id``
    is globally unique on the parent. Create a dedicated scene (+ camera1) on
    each child so the remote links do not collide.

    When *separate_children* is True, child2 is placed far from child1 in parent
    space so geometry alone cannot merge them. Shared-DB merge tests should pass
    False so ReID (or proximity) can converge to one parent ID.
    """
    self._rest_parent = RESTClient(
      self.params_parent["resturl"], rootcert=self.params_parent["rootcert"])
    assert self._rest_parent.authenticate(
      self.params_parent["user"], self.params_parent["password"]), (
      f"parent REST auth failed for {self.params_parent['resturl']}")

    rest_c1 = RESTClient(
      self.params_child1["resturl"], rootcert=self.params_child1["rootcert"])
    assert rest_c1.authenticate(
      self.params_child1["user"], self.params_child1["password"])
    rest_c2 = RESTClient(
      self.params_child2["resturl"], rootcert=self.params_child2["rootcert"])
    assert rest_c2.authenticate(
      self.params_child2["user"], self.params_child2["password"])

    parent = self._rest_parent.createScene({
      "name": "hier_reid_parent",
      "regulated_rate": 10,
    })
    assert parent.statusCode == 201, \
      f"create parent failed: {parent.statusCode} {getattr(parent, 'errors', None)}"
    self.parent_id = parent["uid"]

    # Both child stacks share the same fixture Demo UUID; remote_child_id must
    # be unique on the parent, so create a dedicated scene+camera on each child.
    self.child1_id = self._create_child_scene_with_camera(
      rest_c1, "hier_child1", "camera1", move_demo=True)
    self.child1_camera_id = "camera1"
    self.child2_id = self._create_child_scene_with_camera(
      rest_c2, "hier_child2", "camera1", move_demo=True)
    self.child2_camera_id = "camera1"
    log.info(f"Parent={self.parent_id} child1={self.child1_id} child2={self.child2_id}")

    user, password = load_controller_mqtt_creds(self.params_parent["auth"])
    # Place child2 far from child1 when testing that ReID must NOT merge.
    child2_translation = (100.0, 100.0, 0.0) if separate_children else (0.0, 0.0, 0.0)
    self.link1_id = self._link_remote(
      self.child1_id, "hier-child1",
      self.params_child1["docker_broker_host"], user, password, retrack,
      translation=(0.0, 0.0, 0.0))
    self.link2_id = self._link_remote(
      self.child2_id, "hier-child2",
      self.params_child2["docker_broker_host"], user, password, retrack,
      translation=child2_translation)

    self._wait_child_status(self.child1_id)
    self._wait_child_status(self.child2_id)
    return self

  @staticmethod
  def _create_child_scene_with_camera(rest, scene_name, camera_id, move_demo=True):
    """Create a unique scene; optionally move Demo camera1 onto it."""
    demos = rest.getScenes({"name": "Demo"})
    assert demos.get("count", 0) > 0, "Demo scene missing on child stack"
    demo = demos["results"][0]
    demo_uid = demo["uid"]
    demo_scale = demo.get("scale") or 1000

    scene = rest.createScene({"name": scene_name, "scale": demo_scale})
    assert scene.statusCode == 201, \
      f"create child scene {scene_name} failed: {scene.statusCode} " \
      f"{getattr(scene, 'errors', None)}"
    scene_uid = scene["uid"]

    if not move_demo:
      created = rest.createCamera({
        "name": camera_id,
        "sensor_id": camera_id,
        "scene": scene_uid,
      })
      assert created.statusCode in (200, 201), \
        f"create camera {camera_id} on {scene_name} failed: {created.statusCode} " \
        f"{getattr(created, 'errors', None)}"
      time.sleep(3)
      return scene_uid

    demo_cams = rest.getCameras({"name": "camera1"})
    assert demo_cams.get("count", 0) > 0, "Demo camera1 not found on child stack"
    template = None
    for cam in demo_cams["results"]:
      if cam.get("scene") == demo_uid:
        template = cam
        break
    if template is None:
      template = demo_cams["results"][0]

    moved = rest.updateCamera(template["uid"], {
      "name": template.get("name", "camera1"),
      "scene": scene_uid,
    })
    assert moved.statusCode in (200, 201), \
      f"move camera1 onto {scene_name} failed: {moved.statusCode} " \
      f"{getattr(moved, 'errors', None)}"
    time.sleep(3)
    return scene_uid

  def _link_remote(self, remote_id, name, host_name, user, password, retrack,
                   translation=(0.0, 0.0, 0.0)):
    # Euler layout stores translation in transform1..3 (see ChildScene.update paths).
    tx, ty, tz = translation
    res = self._rest_parent.createChildScene({
      "child_type": "remote",
      "parent": self.parent_id,
      "remote_child_id": remote_id,
      "child_name": name,
      "host_name": host_name,
      "mqtt_username": user,
      "mqtt_password": password,
      "retrack": retrack,
      "transform_type": "euler",
      "transform1": float(tx),
      "transform2": float(ty),
      "transform3": float(tz),
      "transform4": 0.0,
      "transform5": 0.0,
      "transform6": 0.0,
      "transform7": 1.0,
      "transform8": 1.0,
      "transform9": 1.0,
    })
    assert res.statusCode == 201, \
      f"createChildScene({name}) failed: {res.statusCode} {getattr(res, 'errors', None)}"
    log.info(
      f"Linked remote child {name} uid={res['uid']} host={host_name} "
      f"translation={translation} transform={res.get('transform')} "
      f"transform_type={res.get('transform_type')}")
    time.sleep(1)
    return res["uid"]

  def _wait_child_status(self, remote_child_id):
    topic = PubSub.formatTopic(PubSub.SYS_CHILDSCENE_STATUS, scene_id=remote_child_id)
    connected = threading.Event()

    def _on_msg(mqttc, obj, msg):
      payload = msg.payload.decode("utf-8")
      log.info(f"Child status {remote_child_id}: {payload}")
      if payload == "connected":
        connected.set()

    def _on_connect(mqttc, obj, flags, rc):
      if rc == 0:
        mqttc.subscribe(topic)
        mqttc.publish(topic, "isConnected")

    client = PubSub(
      self.params_parent["auth"], None, self.params_parent["rootcert"],
      self.params_parent["broker_url"], self.params_parent["broker_port"])
    client.onConnect = _on_connect
    client.onMessage = _on_msg
    client.connect()
    client.loopStart()
    try:
      assert connected.wait(self.MAX_WAIT), \
        f"Remote child {remote_child_id} did not report connected within {self.MAX_WAIT}s"
    finally:
      client.loopStop()

  def set_retrack(self, link_id, value):
    res = self._rest_parent.updateChildScene(link_id, {"retrack": value})
    assert res.statusCode == 200, \
      f"set retrack failed: {res.statusCode} {getattr(res, 'errors', None)}"
    time.sleep(1)

  def on_parent_regulated(self, mqttc, obj, msg):
    topic = PubSub.parseTopic(msg.topic)
    if topic is None or topic.get("scene_id") != self.parent_id:
      return
    try:
      data = json.loads(msg.payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
      log.warning(f"Failed to decode parent regulated payload: {exc}")
      return
    if not data.get("objects"):
      return
    with self._lock:
      self.parent_received.append(data)
      log.info(f"Parent regulated: {len(data['objects'])} object(s)")

  def make_parent_client(self):
    """Subscribe to parent DATA_REGULATED and accumulate object messages."""
    topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=self.parent_id)
    return make_mqtt_client(
      self.params_parent, topics=[topic], on_message=self.on_parent_regulated)

  def make_child_client(self, role):
    """Return an MQTT client bound to child1 or child2 broker params."""
    params = self.params_child1 if role == "child1" else self.params_child2
    return make_mqtt_client(params)

  def reset_parent_received(self):
    with self._lock:
      self.parent_received.clear()

  def snapshot_parent_ids(self):
    """Return the set of object ids seen on parent regulated messages."""
    with self._lock:
      messages = list(self.parent_received)
    ids = set()
    for msg in messages:
      for obj in msg.get("objects", []):
        if "id" in obj:
          ids.add(obj["id"])
    return ids

  def snapshot_recent_parent_ids(self, last_n=10):
    """Return object ids from the most recent parent regulated messages."""
    with self._lock:
      messages = list(self.parent_received)[-last_n:]
    ids = set()
    for msg in messages:
      for obj in msg.get("objects", []):
        if "id" in obj:
          ids.add(obj["id"])
    return ids

  def snapshot_recent_parent_objects(self, last_n=10):
    """Return (id, translation) tuples from the most recent parent messages."""
    with self._lock:
      messages = list(self.parent_received)[-last_n:]
    objects = []
    for msg in messages:
      for obj in msg.get("objects", []):
        objects.append({
          "id": obj.get("id"),
          "translation": obj.get("translation"),
        })
    return objects

  def wait_for_parent_objects(self, timeout=15, min_messages=1):
    deadline = time.time() + timeout
    while time.time() < deadline:
      with self._lock:
        count = len(self.parent_received)
      if count >= min_messages:
        return
      time.sleep(0.5)
    with self._lock:
      count = len(self.parent_received)
    assert count >= min_messages, \
      f"Timed out waiting for parent objects: got {count}, need {min_messages}"

  def teardown(self):
    if self._rest_parent is None:
      return
    for link_id in (self.link1_id, self.link2_id):
      if link_id:
        try:
          self._rest_parent.deleteChildSceneLink(link_id)
        except Exception as exc:
          log.error(f"teardown link {link_id}: {exc}")
    if self.parent_id:
      try:
        self._rest_parent.deleteScene(self.parent_id)
      except Exception as exc:
        log.error(f"teardown parent {self.parent_id}: {exc}")
    for params, scene_id in (
        (self.params_child1, self.child1_id),
        (self.params_child2, self.child2_id),
    ):
      if not scene_id:
        continue
      try:
        rest = RESTClient(params["resturl"], rootcert=params["rootcert"])
        if rest.authenticate(params["user"], params["password"]):
          rest.deleteScene(scene_id)
      except Exception as exc:
        log.error(f"teardown child scene {scene_id}: {exc}")
