# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared setup for the Controller PTZ functional tests.

Creates a PTZ camera (the assigned `test-source`) in the Demo scene with the pose and
intrinsics of the Demo camera, drives its PoseContexts and detections through the
broker, and collects the Scene Controller's scene output.
"""

import copy
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from scene_common.camera import Camera
from scene_common.mqtt import PubSub
from scene_common.positioning_dwell import PoseSnapshot
from tests.functional.ptz_pose_publisher import (
  SOURCE_ID, PTZPosePublisher, acquisition_time)
from tests.utils.log import get_logger
from tests.utils.ptz_pose import iso, pose_context, rotated_matrix

log = get_logger(__name__)

THING_TYPE = "person"
DEMO_CAMERA_ID = "camera1"
CALIBRATION_VERSION = "ptz-functional-v1"
CALIBRATION_EXAMPLE = "docs/user-guide/api-docs/positioning/v1/ideal-camera.example.json"
DETECTION_RATE_HZ = 10.0
DETECTION_ID = 1
# Normalized image-plane box that projects onto the Demo floor (see the objData fixture)
DETECTION_BOX = {"x": 0.56, "y": 0.0, "width": 0.24, "height": 0.49}
ADMISSION_TIMEOUT_S = 60.0
# Dwell is max_detection_pipeline_latency_s (1 s) plus the pose timestamp uncertainties
MIN_DWELL_S = 1.0
LOCATION_TOLERANCE_M = 0.3
OFF_HOME_YAW_DEG = 25.0


def detection_message(camera_id, timestamp):
  return {
    "id": camera_id,
    "timestamp": iso(timestamp),
    "rate": 9.8,
    "objects": {THING_TYPE: [{
      "id": DETECTION_ID, "category": THING_TYPE, "confidence": 0.95,
      "bounding_box": dict(DETECTION_BOX)}]},
  }


class PTZControllerHarness:

  def __init__(self, params, rest, scene_uid, secrets_dir, repo_root):
    self.params = params
    self.rest = rest
    self.scene_uid = scene_uid
    self.secrets_dir = secrets_dir
    self.repo_root = Path(repo_root)
    self.frame_id = f"scene:{scene_uid}"
    self.created_cameras = []
    self.publisher = None
    self._messages = []
    self._lock = threading.Lock()
    self.pubsub = PubSub(params['auth'], None, params['rootcert'], params['broker_url'],
                         port=int(params['broker_port']))
    self.scene_topic = PubSub.formatTopic(PubSub.DATA_SCENE, scene_id=scene_uid,
                                          thing_type=THING_TYPE)
    self.pubsub.onConnect = lambda *args: self.pubsub.subscribe(self.scene_topic)
    self.pubsub.addCallback(self.scene_topic, self._scene_received)
    self.pubsub.connect()
    self.pubsub.loopStart()

  # Setup

  def calibration(self, version=CALIBRATION_VERSION):
    example = json.loads((self.repo_root / CALIBRATION_EXAMPLE).read_text())
    example["calibration_version"] = version
    return example

  def create_ptz_camera(self, camera_id=SOURCE_ID):
    """PTZ camera at the Demo camera's pose; returns the created camera's REST data."""
    demo = self.rest.getCamera(DEMO_CAMERA_ID)
    assert demo, (demo.statusCode, demo.errors)
    created = self.rest.createCamera({
      "name": camera_id, "sensor_id": camera_id, "scene": self.scene_uid,
      "intrinsics": demo["intrinsics"], "distortion": demo["distortion"],
      "transform_type": "euler", "translation": demo["translation"],
      "rotation": demo["rotation"], "scale": demo["scale"],
      "ptz_calibration": self.calibration(),
    })
    assert created, (created.statusCode, created.errors)
    self.created_cameras.append(camera_id)
    camera = self.rest.getCamera(camera_id)
    assert camera["ptz_calibration"]["calibration_version"] == CALIBRATION_VERSION
    self.camera_data = camera
    return camera

  def start_poses(self, camera, **kwargs):
    """Publish stationary PoseContexts at the camera's home pose (or `matrix`)."""
    self.camera_data = camera
    self.home_matrix = camera["pose_matrix"]
    self.publisher = PTZPosePublisher(
      self.params, self.secrets_dir, self.frame_id, CALIBRATION_VERSION,
      matrix=kwargs.pop("matrix", self.home_matrix), **kwargs)
    self.publisher.new_session()
    self.publisher.start()
    self.poses_started = time.time()
    return self.publisher

  # Scene output

  def _scene_received(self, client, userdata, message):
    data = json.loads(message.payload.decode("utf-8"))
    with self._lock:
      self._messages.append((time.time(), data))

  def clear_output(self):
    with self._lock:
      self._messages.clear()

  def output_with_objects(self):
    with self._lock:
      return [(at, data) for at, data in self._messages if data.get("objects")]

  def send_detection(self, camera_id=SOURCE_ID, age_s=0.3):
    message = detection_message(camera_id, acquisition_time(age_s))
    self.pubsub.publish(PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id),
                        json.dumps(message))

  def run_detections(self, seconds, camera_id=SOURCE_ID, until=None):
    """Send detections for `seconds` (or until `until()` is true); returns whether it was."""
    deadline = time.time() + seconds
    while time.time() < deadline:
      self.send_detection(camera_id)
      time.sleep(1.0 / DETECTION_RATE_HZ)
      if until is not None and until():
        return True
    return until() if until is not None else False

  def wait_for_admission(self, camera_id=SOURCE_ID, timeout=ADMISSION_TIMEOUT_S):
    """Send detections until the Controller publishes a tracked object; returns the time."""
    self.clear_output()
    assert self.run_detections(timeout, camera_id, until=lambda: bool(self.output_with_objects())), \
      f"No PTZ detection was admitted within {timeout}s"
    return self.output_with_objects()[0][0]

  def assert_blackout(self, seconds, camera_id=SOURCE_ID, settle_s=0.7):
    """No scene output while detections keep arriving; `settle_s` lets earlier output drain."""
    self.run_detections(settle_s, camera_id)
    self.clear_output()
    self.run_detections(seconds, camera_id)
    admitted = self.output_with_objects()
    assert not admitted, f"{len(admitted)} detections were admitted during the blackout"

  def latest_location(self):
    objects = self.output_with_objects()
    assert objects, "No scene output with objects"
    return np.array(objects[-1][1]["objects"][0]["translation"][:2])

  # Expected projection

  def expected_location(self, matrix):
    """Scene XY of the detection projected with the Demo camera's intrinsics and `matrix`."""
    from controller.ptz.projection import ProjectedCamera
    from controller.tracking import Tracking
    static = Camera(self.camera_data["uid"], copy.deepcopy(self.camera_data),
                    resolution=self.camera_data["resolution"])
    snapshot = PoseSnapshot.from_payload(pose_context(
      SOURCE_ID, 1, datetime.now(timezone.utc), self.frame_id, CALIBRATION_VERSION,
      matrix=matrix))
    camera = ProjectedCamera(static, snapshot)
    info = {"id": DETECTION_ID, "category": THING_TYPE, "confidence": 0.95,
            "bounding_box": dict(DETECTION_BOX)}
    return np.array(Tracking.createObject(THING_TYPE, info, time.time(), camera)
                    .sceneLoc.asCartesianVector[:2])

  def off_home_matrix_for(self, camera, yaw_deg=OFF_HOME_YAW_DEG):
    return rotated_matrix(camera["pose_matrix"], yaw_deg)

  # Teardown

  def close(self):
    if self.publisher is not None:
      self.publisher.stop()
    for camera_id in self.created_cameras:
      try:
        self.rest.deleteCamera(camera_id)
      except Exception as error:
        log.warning(f"Could not delete camera {camera_id}: {error}")
    self.pubsub.loopStop()
    self.pubsub.disconnect()


@pytest.fixture
def ptz_harness(params, rest, scene_uid, secrets_dir, repo_root):
  harness = PTZControllerHarness(params, rest, scene_uid, secrets_dir, repo_root)
  try:
    yield harness
  finally:
    harness.close()
