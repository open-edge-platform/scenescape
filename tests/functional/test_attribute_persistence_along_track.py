#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import threading
import time

import pytest

from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time
from tests.utils.log import get_logger
from tests.utils.profiles import SCENE_PERSIST_SUB_ATTR
from tests.utils.scene_ready import wait_for_tracker_ready
from tests.utils.spec import AUTH_CONTROLLER, FuncTestSpec

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=SCENE_PERSIST_SUB_ATTR,
  auth=AUTH_CONTROLLER,
)

# Camera ids are limited to 20 characters, with the shape appended.
CAMERA_ID = "ptrack"
PLATE = "ABC1234"
CAR_BBOX = {"x": 50, "y": 200, "width": 150, "height": 100}
OTHER_CAR_BBOX = {"x": 400, "y": 200, "width": 150, "height": 100}
PLATE_BBOX = {"x": 90, "y": 270, "width": 60, "height": 20}
# The OCR result as a metadata attribute, and as the sub-detection the DL Streamer plugin publishes.
METADATA = "metadata"
TOP_LEVEL = "top_level"
SHAPES = (METADATA, TOP_LEVEL)
FRAME_INTERVAL_S = 0.1
FRAMES_WITH_PLATE = 20
FRAMES_WITHOUT_PLATE = 10
OUTPUT_TIMEOUT_S = 20


class SceneOutput:
  """! Collects the car objects the Scene Controller publishes for one scene."""

  def __init__(self, pubsub, scene_uid):
    self._pubsub = pubsub
    self._topic = PubSub.formatTopic(PubSub.DATA_SCENE, scene_id=scene_uid, thing_type="car")
    self._lock = threading.Lock()
    self._objects = []

  def __enter__(self):
    self._pubsub.addCallback(self._topic, self._on_message)
    return self

  def __exit__(self, *exc):
    self._pubsub.removeCallback(self._topic)

  def _on_message(self, _client, _userdata, message):
    try:
      objects = json.loads(message.payload.decode("utf-8")).get("objects", [])
    except (ValueError, UnicodeDecodeError):
      return
    with self._lock:
      self._objects.extend(objects)

  def objects(self):
    with self._lock:
      return list(self._objects)

  def clear(self):
    with self._lock:
      self._objects.clear()

  def wait_for(self, predicate, timeout=OUTPUT_TIMEOUT_S):
    """! Returns the first collected object matching predicate within timeout, else None."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
      for obj in self.objects():
        if predicate(obj):
          return obj
      time.sleep(0.2)
    return None


@pytest.fixture
def mqtt_client(params):
  """! Connected PubSub client with its network loop running."""
  client = PubSub(params["auth"], None, params["rootcert"], params["broker_url"],
                  port=int(params["broker_port"]), keepalive=60)
  client.connect()
  client.loopStart()
  deadline = time.monotonic() + 10
  while not client.isConnected() and time.monotonic() < deadline:
    time.sleep(0.1)
  assert client.isConnected(), "Failed to connect to the MQTT broker"
  yield client
  client.loopStop()
  client.disconnect()


def make_car(car_id, bbox, shape, plate=None):
  """! Builds a car detection, with the OCR result of its license plate when plate is given.

  The metadata shape holds the plate as a semantic attribute, which the metadata schema
  requires to have a label and a model name. The top-level shape is what the DL Streamer
  plugin publishes: the plate as a sub-detection of the car.
  """
  car = {"id": car_id, "category": "car", "bounding_box_px": bbox}
  if plate is None:
    return car
  if shape == METADATA:
    car["metadata"] = {"license_plates": {
      "label": plate, "model_name": "test-ocr", "confidence": 0.9, "text": plate}}
  else:
    car["license_plates"] = [{"bounding_box_px": PLATE_BBOX, "confidence": 0.9, "text": plate}]
  return car


def publish_frames(client, camera_id, cars, count):
  """! Publishes count frames of the given car detections at the camera frame rate."""
  topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id)
  for _ in range(count):
    frame = {"id": camera_id, "timestamp": get_iso_time(), "rate": 1 / FRAME_INTERVAL_S,
             "objects": {"car": cars}}
    if any("license_plates" in car for car in cars):
      frame["sub_detections"] = ["license_plate"]
    client.publish(topic, json.dumps(frame))
    time.sleep(FRAME_INTERVAL_S)


def persisted_plate(obj):
  """! The license_plates attributes persisted on a published object, or None."""
  return (obj.get("persistent_data") or {}).get("license_plates")


def check_persistence(client, params, scene_factory, shape):
  """! Runs the scenario for one detection shape on a scene of its own.
  @return   str                     What went wrong, or None when the plate persisted as expected.
  """
  camera_id = f"{CAMERA_ID}-{shape}"
  scene_uid = scene_factory(f"PersistAlongTrack-{shape}", cameras=[camera_id])["uid"]
  if not wait_for_tracker_ready(params, scene_uid, camera_id=camera_id):
    return "the tracker never produced scene output"

  with SceneOutput(client, scene_uid) as output:
    publish_frames(client, camera_id,
                   [make_car(1, CAR_BBOX, shape, PLATE), make_car(2, OTHER_CAR_BBOX, shape)],
                   FRAMES_WITH_PLATE)
    if not output.wait_for(lambda obj: True):
      return "the cars were never tracked, so the detections were not accepted"
    tracked = output.wait_for(lambda obj: persisted_plate(obj) is not None)
    if tracked is None:
      return "the cars were tracked but the license plate never appeared in persistent_data"
    if persisted_plate(tracked) != {"text": PLATE}:
      return f"only the configured sub-attribute should persist: {tracked.get('persistent_data')}"
    track_id = tracked["id"]

    output.clear()
    publish_frames(client, camera_id,
                   [make_car(1, CAR_BBOX, shape), make_car(2, OTHER_CAR_BBOX, shape)],
                   FRAMES_WITHOUT_PLATE)
    objects = output.objects()

  first = [obj for obj in objects if obj["id"] == track_id]
  if not first:
    return f"track {track_id} was lost once the license plate stopped being reported"
  if any(persisted_plate(obj) != {"text": PLATE} for obj in first):
    return f"the license plate did not persist along the track: {[persisted_plate(o) for o in first]}"
  others = [obj for obj in objects if obj["id"] != track_id]
  if not others:
    return "the second car was not tracked"
  if any(persisted_plate(obj) is not None for obj in others):
    return f"the license plate leaked to another track: {[persisted_plate(o) for o in others]}"
  return None


@pytest.mark.test_name("NEX-T10584")
def test_attribute_persistence_along_track(mqtt_client, params, scene_factory, result_recorder):
  """
  ## Name
  Attribute persistence along track

  ## Objective
  Verify that attributes from model chain inferences persist along the track:
  the license plate text of a car stays on the track in the scene output after
  the model chain stops reporting it, and never reaches another track. This must
  hold for the plate published as the DL Streamer plugin publishes it, a
  sub-detection of the car, and as a metadata attribute.

  ## Labels
  - Functional
  - Tracking
  - Attribute Persistence
  - MQTT

  ## Steps
  1. Start the Scene Controller with persist_attributes {"car": [{"license_plates": "text"}]}.
  2. For each plate shape, metadata attribute and top-level sub-detection, wait until the tracker is live on a scene of its own.
  3. Publish detections of two cars, only the first with the OCR result of its license plate.
  4. Assert the first car's scene output carries persistent_data.license_plates.text and no other license plate field.
  5. Keep publishing both cars without any license plate result.
  6. Assert the first car keeps the same track and the license plate text in persistent_data.
  7. Assert the second car's track never has a license plate in persistent_data.
  """
  problems = {}
  for shape in SHAPES:
    log.info(f"Checking the license plate published as {shape}")
    problem = check_persistence(mqtt_client, params, scene_factory, shape)
    if problem:
      problems[shape] = problem

  assert not problems, "The license plate did not persist for: " + "; ".join(
    f"{shape}: {problem}" for shape, problem in problems.items())
  result_recorder.success()
