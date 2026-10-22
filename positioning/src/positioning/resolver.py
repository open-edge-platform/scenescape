# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Resolve accepted in-process PTZ samples into retained PoseContext messages."""

import datetime
import json
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field

import numpy as np
from scipy.spatial.transform import Rotation

from positioning.pose_math import (
  apply_backlash, axis_angle_degrees, backlash_degrees_at, compose_ptz_rotation,
  physical_home_angle, scene_from_camera_matrix)
from positioning.ptz_model import PTZAxisModel
from positioning.v1 import ptz_pb2
from scene_common.positioning_quality import calibration_score, score, temporal_score

_REASON_TO_INVALID = {
  "no_sample": "no_pose_available",
  "sample_stale": "pose_expired",
  "moving": "invalid_pose",
  "settling": "invalid_pose",
  "calibration_missing": "invalid_pose",
  "calibration_changed": "invalid_pose",
  "invalid_sample": "invalid_pose",
  "backlash_unknown": "invalid_pose",
}


@dataclass(frozen=True)
class PTZSourceCalibration:
  """Manager-owned PTZ model and static home transform for one camera."""

  model: PTZAxisModel
  home_matrix: object
  frame_id: str


@dataclass
class _SourceState:
  adapter_instance_id: str = ""
  last_sequence: int = 0
  last_timestamp_ns: int = 0
  last_reported_angles: object = None
  last_motion_ns: object = None
  physical_angles: object = field(default_factory=lambda: [None, None])
  backlash_known: list = field(default_factory=lambda: [False, False])
  history: object = field(default_factory=deque)
  pending_reason: object = None

  def reset_motion(self):
    self.last_reported_angles = None
    self.last_motion_ns = None
    self.physical_angles = [None, None]
    self.backlash_known = [False, False]
    self.history.clear()


class PTZResolver:
  """Validate, resolve, and publish samples without queuing or replaying them."""

  def __init__(self, source_calibrations, publish, poll_interval_s, max_pose_age_s,
               max_timestamp_uncertainty_s, target_reprojection_rms_px,
               sample_ring_buffer_size=64, clock_ns=None, clock_synchronized=None,
               metrics=None):
    self.source_calibrations = dict(source_calibrations)
    self.publish = publish
    self.clock_synchronized = clock_synchronized or (lambda: True)
    self.metrics = metrics
    self.poll_interval_s = self._positive(poll_interval_s, "poll_interval_s")
    self.max_pose_age_s = self._positive(max_pose_age_s, "max_pose_age_s")
    self.max_timestamp_uncertainty_s = self._nonnegative(
      max_timestamp_uncertainty_s, "max_timestamp_uncertainty_s")
    self.target_reprojection_rms_px = self._positive(
      target_reprojection_rms_px, "target_reprojection_rms_px")
    if self.max_pose_age_s < self.poll_interval_s + self.max_timestamp_uncertainty_s:
      raise ValueError("max_pose_age_s must be >= poll_interval_s + max_timestamp_uncertainty_s")
    if isinstance(sample_ring_buffer_size, bool) or not isinstance(sample_ring_buffer_size, int):
      raise ValueError("sample_ring_buffer_size must be an integer")

    required_history_s = max((
      max(calibration.model.settle_interval_s,
          calibration.model.pan.backlash_history_s,
          calibration.model.tilt.backlash_history_s)
      for calibration in self.source_calibrations.values() if calibration is not None
    ), default=0.0)
    minimum_size = math.ceil(required_history_s / self.poll_interval_s) + 2
    if sample_ring_buffer_size < minimum_size:
      raise ValueError(f"sample_ring_buffer_size must be >= {minimum_size}")

    self.sample_ring_buffer_size = sample_ring_buffer_size
    self.clock_ns = clock_ns or time.time_ns
    self._states = {
      source_id: _SourceState(history=deque(maxlen=sample_ring_buffer_size))
      for source_id in self.source_calibrations
    }
    self._locks = {source_id: threading.RLock() for source_id in self.source_calibrations}
    if self.metrics is not None:
      for source_id, calibration in self.source_calibrations.items():
        self._record_calibration_version(source_id, calibration)

  def _record_calibration_version(self, source_id, calibration):
    if self.metrics is not None:
      self.metrics.set_calibration_version(
        source_id, calibration.model.calibration_version if calibration else None)

  @staticmethod
  def _positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
        or not math.isfinite(value) or value <= 0:
      raise ValueError(f"{name} must be a positive finite number")
    return float(value)

  @staticmethod
  def _nonnegative(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
        or not math.isfinite(value) or value < 0:
      raise ValueError(f"{name} must be a finite nonnegative number")
    return float(value)

  def update_calibration(self, source_id, calibration):
    """Replace a source calibration and reset motion/backlash continuity."""
    if source_id not in self._states:
      raise KeyError(source_id)
    if calibration is not None and not isinstance(calibration, PTZSourceCalibration):
      raise TypeError("calibration must be PTZSourceCalibration or None")
    if calibration is not None:
      model = calibration.model
      required_history_s = max(
        model.settle_interval_s, model.pan.backlash_history_s, model.tilt.backlash_history_s)
      minimum_size = math.ceil(required_history_s / self.poll_interval_s) + 2
      if self.sample_ring_buffer_size < minimum_size:
        raise ValueError(f"sample_ring_buffer_size must be >= {minimum_size}")
    with self._locks[source_id]:
      state = self._states[source_id]
      previous = self.source_calibrations[source_id]
      old_version = previous.model.calibration_version if previous else None
      new_version = calibration.model.calibration_version if calibration else None
      unchanged = previous is None and calibration is None
      if previous is not None and calibration is not None:
        try:
          same_matrix = np.array_equal(
            np.asarray(previous.home_matrix), np.asarray(calibration.home_matrix))
        except (TypeError, ValueError):
          same_matrix = False
        unchanged = old_version == new_version and previous.model == calibration.model \
          and previous.frame_id == calibration.frame_id and same_matrix
      if unchanged:
        return
      self.source_calibrations[source_id] = calibration
      state.reset_motion()
      if state.last_sequence:
        state.pending_reason = "calibration_changed" if calibration else "calibration_missing"
      self._record_calibration_version(source_id, calibration)

  def invalidate_calibration(self, source_id):
    """Drop the cached calibration; poses stay invalid until a reload succeeds."""
    if source_id not in self._states:
      raise KeyError(source_id)
    with self._locks[source_id]:
      state = self._states[source_id]
      self.source_calibrations[source_id] = None
      state.reset_motion()
      if state.last_sequence:
        state.pending_reason = "calibration_changed"
      self._record_calibration_version(source_id, None)

  def submit_ptz_sample(self, sample):
    """Accept a PTZSample, publishing one valid or invalid PoseContext if accepted."""
    source_id = getattr(sample, "camera_id", None)
    if source_id not in self._states:
      return self._ack(ptz_pb2.PTZ_SAMPLE_RESULT_UNKNOWN_CAMERA, "unknown camera")
    with self._locks[source_id]:
      ack = self._submit_locked(source_id, sample)
    if self.metrics is not None and ack.result != ptz_pb2.PTZ_SAMPLE_RESULT_ACCEPTED:
      self.metrics.inc_rejected_sample(source_id, ptz_pb2.PTZSampleResult.Name(ack.result))
    return ack

  def _submit_locked(self, source_id, sample):
    calibration = self.source_calibrations[source_id]
    validation_error, timestamp_ns = self._validate_sample(sample, calibration)
    if validation_error:
      return self._ack(ptz_pb2.PTZ_SAMPLE_RESULT_INVALID, validation_error)

    state = self._states[source_id]
    adapter_instance_id = sample.adapter_instance_id
    if state.adapter_instance_id and state.adapter_instance_id != adapter_instance_id:
      state.last_sequence = 0
      state.last_timestamp_ns = 0
      state.reset_motion()
    if sample.sequence == state.last_sequence:
      return self._ack(ptz_pb2.PTZ_SAMPLE_RESULT_DUPLICATE, "duplicate sequence")
    if sample.sequence < state.last_sequence:
      return self._ack(ptz_pb2.PTZ_SAMPLE_RESULT_OUT_OF_ORDER, "sequence decreased")
    clock_synchronized = self.clock_synchronized()
    # Sequence order still rejects replays; a newer sample with a non-increasing
    # wall-clock timestamp means the host clock stepped backward.
    clock_discontinuity = not clock_synchronized or (
      state.last_timestamp_ns > 0 and timestamp_ns <= state.last_timestamp_ns)
    if clock_discontinuity:
      state.last_timestamp_ns = 0
      state.reset_motion()
    sequence_gap = state.last_sequence > 0 and sample.sequence != state.last_sequence + 1
    timestamp_gap = state.last_timestamp_ns > 0 and \
      timestamp_ns - state.last_timestamp_ns > int(self.max_pose_age_s * 1e9)
    if sequence_gap or timestamp_gap:
      state.reset_motion()
    if sequence_gap and self.metrics is not None:
      self.metrics.inc_sequence_gap(source_id)

    now_ns = self.clock_ns()
    age_s = max(0.0, (now_ns - timestamp_ns) / 1e9)
    uncertainty_s = sample.timestamp_uncertainty_ns / 1e9
    if clock_discontinuity:
      # Timestamps cannot be trusted, so neither motion history nor freshness can be.
      motion_state = "unknown"
      reason_detail = "invalid_sample"
    elif age_s > self.max_pose_age_s:
      state.reset_motion()
      motion_state = "unknown"
      reason_detail = "sample_stale"
    elif calibration is None:
      motion_state = "unknown"
      reason_detail = "calibration_missing"
    else:
      motion_state, reason_detail = self._resolve_motion(sample, timestamp_ns, calibration, state)
    if state.pending_reason:
      reason_detail = state.pending_reason
      state.pending_reason = None

    state.adapter_instance_id = adapter_instance_id
    state.last_sequence = sample.sequence
    state.last_timestamp_ns = timestamp_ns if clock_synchronized else 0

    pose_context = self._build_context(
      source_id, sample.sequence, timestamp_ns, age_s, uncertainty_s, motion_state,
      reason_detail, calibration, state.physical_angles)
    topic = f"scenescape/positioning/pose/{source_id}"
    self.publish(topic, json.dumps(pose_context, separators=(",", ":")), qos=0, retain=True)
    if self.metrics is not None:
      self.metrics.observe_pose_age(source_id, age_s)
      self.metrics.observe_motion_state(source_id, motion_state, timestamp_ns)
    return self._ack(ptz_pb2.PTZ_SAMPLE_RESULT_ACCEPTED, "accepted", sample.sequence)

  def _validate_sample(self, sample, calibration):
    try:
      if not sample.adapter_instance_id or len(sample.adapter_instance_id) > 128:
        return "adapter_instance_id must contain 1-128 characters", 0
      if sample.sequence <= 0 or sample.timestamp_uncertainty_ns <= 0:
        return "sequence and timestamp uncertainty must be positive", 0
      uncertainty_s = sample.timestamp_uncertainty_ns / 1e9
      if uncertainty_s > self.max_timestamp_uncertainty_s:
        return "timestamp uncertainty exceeds configured maximum", 0
      if not sample.HasField("measured_at") or not sample.HasField("position"):
        return "sample is missing measured_at or position", 0
      timestamp = sample.measured_at
      if timestamp.seconds < 0 or not 0 <= timestamp.nanos < 1_000_000_000:
        return "measured_at is outside the supported timestamp range", 0
      timestamp_ns = timestamp.seconds * 1_000_000_000 + timestamp.nanos
      now_ns = self.clock_ns()
      if timestamp_ns - now_ns > sample.timestamp_uncertainty_ns:
        return "measured_at is beyond timestamp uncertainty", 0

      position = sample.position
      values = (position.pan, position.tilt, position.pan_min, position.pan_max,
                position.tilt_min, position.tilt_max)
      if not all(math.isfinite(value) for value in values):
        return "position and ranges must be finite", 0
      if position.pan_min >= position.pan_max or position.tilt_min >= position.tilt_max:
        return "position ranges must be ordered", 0
      if not position.pan_min <= position.pan <= position.pan_max \
          or not position.tilt_min <= position.tilt <= position.tilt_max:
        return "position is outside advertised ranges", 0
      if calibration is not None:
        space = calibration.model.position_space
        expected = (space.pan_min, space.pan_max, space.tilt_min, space.tilt_max)
        actual = (position.pan_min, position.pan_max, position.tilt_min, position.tilt_max)
        if position.position_space_uri != space.uri or any(
          not math.isclose(a, e, rel_tol=0.0, abs_tol=1e-9)
          for a, e in zip(actual, expected)
        ):
          return "reported position space does not match calibration", 0
      return None, timestamp_ns
    except (AttributeError, TypeError, ValueError, OverflowError):
      return "sample is malformed", 0

  def _resolve_motion(self, sample, timestamp_ns, calibration, state):
    model = calibration.model
    position = sample.position
    raw_angles = [
      axis_angle_degrees(position.pan, model.pan.curve),
      axis_angle_degrees(position.tilt, model.tilt.curve),
    ]
    axes = (model.pan, model.tilt)
    positions = (position.pan, position.tilt)
    for index, axis in enumerate(axes):
      backlash = backlash_degrees_at(axis.backlash, positions[index])
      if not state.backlash_known[index]:
        home_angle = axis_angle_degrees(axis.home_position, axis.curve)
        at_home = abs(raw_angles[index] - home_angle) <= axis.backlash_home_tolerance_deg
        if at_home:
          state.physical_angles[index] = apply_backlash(
            physical_home_angle(axis), raw_angles[index], backlash)
          state.backlash_known[index] = True
        else:
          state.physical_angles[index] = raw_angles[index]
      else:
        state.physical_angles[index] = apply_backlash(
          state.physical_angles[index], raw_angles[index], backlash)

    is_moving = state.last_reported_angles is not None and any(
      abs(current - previous) > model.settle_angular_threshold_deg
      for current, previous in zip(raw_angles, state.last_reported_angles)
    )
    if is_moving:
      state.last_motion_ns = timestamp_ns
    state.last_reported_angles = raw_angles
    state.history.append((timestamp_ns, raw_angles))

    if not all(state.backlash_known):
      return "unknown", "backlash_unknown"
    if is_moving:
      return "slewing", "moving"

    settle_ns = int(model.settle_interval_s * 1e9)
    window_start_ns = timestamp_ns - settle_ns
    window = list(state.history)
    boundary_index = max(
      (i for i, entry in enumerate(window) if entry[0] <= window_start_ns), default=0)
    window = window[boundary_index:]
    if not window or window[0][0] > window_start_ns:
      return ("settling", "settling") if state.last_motion_ns is not None else ("unknown", "settling")
    spans = [max(item[1][axis] for item in window) - min(item[1][axis] for item in window)
             for axis in range(2)]
    if state.last_motion_ns is not None and timestamp_ns - state.last_motion_ns < settle_ns:
      return "settling", "settling"
    if any(span > model.settle_angular_threshold_deg for span in spans):
      return "settling", "settling"
    return "stationary", None

  def _build_context(self, source_id, sequence, timestamp_ns, age_s, uncertainty_s,
                     motion_state, reason_detail, calibration, physical_angles):
    timestamp = self._format_timestamp(timestamp_ns)
    context = {
      "schema_version": 1,
      "source_id": source_id,
      "timestamp": timestamp,
      "valid_until": self._format_timestamp(timestamp_ns + int(self.max_pose_age_s * 1e9)),
      "sequence": sequence,
      "valid": False,
      "motion_state": motion_state,
      "sample_age_s": age_s,
      "timestamp_uncertainty_s": uncertainty_s,
      "calibration_version": calibration.model.calibration_version if calibration else "unknown",
    }
    if reason_detail is None and calibration is not None:
      model = calibration.model
      if model.reprojection_rms_px > self.target_reprojection_rms_px:
        reason_detail = "calibration_missing"
      else:
        try:
          home = np.asarray(calibration.home_matrix, dtype=float)
        except (TypeError, ValueError):
          home = np.empty((0, 0))
        if not self._valid_home_matrix(home) or not calibration.frame_id:
          reason_detail = "calibration_missing"
        else:
          home_rotation = Rotation.from_matrix(home[:3, :3])
          home_angles = (physical_home_angle(model.pan), physical_home_angle(model.tilt))
          rotation = compose_ptz_rotation(
            model, home_rotation,
            physical_angles[0] - home_angles[0], physical_angles[1] - home_angles[1])
          matrix = scene_from_camera_matrix(rotation, home[:3, 3])
          temporal = temporal_score(age_s, uncertainty_s, self.max_pose_age_s)
          calibrated = calibration_score(
            model.reprojection_rms_px, self.target_reprojection_rms_px)
          context["valid"] = True
          context["pose"] = {
            "frame_id": calibration.frame_id,
            "transform_direction": "scene_from_camera",
            "matrix_layout": "row_major",
            "matrix_4x4": matrix.tolist(),
            "translation_unit": "m",
          }
          context["quality"] = {
            "score": score(temporal, calibrated),
            "temporal_score": temporal,
            "calibration_score": calibrated,
            "reprojection_rms_px": model.reprojection_rms_px,
          }
    if not context["valid"]:
      if reason_detail is None:
        reason_detail = "invalid_sample"
      context["invalid_reason"] = _REASON_TO_INVALID[reason_detail]
      context["reason_detail"] = reason_detail
    return context

  @staticmethod
  def _valid_home_matrix(matrix):
    if matrix.shape != (4, 4) or not np.all(np.isfinite(matrix)):
      return False
    if not np.allclose(matrix[3], [0.0, 0.0, 0.0, 1.0], atol=1e-9):
      return False
    rotation = matrix[:3, :3]
    return np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-6) \
      and math.isclose(float(np.linalg.det(rotation)), 1.0, rel_tol=0.0, abs_tol=1e-6)

  @staticmethod
  def _format_timestamp(timestamp_ns):
    value = datetime.datetime.fromtimestamp(timestamp_ns / 1e9, tz=datetime.timezone.utc)
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")

  @staticmethod
  def _ack(result, detail, sequence=0):
    return ptz_pb2.PTZSampleAck(result=result, detail=detail, accepted_sequence=sequence)
