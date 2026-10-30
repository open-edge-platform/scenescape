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

MQTT_CONNECT_TIMEOUT_S = 10
DEFAULT_TIMEOUT_S = 30
DEFAULT_DRAIN_TIMEOUT_S = 10
PROBE_FRAME_RATE = 10

# Requiring more than one empty result avoids returning on a transient
# empty scene update while the probe track is still being finalized.
EMPTY_SCENE_CONFIRMATIONS = 2


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


def _empty_detection(camera_id):
  return {
    "id": camera_id,
    "objects": {
      "person": [],
    },
    "rate": 9.8,
  }


def _person_count(scene_data):
  """Return the number of active person tracks in a DATA_SCENE payload."""
  if not isinstance(scene_data, dict):
    log.warning(
      "Unexpected DATA_SCENE payload type: %s",
      type(scene_data).__name__,
    )
    return None

  objects = scene_data.get("objects")
  if not isinstance(objects, list):
    log.warning(
      "DATA_SCENE objects is not a list; top-level keys=%s",
      list(scene_data.keys()),
    )
    return None

  return sum(
    1
    for obj in objects
    if isinstance(obj, dict) and obj.get("category") == "person"
  )


def wait_for_tracker_ready(params, scene_uid, camera_id="camera1",
                           timeout=DEFAULT_TIMEOUT_S,
                           drain_timeout=DEFAULT_DRAIN_TIMEOUT_S):
  """Wait until the tracker responds and the readiness-probe track ages out.

  The probe first publishes a synthetic person until DATA_SCENE reports
  tracking output. It then publishes empty camera frames until DATA_SCENE
  reports no active person tracks for multiple consecutive updates.

  @return True when the tracker responded and the probe track drained.
  """
  tracker_seen_event = threading.Event()
  probe_drained_event = threading.Event()

  callback_lock = threading.Lock()
  state = {
    "draining": False,
    "empty_confirmations": 0,
  }

  def _on_scene_data(mqttc, obj, msg):
    try:
      data = json.loads(msg.payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
      return

    person_count = _person_count(data)
    if person_count is None:
      log.debug(
        "Ignoring DATA_SCENE payload with unexpected schema for scene %s",
        scene_uid,
      )
      return

    with callback_lock:
      if not state["draining"]:
        if person_count > 0:
          tracker_seen_event.set()
        return

      if person_count == 0:
        state["empty_confirmations"] += 1
        if state["empty_confirmations"] >= EMPTY_SCENE_CONFIRMATIONS:
          probe_drained_event.set()
      else:
        state["empty_confirmations"] = 0

  pubsub = PubSub(
    params["auth"],
    None,
    params["rootcert"],
    params["broker_url"],
    port=int(params["broker_port"]),
  )

  wait_topic = PubSub.formatTopic(
    PubSub.DATA_SCENE,
    scene_id=scene_uid,
    thing_type="person",
  )
  publish_topic = PubSub.formatTopic(
    PubSub.DATA_CAMERA,
    camera_id=camera_id,
  )

  pubsub.connect()
  pubsub.loopStart()

  try:
    connect_deadline = get_epoch_time() + MQTT_CONNECT_TIMEOUT_S
    while (not pubsub.isConnected()
           and get_epoch_time() < connect_deadline):
      tracker_seen_event.wait(0.05)

    if not pubsub.isConnected():
      log.warning(
        "wait_for_tracker_ready: timed out connecting to the broker "
        "for scene %s",
        scene_uid,
      )
      return False

    pubsub.addCallback(wait_topic, _on_scene_data)

    interval = 1.0 / PROBE_FRAME_RATE
    timestamp_epoch = get_epoch_time()

    # Prove that the tracker processes the synthetic detection.
    probe = _probe_detection(camera_id)
    ready_deadline = get_epoch_time() + timeout

    while (not tracker_seen_event.is_set()
           and get_epoch_time() < ready_deadline):
      probe["timestamp"] = get_iso_time(timestamp_epoch)
      pubsub.publish(publish_topic, json.dumps(probe))

      tracker_seen_event.wait(interval)
      timestamp_epoch += interval

    if not tracker_seen_event.is_set():
      log.warning(
        "wait_for_tracker_ready: no tracked person observed for scene %s "
        "within %ss",
        scene_uid,
        timeout,
      )
      return False

    # Switch callback interpretation before publishing the first empty frame,
    # so an immediate empty DATA_SCENE update cannot be missed.
    with callback_lock:
      state["draining"] = True
      state["empty_confirmations"] = 0

    # Advance the tracker with empty frames until the probe track disappears from scene output.
    empty_frame = _empty_detection(camera_id)
    drain_deadline = get_epoch_time() + drain_timeout

    while (not probe_drained_event.is_set()
           and get_epoch_time() < drain_deadline):
      empty_frame["timestamp"] = get_iso_time(timestamp_epoch)
      pubsub.publish(publish_topic, json.dumps(empty_frame))

      probe_drained_event.wait(interval)
      timestamp_epoch += interval

    if not probe_drained_event.is_set():
      log.warning(
        "wait_for_tracker_ready: probe track did not age out for scene %s "
        "within %ss",
        scene_uid,
        drain_timeout,
      )
      return False

    log.debug(
      "Tracker ready and readiness-probe track drained for scene %s",
      scene_uid,
    )
    return True

  finally:
    try:
      pubsub.removeCallback(wait_topic)
    finally:
      pubsub.loopStop()
