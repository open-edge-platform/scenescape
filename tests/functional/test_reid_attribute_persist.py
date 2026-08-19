# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Functional tests for the ReID persistent-attribute (gender) feature.

Detections are injected as synthetic MQTT messages so gender labels and confidence values
are deterministic, then asserted against the ReID vector database and the scene
controller's tracked-object output.
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

from tests.functional.reid_backend import (
  configure_host_reid_certs,
  connect_reid_database,
  create_reid_database,
)
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


def make_embedding(seed=None):
  """Return a deterministic unit-norm 256-float ReID embedding."""
  rng = np.random.default_rng(seed)
  vec = rng.standard_normal(REID_DIMENSIONS)
  return (vec / np.linalg.norm(vec)).astype(np.float32)


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
    metadata["gender"] = {
      "label": gender,
      "model_name": "test-age-gender",
      "confidence": gender_conf,
    }
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
  """Authenticate and return (scene_uid, camera_id) for the first scene with a camera."""
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
      return scene_uid, camera_id

  raise AssertionError("No scene with a configured camera found")


class SceneOutputCollector:
  """Subscribe to the scene controller's tracked-object topic and collect published objects."""

  def __init__(self, pubsub, scene_uid, thing_type="person"):
    self._pubsub = pubsub
    self._topic = PubSub.formatTopic(PubSub.DATA_SCENE, scene_id=scene_uid,
                                     thing_type=thing_type)
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


def connect_reid_backend(use_tls=True):
  """Connect to the configured ReID vector database (VDMS or Qdrant) from the host."""
  configure_host_reid_certs()
  db = create_reid_database()
  connect_reid_database(db, use_tls=use_tls)
  return db


GENDER_BBOX = {"x": 100, "y": 100, "width": 120, "height": 240}
SMALL_BBOX = {"x": 100, "y": 100, "width": 40, "height": 60}
NEGATIVE_BBOX = {"x": 500, "y": 100, "width": 120, "height": 240}

FEATURE_THRESHOLD = 12
STALE_TIMEOUT_S = 5
SUSPENDED_TRACK_TIMEOUT_S = 60

RESOLVED_REID_STATES = {"matched", "query_no_match", "reid_disabled"}


def gender_label(obj):
  """Return persistent_data.gender.label from a published object, or None."""
  return (obj.get("persistent_data") or {}).get("gender", {}).get("label")


def is_reid_resolved(obj):
  """True once the object's ReID query has settled (matched, no match, or disabled)."""
  return obj.get("reid_state") in RESOLVED_REID_STATES


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
  """(scene_uid, camera_id) after confirming the tracker pipeline is live."""
  scene_uid, camera_id = get_scene_and_camera(params)
  wait_for_tracker_ready(mqtt_client, scene_uid, camera_id)
  return scene_uid, camera_id


def test_persist_stored_to_vdms_on_track_end(mqtt_client, warmed_scene,
                                             record_xml_attribute):
  """Persisted gender is flushed to the ReID database when the track ends."""
  record_xml_attribute("name", "NEX-T25995")
  scene_uid, camera_id = warmed_scene

  emb = make_embedding(seed=1)
  det = make_detection(1, GENDER_BBOX, embedding=emb, gender="Male", gender_conf=0.9)

  with SceneOutputCollector(mqtt_client, scene_uid) as collector:
    publish_frames(mqtt_client, camera_id, [det], num_frames=FEATURE_THRESHOLD + 8)
    obj = collector.wait_for(lambda o: gender_label(o) == "Male", timeout=20)
    assert obj is not None, "gender never appeared in scene output"
    gid = obj["id"]
    publish_empty(mqtt_client, camera_id, num_frames=10)

  time.sleep(STALE_TIMEOUT_S + 3)

  db = connect_reid_backend()
  persist = db.getPersistedAttributes(gid)
  log.info(f"persisted attributes for gid={gid}: {persist}")
  assert persist, f"No persisted attributes stored for gid={gid}"
  assert "gender" in persist, f"persist missing gender: {persist}"
  assert persist["gender"].get("label") == "Male", \
    f"persist gender label mismatch: {persist.get('gender')}"


def test_bbox_below_minimum_area_gathers_no_features(mqtt_client, warmed_scene,
                                                     record_xml_attribute):
  """Detections under minimum_bbox_area never contribute embeddings."""
  record_xml_attribute("name", "NEX-T25996")
  scene_uid, camera_id = warmed_scene

  det = make_detection(14, SMALL_BBOX, embedding=make_embedding(seed=9),
                       gender="Male", gender_conf=0.9)

  with SceneOutputCollector(mqtt_client, scene_uid) as collector:
    publish_frames(mqtt_client, camera_id, [det], num_frames=FEATURE_THRESHOLD * 2)
    assert collector.wait_for(lambda o: o.get("id") is not None, timeout=20), \
      "small-bbox detections never produced scene output"
    tracked_objs = collector.objects()
    publish_empty(mqtt_client, camera_id, num_frames=10)

  states = {o.get("reid_state") for o in tracked_objs}
  assert states == {"pending_collection"}, \
    f"small-bbox track left pending_collection: {states}"
  assert all(o.get("similarity") is None for o in tracked_objs), \
    "small-bbox track was scored against the ReID database"


def test_gender_survives_intermittent_dropouts(mqtt_client, warmed_scene,
                                               record_xml_attribute):
  """Gender stays populated when the analytics model stops reporting the attribute."""
  record_xml_attribute("name", "NEX-T25997")
  scene_uid, camera_id = warmed_scene

  emb = make_embedding(seed=3)
  det_present = make_detection(3, GENDER_BBOX, embedding=emb,
                               gender="Male", gender_conf=0.9)
  det_dropout = make_detection(3, GENDER_BBOX, embedding=emb)

  with SceneOutputCollector(mqtt_client, scene_uid) as collector:
    publish_frames(mqtt_client, camera_id, [det_present],
                   num_frames=FEATURE_THRESHOLD + 4)
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


@pytest.mark.parametrize("reentry_confidence,should_match,seed,test_name", [
  (0.9, False, 4, "NEX-T25998"),
  (0.63, True, 6, "NEX-T25999"),
], ids=["high_confidence_filters", "low_confidence_ignored"])
def test_gender_confidence_gates_reid_match(mqtt_client, warmed_scene, reentry_confidence,
                                            should_match, seed, test_name,
                                            record_xml_attribute):
  """Gender filters ReID candidates only at or above the 0.8 confidence threshold."""
  record_xml_attribute("name", test_name)
  scene_uid, camera_id = warmed_scene

  emb = make_embedding(seed=seed)

  det_baseline = make_detection(6, GENDER_BBOX, embedding=emb,
                                gender="Male", gender_conf=0.9)
  with SceneOutputCollector(mqtt_client, scene_uid) as collector:
    publish_frames(mqtt_client, camera_id, [det_baseline],
                   num_frames=FEATURE_THRESHOLD + 8)
    baseline_obj = collector.wait_for(
      lambda o: gender_label(o) == "Male" and is_reid_resolved(o), timeout=30)
    assert baseline_obj is not None, "baseline track never resolved its ReID query"
    baseline_gid = baseline_obj["id"]
    publish_empty(mqtt_client, camera_id, num_frames=10)

  time.sleep(SUSPENDED_TRACK_TIMEOUT_S + 5)

  det_reentry = make_detection(7, NEGATIVE_BBOX, embedding=emb,
                               gender="Female", gender_conf=reentry_confidence)
  with SceneOutputCollector(mqtt_client, scene_uid) as collector:
    publish_frames(mqtt_client, camera_id, [det_reentry],
                   num_frames=FEATURE_THRESHOLD + 8)
    reentry_obj = collector.wait_for(is_reid_resolved, timeout=30)
    assert reentry_obj is not None, "re-entered track never resolved its ReID query"
    reentry_gid = reentry_obj["id"]
    publish_empty(mqtt_client, camera_id, num_frames=10)

  if should_match:
    assert reentry_gid == baseline_gid, (
      f"re-entered track (gid={reentry_gid}) did not match baseline gid={baseline_gid}; "
      "a low-confidence gender mismatch was applied as a hard match constraint")
  else:
    assert reentry_gid != baseline_gid, (
      "re-entered track matched the baseline gid despite a mismatched high-confidence "
      "gender; gender is not being applied as a TIER-1 constraint")
