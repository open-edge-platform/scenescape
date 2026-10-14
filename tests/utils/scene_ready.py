# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared helper to confirm a freshly created/linked scene has a live tracker.

A scene created via `scene_factory`/`demo_scene`, or a scene just linked as a
hierarchy child/parent, needs the scene controller to spin up a Scene/Tracker
instance before it will process detections. REST readiness (the scene exists,
CMD_DATABASE was seen) does not prove that warm-up has finished. Tests that
immediately publish camera detections and assert on DATA_SCENE/DATA_EXTERNAL/
DATA_REGULATED output can otherwise race this warm-up and flake with
"timed out waiting for ..." style assertions.

This module centralizes that readiness probe so it can run once during setup
(where a failure is scoped and obvious) instead of being inferred indirectly,
deep inside each test's own assertions, via ever-larger ad-hoc timeouts.
"""

import json
import threading

from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time, get_epoch_time
from tests.utils.log import get_logger

log = get_logger(__name__)

# Seconds to wait for the broker handshake before giving up on a connection.
MQTT_CONNECT_TIMEOUT_S = 10
# Default probe budget; a freshly created scene's tracker should come up well
# within this, but it is deliberately generous to absorb CI load/jitter.
DEFAULT_TIMEOUT_S = 30
PROBE_FRAME_RATE = 10


def _probe_detection(camera_id):
  return {
    "id": camera_id,
    "objects": {
      "person": [{
        "id": 1, "category": "person",
        "bounding_box": {"x": 0.56, "y": 0.0, "width": 0.24, "height": 0.49},
      }],
    },
    "rate": 9.8,
  }


def wait_for_tracker_ready(params, scene_uid, camera_id="camera1",
                          timeout=DEFAULT_TIMEOUT_S):
  """Block until the scene controller publishes DATA_SCENE for *scene_uid*.

  Repeatedly publishes a synthetic "person" detection on `camera_id`'s
  DATA_CAMERA topic until a DATA_SCENE message for *scene_uid* is observed,
  or *timeout* elapses.

  @param    params      Dict of functional-test connection parameters
                        (resturl/rootcert/auth/broker_url/broker_port, as
                        provided by the `params` fixture).
  @param    scene_uid   UID of the scene expected to report tracking data.
  @param    camera_id   Name/sensor_id of a calibrated camera in the scene.
  @param    timeout     Seconds to probe before giving up.
  @return               True if DATA_SCENE was observed in time, else False.
  """
  ready_event = threading.Event()

  def _on_scene_data(mqttc, obj, msg):
    try:
      data = json.loads(msg.payload.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
      return
    if data is not None:
      ready_event.set()
    return

  pubsub = PubSub(params['auth'], None, params['rootcert'],
                  params['broker_url'], port=int(params['broker_port']))
  wait_topic = PubSub.formatTopic(PubSub.DATA_SCENE, scene_id=scene_uid,
                                  thing_type="person")
  publish_topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id)

  pubsub.connect()
  pubsub.loopStart()
  try:
    deadline = get_epoch_time() + MQTT_CONNECT_TIMEOUT_S
    while not pubsub.isConnected() and get_epoch_time() < deadline:
      ready_event.wait(0.05)
    if not pubsub.isConnected():
      log.warning(
        "wait_for_tracker_ready: timed out connecting to the broker for "
        "scene %s", scene_uid)
      return False

    pubsub.addCallback(wait_topic, _on_scene_data)
    detection = _probe_detection(camera_id)
    interval = 1.0 / PROBE_FRAME_RATE
    begin = get_epoch_time()
    count = 0
    max_count = max(1, int(timeout / interval))
    while not ready_event.is_set() and count < max_count:
      detection['timestamp'] = get_iso_time(begin + count * interval)
      pubsub.publish(publish_topic, json.dumps(detection))
      ready_event.wait(interval)
      count += 1
    pubsub.removeCallback(wait_topic)

    if not ready_event.is_set():
      log.warning(
        "wait_for_tracker_ready: no DATA_SCENE observed for scene %s within "
        "%ss", scene_uid, timeout)
    return ready_event.is_set()
  finally:
    pubsub.loopStop()
