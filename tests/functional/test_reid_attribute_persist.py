# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Functional tests for the ReID persistent-attribute (gender) feature.

Detections are injected as synthetic MQTT messages so gender labels and confidence values
are deterministic, then asserted against VDMS descriptors, the regulated scene
output, and the scene controller log.
"""

import base64
import json
import struct
import threading
import time

import numpy as np
import pytest

from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from scene_common.timestamp import get_iso_time

from controller.vdms_adapter import VDMSDatabase, vdms
from tests.utils.log import get_logger
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import REID_NO_VIDEO

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
    profile=REID_NO_VIDEO,
    auth=AUTH_CONTROLLER
)

REID_DIMENSIONS = 256
REID_MODEL = "person-reidentification-retail-0287"
VDMS_HOST = "vdms.scenescape.intel.com"
SCHEMA_NAME = "reid_vector"


def make_embedding(seed=None):
  """Return a deterministic-ish 256-float ReID embedding."""
  rng = np.random.default_rng(seed)
  return rng.random(REID_DIMENSIONS).astype(np.float32)


def encode_embedding(embedding):
  """Base64-encode a 256-float embedding for the metadata.reid field."""
  packed = struct.pack(f"{REID_DIMENSIONS}f", *embedding)
  return base64.b64encode(packed).decode("utf-8")


def make_detection(det_id, bbox, embedding=None, gender=None, gender_conf=None):
  """Build a single person detection.

  @param bbox         {"x","y","width","height"} in pixel coordinates.
  @param embedding    Optional np embedding; adds metadata.reid when present.
  @param gender       Optional gender label (e.g. "Male"); adds metadata.gender.
  @param gender_conf  Confidence for the gender attribute.
  """
  det = {
    "id": det_id,
    "category": "person",
    "bounding_box_px": bbox,
  }
  metadata = {}
  if embedding is not None:
    metadata["reid"] = {
      "embedding_vector": encode_embedding(embedding),
      "model_name": REID_MODEL,
    }
  if gender is not None:
    metadata["gender"] = {"label": gender, "model_name": "test-age-gender", "confidence": gender_conf}
  if metadata:
    det["metadata"] = metadata
  return det


def make_frame(camera_id, detections):
  """Wrap a list of detections in a camera-frame MQTT payload."""
  return {
    "id": camera_id,
    "timestamp": get_iso_time(),
    "rate": 10.0,
    "objects": {"person": list(detections)},
  }


def publish_frames(pubsub, camera_id, detections, num_frames, interval=0.1):
  """Publish `num_frames` copies of `detections` at the tracker frame rate."""
  topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id)
  for _ in range(num_frames):
    pubsub.publish(topic, json.dumps(make_frame(camera_id, detections)))
    time.sleep(interval)


def publish_empty(pubsub, camera_id, num_frames=10, interval=0.1):
  """Publish empty person lists to let the track go stale and prune."""
  topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id)
  for _ in range(num_frames):
    pubsub.publish(topic, json.dumps(make_frame(camera_id, [])))
    time.sleep(interval)


def get_scene_and_camera(params):
  """Authenticate and return (rest, scene_uid, camera_id)."""
  rest = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest.authenticate(params["user"], params["password"]), "Auth failed"

  scenes = rest.getScenes({})
  results = scenes.get("results", []) if isinstance(scenes, dict) else []
  assert results, "No scenes available"

  for scene in results:
    scene_uid = scene["uid"]
    cameras = rest.getCameras({"scene": scene_uid})
    cam_results = cameras.get("results", []) if isinstance(cameras, dict) else []
    if cam_results:
      camera_id = cam_results[0]["uid"]
      log.info(f"Using scene={scene['name']} ({scene_uid}) camera={camera_id}")
      return rest, scene_uid, camera_id
  
  cameras = rest.getCameras({"scene": scene_uid})
  cam_results = cameras.get("results", []) if isinstance(cameras, dict) else []
  if cam_results:
    camera_id = cam_results[0]["uid"]
    log.info(f"Using scene={scene_uid} camera={camera_id}")
    return rest, scene_uid, camera_id

  raise AssertionError("No scene with a configured camera found")


class SceneOutputCollector:
  """Subscribe to the regulated scene topic and collect published objects."""

  def __init__(self, pubsub, scene_uid):
    self._pubsub = pubsub
    self._topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=scene_uid)
    self._lock = threading.Lock()
    self._messages = []

  def __enter__(self):
    self._pubsub.addCallback(self._topic, self._on_message)
    return self

  def __exit__(self, *exc):
    self._pubsub.removeCallback(self._topic)

  def _on_message(self, client, userdata, message):
    try:
      data = json.loads(message.payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
      return
    with self._lock:
      self._messages.append(data)

  def objects(self):
    """Flat list of every object seen across all collected frames."""
    with self._lock:
      msgs = list(self._messages)
    objs = []
    for msg in msgs:
      objs.extend(msg.get("objects", []))
    return objs

  def clear(self):
    with self._lock:
      self._messages.clear()

  def wait_for(self, predicate, timeout=15.0, interval=0.2):
    """Return the first object matching predicate within timeout, else None."""
    deadline = time.time() + timeout
    while time.time() < deadline:
      for obj in self.objects():
        if predicate(obj):
          return obj
      time.sleep(interval)
    return None


def connect_vdms(params, use_tls=True):
  """Connect to VDMS, mirroring BackendFunctionalTest.vdms_connect."""
  import os
  rootcert = params["rootcert"]
  certs_dir = os.path.join(os.path.dirname(os.path.dirname(rootcert)), "certs")
  vdb = VDMSDatabase(
    ca_cert=rootcert,
    client_cert=os.path.join(certs_dir, "scenescape-vdms-c.crt"),
    client_key=os.path.join(certs_dir, "scenescape-vdms-c.key"),
  )
  if not use_tls:
    vdb.db = vdms.vdms(use_tls=False)
  vdb.connect()
  assert vdb.db.connected, "Failed to connect to VDMS"
  return vdb


def find_persist_by_uuid(vdb, uuid):
  """Return descriptor entities (uuid, decoded persist, persist_timestamp)."""
  query = [{
    "FindDescriptor": {
      "set": SCHEMA_NAME,
      "constraints": {"uuid": ["==", uuid]},
      "results": {"list": ["uuid", "persist", "persist_timestamp"], "blob": False},
    }
  }]
  response, _ = vdb.sendQuery(query)
  entities = response[0].get("entities", [])
  for ent in entities:
    raw = ent.get("persist")
    if isinstance(raw, str) and raw:
      try:
        ent["persist"] = json.loads(raw)
      except ValueError:
        pass
  return entities


def scene_logs(scenescape_env):
  """Return the current scene controller container logs as a string."""
  return scenescape_env.docker.compose.logs(services=["scene"])


def log_contains(scenescape_env, needle, timeout=15.0, interval=0.5):
  """Poll scene logs until `needle` (substring or regex) appears."""
  import re
  pattern = re.compile(needle)
  deadline = time.time() + timeout
  while time.time() < deadline:
    if pattern.search(scene_logs(scenescape_env)):
      return True
    time.sleep(interval)
  return False


GENDER_BBOX = {"x": 100, "y": 100, "width": 120, "height": 240}
SMALL_BBOX = {"x": 100, "y": 100, "width": 40, "height": 60}
REENTRY_BBOX = {"x": 500, "y": 100, "width": 120, "height": 240}

FEATURE_THRESHOLD = 12
STALE_TIMEOUT_S = 5
SUSPENDED_TRACK_TIMEOUT_S = 60


def gender_label(obj):
  """Return persistent_data.gender.label from a published object, or None."""
  return (obj.get("persistent_data") or {}).get("gender", {}).get("label")


def wait_for_tracker_ready(pubsub, scene_uid, camera_id, timeout=45.0):
  """Publish throwaway detections until the person tracker produces scene output."""
  warm_det = make_detection(999, SMALL_BBOX)
  with SceneOutputCollector(pubsub, scene_uid) as collector:
    deadline = time.time() + timeout
    ready = False
    while time.time() < deadline:
      publish_frames(pubsub, camera_id, [warm_det], num_frames=1, interval=0.2)
      if collector.objects():
        ready = True
        break
    assert ready, "tracker never produced scene output within warm-up timeout"
  publish_empty(pubsub, camera_id, num_frames=5)


@pytest.fixture
def warmed_scene(params, mqtt_client):
  """(rest, scene_uid, camera_id) after confirming the tracker pipeline is live."""
  rest, scene_uid, camera_id = get_scene_and_camera(params)
  wait_for_tracker_ready(mqtt_client, scene_uid, camera_id)
  return rest, scene_uid, camera_id


def test_persist_stored_to_vdms_on_track_end(scenescape_env, params, mqtt_client,
                                             warmed_scene, record_xml_attribute):
  record_xml_attribute("name", "NEX-T25995")
  rest, scene_uid, camera_id = warmed_scene

  time.sleep(10)
  emb = make_embedding(seed=1)
  det = make_detection(1, GENDER_BBOX, embedding=emb, gender="Male", gender_conf=0.9)

  with SceneOutputCollector(mqtt_client, scene_uid) as collector:
    publish_frames(mqtt_client, camera_id, [det], num_frames=FEATURE_THRESHOLD + 8)
    tracked = collector.wait_for(lambda o: (o.get("metadata") or {}).get("gender", {}).get("label") == "Male", timeout=20)
    all_objs = collector.objects()
    log.info(f"collected {len(all_objs)} objects on scene {scene_uid}; "
             f"cameras seen: {set(c for o in all_objs for c in o.get('visibility', []))}")
    if tracked is None:
      logs = scene_logs(scenescape_env)
      for ln in logs.splitlines():
        if any(k in ln for k in ("FELL BEHIND", "Unknown camera", "UNKNOWN SENDER",
                                 "no pose", "DISCARDING", "detector", "Invalid",
                                 "schema", "validate", camera_id)):
          log.info("SCENE-DROP: " + ln)
    assert tracked is not None, "object with metadata.gender never tracked"  
    obj = collector.wait_for(lambda o: gender_label(o) == "Male", timeout=20)
    assert obj is not None, "gender never appeared in scene output"
    gid = obj["id"]
    publish_empty(mqtt_client, camera_id, num_frames=10)

  time.sleep(STALE_TIMEOUT_S + 3)

  vdb = connect_vdms(params)
  entities = find_persist_by_uuid(vdb, gid)
  log.info(f"VDMS FindDescriptor for gid={gid} returned {len(entities)} entities")
  assert entities, f"No reid_vector descriptor for gid={gid}"
  persist = entities[0].get("persist")
  assert isinstance(persist, dict) and "gender" in persist, f"persist missing gender: {persist}"
  assert persist["gender"].get("label") == "Male", f"persist gender label mismatch: {persist.get('gender')}"

  if log_contains(scenescape_env, r"_addNewFeaturesToDatabase: Adding \d+ features", timeout=5.0):
    log.info("_addNewFeaturesToDatabase log line observed")
  else:
    log.info("_addNewFeaturesToDatabase log line not observed (requires DEBUG log level)")


def test_persist_appears_in_scene_output_during_continuous_track(mqtt_client, warmed_scene,
                                                                  record_xml_attribute):
  record_xml_attribute("name", "NEX-T25996")
  rest, scene_uid, camera_id = warmed_scene

  emb = make_embedding(seed=2)
  det = make_detection(2, GENDER_BBOX, embedding=emb, gender="Male", gender_conf=0.9)

  with SceneOutputCollector(mqtt_client, scene_uid) as collector:
    publish_frames(mqtt_client, camera_id, [det], num_frames=FEATURE_THRESHOLD + 8)
    obj = collector.wait_for(lambda o: gender_label(o) == "Male", timeout=20)
    assert obj is not None, "persistent_data.gender never appeared during continuous track"


def test_gender_survives_intermittent_dropouts(mqtt_client,
                                               warmed_scene, record_xml_attribute):
  record_xml_attribute("name", "NEX-T25997")
  _, scene_uid, camera_id = warmed_scene

  emb = make_embedding(seed=3)
  det_present = make_detection(3, GENDER_BBOX, embedding=emb, gender="Male", gender_conf=0.9)
  det_dropout = make_detection(3, GENDER_BBOX, embedding=emb, gender="Male", gender_conf=0.9)
  det_dropout["metadata"]["gender"]["label"] = None
  det_dropout["metadata"]["gender"]["confidence"] = None

  with SceneOutputCollector(mqtt_client, scene_uid) as collector:
    # Warm-up: establish persistent_data.gender == "Male" before introducing dropouts.
    publish_frames(mqtt_client, camera_id, [det_present], num_frames=FEATURE_THRESHOLD + 4)
    warm_obj = collector.wait_for(lambda o: gender_label(o) == "Male", timeout=20)
    assert warm_obj is not None, "gender never appeared during warm-up"
    gid = warm_obj["id"]
    collector.clear()

    publish_frames(mqtt_client, camera_id, [det_dropout], num_frames=4)
    publish_frames(mqtt_client, camera_id, [det_present], num_frames=4)

    tracked_objs = [o for o in collector.objects() if o.get("id") == gid]
    labels = [gender_label(o) for o in tracked_objs]

  assert labels, "no scene output observed for tracked object during dropout/recovery window"
  assert all(label == "Male" for label in labels), \
      f"gender dropped to null/missing during dropout window: {labels}"


def test_high_confidence_gender_used_as_tier1_constraint(scenescape_env, mqtt_client,
                                                          warmed_scene, record_xml_attribute):
  record_xml_attribute("name", "NEX-T25998")
  rest, scene_uid, camera_id = warmed_scene

  emb = make_embedding(seed=4)

  # Establish a baseline track and let it flush its persisted gender to VDMS.
  det_baseline = make_detection(6, GENDER_BBOX, embedding=emb, gender="Male", gender_conf=0.9)
  with SceneOutputCollector(mqtt_client, scene_uid) as collector:
    publish_frames(mqtt_client, camera_id, [det_baseline], num_frames=FEATURE_THRESHOLD + 8)
    baseline_obj = collector.wait_for(lambda o: gender_label(o) == "Male", timeout=20)
    assert baseline_obj is not None, "baseline gender never appeared in scene output"
    gid = baseline_obj["id"]
    publish_empty(mqtt_client, camera_id, num_frames=10)

  time.sleep(SUSPENDED_TRACK_TIMEOUT_S + 5)

  det_reentry = make_detection(7, GENDER_BBOX, embedding=emb, gender="Male", gender_conf=0.9)
  with SceneOutputCollector(mqtt_client, scene_uid) as collector:
    publish_frames(mqtt_client, camera_id, [det_reentry], num_frames=FEATURE_THRESHOLD + 8)
    reentry_obj = collector.wait_for(lambda o: gender_label(o) == "Male", timeout=20)
    assert reentry_obj is not None, "re-entry gender never appeared in scene output"
    reentry_gid = reentry_obj["id"]
    publish_empty(mqtt_client, camera_id, num_frames=10)

  assert reentry_gid == gid, \
      f"re-entered track (gid={reentry_gid}) did not match baseline gid={gid} via VDMS ReID"

  if log_contains(scenescape_env,
                   r"\[VDMS\].*ADDED: gender=Male \(confidence=0\.9 >= 0\.8\)", timeout=5.0):
    log.info("TIER-1 gender constraint log line observed")
  else:
    log.info("TIER-1 gender constraint log line not observed (requires DEBUG log level)")

  det_negative = make_detection(8, REENTRY_BBOX, embedding=emb, gender="Female", gender_conf=0.9)
  with SceneOutputCollector(mqtt_client, scene_uid) as collector:
    publish_frames(mqtt_client, camera_id, [det_negative], num_frames=FEATURE_THRESHOLD + 8)
    negative_obj = collector.wait_for(lambda o: gender_label(o) == "Female", timeout=20)
    assert negative_obj is not None, "negative-control gender never appeared in scene output"
    negative_gid = negative_obj["id"]

  assert negative_gid != gid, (
      "negative control matched baseline gid despite mismatched high-confidence gender; "
      "gender is not being applied as a TIER-1 constraint")