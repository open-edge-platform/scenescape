#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
PTZ PoseContext consumption service tests for the tracker.

A PTZ camera (`ptz-cam`, home pose looking straight down from 3 m at the scene origin)
is driven through the broker the way the Positioning service and a detector would:
retained resolver status, PoseContexts at 5 Hz, and detections acquired 250 ms before
they are published. The PoseContext pose is 5 m east and 2 m north of the home pose,
so a detection projected with it lands near (5, 2) and one projected with the static
home pose lands near the origin.

Covers:
- Enforcing mode: nothing reaches tracking while the camera moves or the dwell is
  incomplete; afterwards tracks are projected with the PoseContext.
- Shadow mode: tracking is unchanged (static projection, no gating) and sampled
  per-decision JSONL records with candidate residuals are written to stdout.
- A resolver session change resets the dwell.
- Subscriptions cover only assigned sources and their resolvers.
"""

import json
import math
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import paho.mqtt.client as mqtt
import pytest
from python_on_whales import DockerClient
from waiting import wait

from utils.docker import get_broker_host, get_container_logs, wait_for_readiness

SCENE_ID = "ptz-test-scene"
SOURCE_ID = "ptz-cam"
UNASSIGNED_ID = "unassigned-ptz"
RESOLVER_ID = "positioning"
CALIBRATION_VERSION = "svc-ptz-v1"
SCENE_TOPIC = f"scenescape/data/scene/{SCENE_ID}/thing"
POSE_TOPIC = f"scenescape/positioning/pose/{SOURCE_ID}"
STATUS_TOPIC = f"scenescape/positioning/status/{RESOLVER_ID}"
RECORD_MARKER = '{"record_type":"ptz_shadow"'

POSE_X, POSE_Y, HEIGHT = 5.0, 2.0, 3.0
POSE_PERIOD_S = 0.2
DETECTION_PERIOD_S = 0.1
ACQUISITION_DELAY_S = 0.25
LOCATION_TOLERANCE_M = 0.3
MOVING_S = 2.5
ADMISSION_TIMEOUT_S = 20

# Bbox whose bottom-centre is the principal point: it projects to the camera nadir.
DETECTION_BOX = {"x": 300, "y": 160, "width": 40, "height": 80}

PTZ_ENV = (
    "TRACKER_MQTT_INSECURE=true\n"
    "TRACKER_SCENES_SOURCE=file\n"
    "TRACKER_SCENES_FILE_PATH=/test-fixtures/ptz-test-scene.json\n"
    "TRACKER_NTP_SERVER=ntp-server\n"
    "TRACKER_NTP_SYNC_INTERVAL_S=60\n"
    "TRACKER_PTZ_MAX_POSE_AGE_S=0.5\n"
    "TRACKER_PTZ_MAX_CLOCK_OFFSET_S=0.25\n"
    "TRACKER_PTZ_MAX_DETECTION_PIPELINE_LATENCY_S=0.5\n"
    "TRACKER_PTZ_MAX_DETECTION_TIMESTAMP_UNCERTAINTY_S=0.05\n"
    "TRACKER_PTZ_ASSIGNMENTS_PATH=/test-fixtures/ptz-assignments.json\n"
    "TRACKER_PTZ_SHADOW_SAMPLE_EVERY_N=1\n"
)


def iso(moment):
  return moment.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def pose_matrix():
  # Downward-looking camera (Rx(180)) translated to (POSE_X, POSE_Y, HEIGHT)
  return [[1.0, 0.0, 0.0, POSE_X], [0.0, -1.0, 0.0, POSE_Y],
          [0.0, 0.0, -1.0, HEIGHT], [0.0, 0.0, 0.0, 1.0]]


class PositioningDriver:
  """Publishes resolver status, PoseContexts, and detections like the real producers."""

  def __init__(self, client):
    self.client = client
    self.motion_state = "slewing"
    self.sequence = 0
    self._stop = threading.Event()
    self._threads = []

  def publish_status(self, session_start):
    payload = {"resolver_id": RESOLVER_ID, "status": "online", "timestamp": iso(session_start)}
    self.client.publish(STATUS_TOPIC, json.dumps(payload), qos=1, retain=True).wait_for_publish()

  def _pose(self, now):
    self.sequence += 1
    payload = {
        "schema_version": 1, "source_id": SOURCE_ID, "timestamp": iso(now),
        "valid_until": iso(now + timedelta(seconds=1)), "sequence": self.sequence,
        "motion_state": self.motion_state, "sample_age_s": 0.0,
        "timestamp_uncertainty_s": 0.01, "calibration_version": CALIBRATION_VERSION,
    }
    if self.motion_state == "stationary":
      payload.update({
          "valid": True,
          "pose": {"frame_id": f"scene:{SCENE_ID}", "transform_direction": "scene_from_camera",
                   "matrix_layout": "row_major", "matrix_4x4": pose_matrix(),
                   "translation_unit": "m"},
          "quality": {"score": 0.9, "temporal_score": 0.9, "calibration_score": 0.9,
                      "reprojection_rms_px": 1.0},
      })
    else:
      payload.update({"valid": False, "invalid_reason": "invalid_pose", "reason_detail": "moving"})
    return payload

  def _poses(self):
    while not self._stop.is_set():
      payload = self._pose(datetime.now(timezone.utc))
      self.client.publish(POSE_TOPIC, json.dumps(payload), qos=0, retain=True)
      self._stop.wait(POSE_PERIOD_S)

  def _detections(self):
    while not self._stop.is_set():
      acquired = datetime.now(timezone.utc) - timedelta(seconds=ACQUISITION_DELAY_S)
      for camera_id in (SOURCE_ID, UNASSIGNED_ID):
        message = {"id": camera_id, "timestamp": iso(acquired),
                   "objects": {"thing": [{"id": 1, "bounding_box_px": DETECTION_BOX}]}}
        self.client.publish(f"scenescape/data/camera/{camera_id}", json.dumps(message), qos=0)
      self._stop.wait(DETECTION_PERIOD_S)

  def start(self):
    for target in (self._poses, self._detections):
      thread = threading.Thread(target=target, daemon=True)
      thread.start()
      self._threads.append(thread)

  def stop(self):
    self._stop.set()
    for thread in self._threads:
      thread.join(timeout=2)


def ptz_service(tls_certs, mode_env):
  service_dir = Path(__file__).parent
  project_name = f"tracker-ptz-{uuid.uuid4().hex[:8]}"
  env_file = tls_certs.temp_dir / ".env"
  env_file.write_text(
      f"TLS_CA_CERT_FILE={tls_certs.ca.cert_path}\n"
      f"TLS_SERVER_CERT_FILE={tls_certs.server.cert_path}\n"
      f"TLS_SERVER_KEY_FILE={tls_certs.server.key_path}\n"
      f"TLS_CLIENT_CERT_FILE={tls_certs.client.cert_path}\n"
      f"TLS_CLIENT_KEY_FILE={tls_certs.client.key_path}\n"
      + PTZ_ENV + mode_env)
  docker = DockerClient(
      compose_files=[service_dir / "compose.yml", service_dir / "compose.override.yml"],
      compose_project_name=project_name,
      compose_project_directory=str(service_dir),
      compose_env_files=[str(env_file)],
      compose_profiles=["ntp"],
  )
  docker.compose.up(services=["ntp-server"], detach=True, wait=True)
  docker.compose.up(detach=True, wait=False)
  try:
    wait_for_readiness(docker, timeout=30)
  except Exception:
    print(get_container_logs(docker, "tracker"))
    docker.compose.down(remove_orphans=True, volumes=True)
    raise
  return docker


@pytest.fixture(scope="function")
def ptz_enforce(tls_certs):
  docker = ptz_service(tls_certs, "TRACKER_PTZ_ENABLED=true\n")
  try:
    yield docker
  finally:
    docker.compose.down(remove_orphans=True, volumes=True)


@pytest.fixture(scope="function")
def ptz_shadow(tls_certs):
  docker = ptz_service(tls_certs, "TRACKER_PTZ_SHADOW_MODE=true\n"
                       "TRACKER_PTZ_SHADOW_PER_DECISION=true\n"
                       "TRACKER_PTZ_SHADOW_RUN_ID=service-shadow\n")
  try:
    yield docker
  finally:
    docker.compose.down(remove_orphans=True, volumes=True)


class SceneOutput:

  def __init__(self, docker):
    host, port = get_broker_host(docker, port=1883)
    self.messages = []
    self._lock = threading.Lock()
    self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                              client_id=f"test-ptz-{uuid.uuid4().hex[:8]}")
    self.client.on_message = self._on_message
    self.client.connect(host, port, keepalive=60)
    self.client.loop_start()
    self.client.subscribe(SCENE_TOPIC, qos=0)

  def _on_message(self, _client, _userdata, msg):
    with self._lock:
      self.messages.append(json.loads(msg.payload.decode()))

  def clear(self):
    with self._lock:
      self.messages.clear()

  def tracks(self):
    with self._lock:
      return [obj for message in self.messages for obj in message.get("objects", [])]

  def close(self):
    self.client.loop_stop()
    self.client.disconnect()


def near(track, x, y):
  return math.hypot(track["translation"][0] - x, track["translation"][1] - y) < LOCATION_TOLERANCE_M


def shadow_records(docker):
  records = []
  for line in get_container_logs(docker, "tracker").splitlines():
    start = line.find(RECORD_MARKER)
    if start >= 0:
      records.append(json.loads(line[start:]))
  return records


def test_enforce_gates_until_dwell_then_projects_with_pose(ptz_enforce):
  """No PTZ detection reaches tracking while moving; after the dwell, tracks use the pose."""
  output = SceneOutput(ptz_enforce)
  driver = PositioningDriver(output.client)
  try:
    driver.publish_status(datetime.now(timezone.utc))
    driver.start()
    time.sleep(MOVING_S)
    assert output.tracks() == [], "detections reached tracking while the camera was moving"

    driver.motion_state = "stationary"
    wait(lambda: any(near(t, POSE_X, POSE_Y) for t in output.tracks()),
         timeout_seconds=ADMISSION_TIMEOUT_S, sleep_seconds=0.2,
         waiting_for="tracks projected with the PoseContext")
    assert not any(near(t, 0.0, 0.0) for t in output.tracks()), \
        "a PTZ detection was projected with the static home pose"
  finally:
    driver.stop()
    output.close()

  logs = get_container_logs(ptz_enforce, "tracker")
  assert "Queued PTZ positioning subscriptions" in logs and "2 topics" in logs
  assert f"PTZ camera {UNASSIGNED_ID} has no resolver" in logs
  assert "PTZ pose consumption: enforce mode" in logs


def test_shadow_keeps_static_tracking_and_records_decisions(ptz_shadow):
  """Shadow mode never gates or reprojects; it records decisions and candidate residuals."""
  output = SceneOutput(ptz_shadow)
  driver = PositioningDriver(output.client)
  try:
    driver.publish_status(datetime.now(timezone.utc))
    driver.start()
    wait(lambda: any(near(t, 0.0, 0.0) for t in output.tracks()),
         timeout_seconds=ADMISSION_TIMEOUT_S, sleep_seconds=0.2,
         waiting_for="static tracks while the camera moves")

    driver.motion_state = "stationary"
    wait(lambda: any(r["admitted"] and r["source_id"] == SOURCE_ID
                     for r in shadow_records(ptz_shadow)),
         timeout_seconds=ADMISSION_TIMEOUT_S, sleep_seconds=0.5,
         waiting_for="an admitted shadow decision")

    driver.publish_status(datetime.now(timezone.utc) + timedelta(seconds=1))
    time.sleep(1.0)
    output.clear()
    time.sleep(1.0)
    assert output.tracks() and all(not near(t, POSE_X, POSE_Y) for t in output.tracks()), \
        "shadow mode changed the projection of live tracks"
  finally:
    driver.stop()
    output.close()

  records = [r for r in shadow_records(ptz_shadow) if r["source_id"] == SOURCE_ID]
  assert all(r["run_id"] == "service-shadow" and r["profile"] == "tracker"
             and r["mode"] == "shadow" for r in records)
  assert any(r["reason_detail"] == "moving" for r in records)
  admitted = [r for r in records if r["admitted"]]
  assert admitted and admitted[0]["calibration_version"] == CALIBRATION_VERSION
  residuals = [d["residual_m"] for r in admitted for d in r["detections"]]
  assert residuals and all(abs(value - math.hypot(POSE_X, POSE_Y)) < LOCATION_TOLERANCE_M
                           for value in residuals)
  first_admitted = records.index(admitted[0])
  later = records[first_admitted:]
  assert any(r["reason_detail"] == "dwell_incomplete" for r in later), \
      "a resolver session change must reset the dwell"
