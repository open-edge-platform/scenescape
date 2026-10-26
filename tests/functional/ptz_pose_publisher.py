# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Publishes synthetic PTZ PoseContexts through the broker as the Positioning identity.

The Positioning ACL allows only pose writes for sources in the deployment assignment
manifest (tests/compose/positioning-assignments.json) and status writes for its own
resolver, so functional tests can drive Controller consumption without a camera.
"""

import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone

from scene_common import positioning_reasons as reasons
from scene_common.mqtt import PubSub
from tests.utils.log import get_logger
from tests.utils.ptz_pose import IDENTITY_MATRIX, pose_context, status_payload

log = get_logger(__name__)

SOURCE_ID = "test-source"
RESOLVER_ID = "positioning-default"
POSITIONING_AUTH_FILE = "positioning.auth"
DEFAULT_RATE_HZ = 10.0
MOTION_STATIONARY = "stationary"
MOTION_SLEWING = "slewing"
MOTION_SETTLING = "settling"
# Valid long enough to survive scheduling jitter yet shorter than the dwell bound
VALIDITY_S = 0.5


def utc_now():
  return datetime.now(timezone.utc)


class PTZPosePublisher:
  """Background publisher with test-controlled pose state."""

  def __init__(self, params, secrets_dir, frame_id, calibration_version,
               matrix=None, source_id=SOURCE_ID, resolver_id=RESOLVER_ID,
               rate_hz=DEFAULT_RATE_HZ):
    self.source_id = source_id
    self.resolver_id = resolver_id
    self.frame_id = frame_id
    self.calibration_version = calibration_version
    self.matrix = matrix or IDENTITY_MATRIX
    self.motion_state = MOTION_STATIONARY
    self.valid = True
    self.pose_frame_id = frame_id
    self.reason_detail = reasons.DETAIL_MOVING
    self.period_s = 1.0 / rate_hz
    # Retained poses of an earlier test are non-contiguous with this base, which resets dwell
    self.sequence = int(time.time())
    self._lock = threading.Lock()
    self._paused = threading.Event()
    self._stop = threading.Event()
    self._thread = None
    self.pose_topic = PubSub.formatTopic(PubSub.POSITIONING_POSE, source_id=source_id)
    self.status_topic = PubSub.formatTopic(PubSub.POSITIONING_STATUS, resolver_id=resolver_id)
    self.pubsub = PubSub(os.path.join(secrets_dir, POSITIONING_AUTH_FILE), None,
                         params['rootcert'], params['broker_url'],
                         port=int(params['broker_port']))
    self.pubsub.connect()
    self.pubsub.loopStart()

  # Control

  def set_pose(self, matrix=None, motion_state=None, valid=None, frame_id=None,
               calibration_version=None, reason_detail=None):
    """Change the pose published from the next message on."""
    with self._lock:
      if matrix is not None:
        self.matrix = matrix
      if motion_state is not None:
        self.motion_state = motion_state
      if valid is not None:
        self.valid = valid
      if frame_id is not None:
        self.pose_frame_id = frame_id
      if calibration_version is not None:
        self.calibration_version = calibration_version
      if reason_detail is not None:
        self.reason_detail = reason_detail

  def skip_sequence(self, count=1):
    """Create a sequence gap; the next message follows `count` unpublished samples."""
    with self._lock:
      self.sequence += count

  def pause(self):
    self._paused.set()

  def resume(self):
    self._paused.clear()

  def publish_status(self, state="online", session_start=None):
    """Publish a retained resolver status; a new session start resets consumers' dwell."""
    payload = status_payload(self.resolver_id, session_start or utc_now(), state)
    self.pubsub.publish(self.status_topic, json.dumps(payload), qos=1, retain=True)

  def new_session(self):
    self.publish_status("online", utc_now())

  # Publishing

  def start(self):
    self._thread = threading.Thread(target=self._run, name="ptz-pose-publisher", daemon=True)
    self._thread.start()

  def stop(self):
    """Stop publishing and clear the retained pose so later tests start clean."""
    self._stop.set()
    if self._thread is not None:
      self._thread.join(timeout=5)
    try:
      self.pubsub.publish(self.pose_topic, b"", qos=1, retain=True)
    finally:
      self.pubsub.loopStop()
      self.pubsub.disconnect()

  def now(self):
    return utc_now()

  def _run(self):
    next_at = time.monotonic()
    while not self._stop.is_set():
      if not self._paused.is_set():
        self._publish_one()
      next_at += self.period_s
      time.sleep(max(0.0, next_at - time.monotonic()))

  def _publish_one(self):
    with self._lock:
      self.sequence += 1
      payload = pose_context(
        self.source_id, self.sequence, utc_now(), self.pose_frame_id,
        self.calibration_version, matrix=self.matrix, valid=self.valid,
        motion_state=self.motion_state, validity_s=VALIDITY_S,
        reason_detail=self.reason_detail)
    self.pubsub.publish(self.pose_topic, json.dumps(payload), qos=0, retain=True)


def acquisition_time(age_s=0.3):
  """Detection acquisition timestamp: slightly in the past, as after pipeline latency."""
  return utc_now() - timedelta(seconds=age_s)
