# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Normative v1 dwell admission for PTZ PoseContext consumers.

Transport-agnostic and clock-injected: callers feed PoseContext and resolver
status messages in arrival order and pass the synchronized local time to
``evaluate``. Times are integer nanoseconds so boundary comparisons are exact
and portable to the C++ Tracker implementation.

A detection is admitted only when all of the following hold for the source's
latest valid stationary PoseContext (``latest``) in an uninterrupted dwell
started at ``stationary_since`` (checked in this order; the first failure is
the reported reason):

  - pose valid, stationary, matching frame/calibration, ``local_now < valid_until``
    and ``local_now - latest.timestamp < max_pose_age``
  - ``local_now - observation <= max_detection_pipeline_latency``
  - ``observation <= latest.timestamp``
  - ``(latest.timestamp - stationary_since) - latest.uncertainty
     - stationary_since_uncertainty >= max_detection_pipeline_latency``
  - ``observation - max_detection_timestamp_uncertainty >= stationary_since``

Dwell resets on any invalid/non-stationary pose, sequence gap or non-increase,
non-increasing timestamp, calibration/frame/source mismatch, or resolver
session change.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from scene_common import positioning_reasons as reasons
from scene_common.positioning_config import ConsumerPositioningConfig

NS_PER_S = 1_000_000_000
MOTION_STATIONARY = "stationary"
MOTION_SLEWING = "slewing"
MOTION_SETTLING = "settling"
MOTION_UNKNOWN = "unknown"
STATUS_ONLINE = "online"

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

_MOTION_DETAILS = {
  MOTION_SLEWING: reasons.DETAIL_MOVING,
  MOTION_SETTLING: reasons.DETAIL_SETTLING,
  MOTION_UNKNOWN: reasons.DETAIL_NO_SAMPLE,
}


def seconds_to_ns(seconds: float) -> int:
  return int(round(seconds * NS_PER_S))


def parse_timestamp_ns(text: str) -> int:
  """ISO-8601 timestamp with explicit timezone -> integer ns since the epoch."""
  parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
  if parsed.tzinfo is None:
    raise ValueError(f"Timestamp without timezone: {text!r}")
  delta = parsed - _EPOCH
  return ((delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds) * 1000


@dataclass(frozen=True)
class PoseSnapshot:
  """Fields of a schema-validated PoseContext used for dwell admission."""
  source_id: str
  sequence: int
  timestamp_ns: int
  valid_until_ns: int
  timestamp_uncertainty_ns: int
  valid: bool
  motion_state: str
  calibration_version: str
  frame_id: Optional[str] = None
  invalid_reason: Optional[str] = None
  reason_detail: Optional[str] = None
  payload: Mapping[str, Any] = field(default_factory=dict, compare=False, repr=False)

  @classmethod
  def from_payload(cls, payload: Mapping[str, Any]) -> "PoseSnapshot":
    pose = payload.get("pose") or {}
    return cls(
      source_id=payload["source_id"],
      sequence=int(payload["sequence"]),
      timestamp_ns=parse_timestamp_ns(payload["timestamp"]),
      valid_until_ns=parse_timestamp_ns(payload["valid_until"]),
      timestamp_uncertainty_ns=seconds_to_ns(payload["timestamp_uncertainty_s"]),
      valid=payload["valid"] is True,
      motion_state=payload["motion_state"],
      calibration_version=payload["calibration_version"],
      frame_id=pose.get("frame_id"),
      invalid_reason=payload.get("invalid_reason"),
      reason_detail=payload.get("reason_detail"),
      payload=payload,
    )


@dataclass(frozen=True)
class DwellConfig:
  max_pose_age_ns: int
  max_detection_pipeline_latency_ns: int
  max_detection_timestamp_uncertainty_ns: int

  @classmethod
  def from_consumer_config(cls, config: ConsumerPositioningConfig) -> "DwellConfig":
    return cls(
      max_pose_age_ns=seconds_to_ns(config.max_pose_age_s),
      max_detection_pipeline_latency_ns=seconds_to_ns(config.max_detection_pipeline_latency_s),
      max_detection_timestamp_uncertainty_ns=seconds_to_ns(
        config.max_detection_timestamp_uncertainty_s),
    )


@dataclass(frozen=True)
class AdmissionDecision:
  admitted: bool
  invalid_reason: Optional[str] = None
  reason_detail: Optional[str] = None
  pose: Optional[PoseSnapshot] = None
  dwell_elapsed_s: Optional[float] = None


def _reject(detail: str, pose: Optional[PoseSnapshot] = None,
            dwell_elapsed_s: Optional[float] = None) -> AdmissionDecision:
  return AdmissionDecision(False, reasons.canonical_reason(detail), detail, pose, dwell_elapsed_s)


class DwellTracker:
  """Per-source dwell state for one PTZ camera; not thread-safe."""

  def __init__(self, source_id: str, resolver_id: str, config: DwellConfig,
               expected_frame_id: Optional[str] = None,
               expected_calibration_version: Optional[str] = None):
    self.source_id = source_id
    self.resolver_id = resolver_id
    self.config = config
    self.expected_frame_id = expected_frame_id
    self.expected_calibration_version = expected_calibration_version
    self._latest: Optional[PoseSnapshot] = None
    self._session_ns: Optional[int] = None
    self._stationary_since_ns: Optional[int] = None
    self._stationary_since_uncertainty_ns = 0
    self._latest_stationary: Optional[PoseSnapshot] = None

  def reset(self) -> None:
    self._stationary_since_ns = None
    self._stationary_since_uncertainty_ns = 0
    self._latest_stationary = None

  @property
  def stationary_since_ns(self) -> Optional[int]:
    return self._stationary_since_ns

  def set_expected_calibration_version(self, calibration_version: Optional[str]) -> None:
    if calibration_version != self.expected_calibration_version:
      self.expected_calibration_version = calibration_version
      self.reset()

  def on_status(self, resolver_id: str, status: str, timestamp_ns: int) -> None:
    """Resolver status/LWT; any session change or non-online status resets dwell."""
    if resolver_id != self.resolver_id:
      return
    session = timestamp_ns if status == STATUS_ONLINE else None
    if status != STATUS_ONLINE or session != self._session_ns:
      self.reset()
    self._session_ns = session

  def on_pose(self, pose: PoseSnapshot) -> None:
    if pose.source_id != self.source_id:
      self.reset()
      return
    previous = self._latest
    if previous is not None and (pose.sequence != previous.sequence + 1
                                 or pose.timestamp_ns <= previous.timestamp_ns):
      self.reset()
    self._latest = pose

    if not self._usable_for_dwell(pose):
      self.reset()
      return
    dwell = self._latest_stationary
    if dwell is not None and (dwell.calibration_version != pose.calibration_version
                              or dwell.frame_id != pose.frame_id):
      self.reset()
    if self._stationary_since_ns is None:
      self._stationary_since_ns = pose.timestamp_ns
      self._stationary_since_uncertainty_ns = pose.timestamp_uncertainty_ns
    self._latest_stationary = pose

  def _usable_for_dwell(self, pose: PoseSnapshot) -> bool:
    return (pose.valid and pose.motion_state == MOTION_STATIONARY
            and pose.frame_id is not None
            and (self.expected_frame_id is None or pose.frame_id == self.expected_frame_id)
            and (self.expected_calibration_version is None
                 or pose.calibration_version == self.expected_calibration_version))

  def evaluate(self, observation_timestamp_ns: int, local_now_ns: int) -> AdmissionDecision:
    """Admission decision for a detection acquired at ``observation_timestamp_ns``."""
    latest = self._latest
    if latest is None:
      return _reject(reasons.DETAIL_NO_SAMPLE)
    if not latest.valid:
      detail = latest.reason_detail
      if detail in reasons.ALL_REASON_DETAILS:
        return _reject(detail, latest)
      return AdmissionDecision(False, latest.invalid_reason or reasons.REASON_INVALID_POSE,
                               detail, latest)
    if latest.motion_state != MOTION_STATIONARY:
      return _reject(_MOTION_DETAILS.get(latest.motion_state, reasons.DETAIL_NO_SAMPLE), latest)
    if self.expected_frame_id is not None and latest.frame_id != self.expected_frame_id:
      return _reject(reasons.DETAIL_FRAME_MISMATCH, latest)
    if (self.expected_calibration_version is not None
        and latest.calibration_version != self.expected_calibration_version):
      return _reject(reasons.DETAIL_CALIBRATION_CHANGED, latest)

    stationary = self._latest_stationary
    since = self._stationary_since_ns
    if stationary is None or since is None:
      return _reject(reasons.DETAIL_DWELL_INCOMPLETE, latest)
    elapsed_ns = stationary.timestamp_ns - since
    elapsed_s = elapsed_ns / NS_PER_S

    if (local_now_ns >= stationary.valid_until_ns
        or local_now_ns - stationary.timestamp_ns >= self.config.max_pose_age_ns):
      return _reject(reasons.DETAIL_SAMPLE_STALE, stationary, elapsed_s)
    if local_now_ns - observation_timestamp_ns > self.config.max_detection_pipeline_latency_ns:
      return _reject(reasons.DETAIL_DETECTION_TOO_OLD, stationary, elapsed_s)
    if observation_timestamp_ns > stationary.timestamp_ns:
      return _reject(reasons.DETAIL_NO_SAMPLE, stationary, elapsed_s)
    if (elapsed_ns - stationary.timestamp_uncertainty_ns - self._stationary_since_uncertainty_ns
        < self.config.max_detection_pipeline_latency_ns):
      return _reject(reasons.DETAIL_DWELL_INCOMPLETE, stationary, elapsed_s)
    if observation_timestamp_ns - self.config.max_detection_timestamp_uncertainty_ns < since:
      return _reject(reasons.DETAIL_OBSERVATION_BEFORE_DWELL, stationary, elapsed_s)
    return AdmissionDecision(True, pose=stationary, dwell_elapsed_s=elapsed_s)
