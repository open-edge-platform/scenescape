# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Per-source PTZ pose state for the Controller.

Holds one `DwellTracker` per PTZ camera of the loaded scenes that the deployment
assigns to a Resolver. Pose and status messages arrive on the MQTT network thread
and are untrusted: they are size-bounded, schema-validated, guarded and matched to
a managed source before they touch dwell state. Detections are admitted or dropped
immediately; nothing is queued or waited for.
"""

import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

import orjson

from scene_common import log
from scene_common import positioning_reasons as reasons
from scene_common.mqtt import PubSub
from scene_common.positioning_dwell import (
  NS_PER_S, DwellConfig, DwellTracker, PoseSnapshot, parse_timestamp_ns)
from scene_common.positioning_schema_guards import (
  PoseContextGuardError, check_payload_size, validate_pose_context_payload)
from controller.observability import metrics
from controller.ptz.config import PTZSettings
from controller.ptz.projection import ProjectedCamera, PTZProjectionContext

MAX_STATUS_BYTES = 1024
SCHEMA_POSE_CONTEXT = "pose_context"
SCHEMA_STATUS = "positioning_status"

# Bounded label values for scenescape_controller_ptz_pose_messages_rejected
STAGE_SIZE = "size"
STAGE_JSON = "json"
STAGE_SCHEMA = "schema"
STAGE_GUARD = "guard"
STAGE_TOPIC = "topic"
STAGE_UNMANAGED = "unmanaged"

Clock = Callable[[], Tuple[int, bool]]


def is_ptz_camera(camera: Any) -> bool:
  return getattr(camera, "ptz_calibration", None) is not None


def frame_id_for_scene(scene_uid: str) -> str:
  return f"scene:{scene_uid}"


@dataclass(frozen=True)
class PTZAdmission:
  """Outcome of the dwell contract for one camera message."""
  admitted: bool
  managed: bool = True
  invalid_reason: Optional[str] = None
  reason_detail: Optional[str] = None
  context: Optional[PTZProjectionContext] = None
  sequence: Optional[int] = None
  calibration_version: Optional[str] = None
  pose_age_s: Optional[float] = None
  timestamp_uncertainty_s: Optional[float] = None
  dwell_elapsed_s: Optional[float] = None


class _SourceState:
  def __init__(self, tracker: DwellTracker, scene_uid: str, resolver_id: str):
    self.tracker = tracker
    self.scene_uid = scene_uid
    self.resolver_id = resolver_id
    self.projected: Optional[ProjectedCamera] = None


def _rejection(detail: str, managed: bool = True, pose: Optional[PoseSnapshot] = None,
               local_now_ns: Optional[int] = None,
               dwell_elapsed_s: Optional[float] = None) -> PTZAdmission:
  age = None
  if pose is not None and local_now_ns is not None:
    age = max(0.0, (local_now_ns - pose.timestamp_ns) / NS_PER_S)
  return PTZAdmission(
    admitted=False, managed=managed, invalid_reason=reasons.canonical_reason(detail),
    reason_detail=detail,
    sequence=pose.sequence if pose else None,
    calibration_version=pose.calibration_version if pose else None,
    pose_age_s=age,
    timestamp_uncertainty_s=pose.timestamp_uncertainty_ns / NS_PER_S if pose else None,
    dwell_elapsed_s=dwell_elapsed_s)


class PTZPoseRegistry:

  def __init__(self, settings: PTZSettings, schema_validation: Any, clock: Clock):
    """
    @param settings           validated PTZ consumer settings
    @param schema_validation  SchemaValidation loaded with the pose_context/status schemas
    @param clock              returns (synchronized local time in ns, clock within bound)
    """
    self.settings = settings
    self._schema = schema_validation
    self._clock = clock
    self._dwell_config = DwellConfig.from_consumer_config(settings.consumer)
    self._lock = threading.Lock()
    self._states: Dict[str, _SourceState] = {}
    self._unassigned: frozenset = frozenset()
    self._reported_unassigned: set = set()

  # Configuration

  def reconcile(self, scenes: Iterable[Any]) -> None:
    """Align managed sources with the PTZ cameras of the loaded scenes."""
    wanted: Dict[str, Tuple[str, str, Optional[str]]] = {}
    unassigned = set()
    for scene in scenes:
      for camera_id, camera in scene.cameras.items():
        if not is_ptz_camera(camera):
          continue
        resolver_id = self.settings.assignments.get(camera_id)
        if resolver_id is None:
          unassigned.add(camera_id)
          continue
        wanted[camera_id] = (scene.uid, resolver_id,
                             camera.ptz_calibration.get("calibration_version"))
    with self._lock:
      self._apply(wanted)
      self._unassigned = frozenset(unassigned)
      self._reported_unassigned &= unassigned

  def _apply(self, wanted: Mapping[str, Tuple[str, str, Optional[str]]]) -> None:
    for camera_id in list(self._states):
      state = self._states[camera_id]
      target = wanted.get(camera_id)
      if target is None or (target[0], target[1]) != (state.scene_uid, state.resolver_id):
        del self._states[camera_id]
    for camera_id, (scene_uid, resolver_id, version) in wanted.items():
      state = self._states.get(camera_id)
      if state is None:
        tracker = DwellTracker(camera_id, resolver_id, self._dwell_config,
                               expected_frame_id=frame_id_for_scene(scene_uid),
                               expected_calibration_version=version)
        self._states[camera_id] = _SourceState(tracker, scene_uid, resolver_id)
      else:
        state.tracker.set_expected_calibration_version(version)

  def pose_source_ids(self) -> List[str]:
    with self._lock:
      return sorted(self._states)

  def resolver_ids(self) -> List[str]:
    with self._lock:
      return sorted({state.resolver_id for state in self._states.values()})

  # Inbound MQTT

  def on_pose_message(self, topic: str, raw: bytes) -> Optional[str]:
    """Apply a PoseContext; returns the rejection stage, or None when applied."""
    stage = self._apply_pose(topic, raw)
    if stage is not None:
      metrics.inc_ptz_pose_rejected({"stage": stage})
    return stage

  def _apply_pose(self, topic: str, raw: bytes) -> Optional[str]:
    try:
      check_payload_size(raw)
    except PoseContextGuardError:
      return STAGE_SIZE
    payload = self._decode(raw)
    if payload is None:
      return STAGE_JSON
    if not self._schema.validateMessage(SCHEMA_POSE_CONTEXT, payload, check_format=True):
      return STAGE_SCHEMA
    try:
      validate_pose_context_payload(payload)
      snapshot = PoseSnapshot.from_payload(payload)
    except PoseContextGuardError:
      return STAGE_GUARD
    except (ValueError, KeyError, TypeError):
      return STAGE_SCHEMA
    topic_source = self._topic_value(topic, "source_id")
    if topic_source is None:
      return STAGE_TOPIC
    # Routed by topic; a payload naming another source resets that source's dwell
    with self._lock:
      state = self._states.get(topic_source)
      if state is None:
        return STAGE_UNMANAGED
      state.tracker.on_pose(snapshot)
    return None

  def on_status_message(self, topic: str, raw: bytes) -> Optional[str]:
    """Apply a resolver status/LWT; returns the rejection stage, or None when applied."""
    stage = self._apply_status(topic, raw)
    if stage is not None:
      metrics.inc_ptz_pose_rejected({"stage": stage})
    return stage

  def _apply_status(self, topic: str, raw: bytes) -> Optional[str]:
    if len(raw) > MAX_STATUS_BYTES:
      return STAGE_SIZE
    payload = self._decode(raw)
    if payload is None:
      return STAGE_JSON
    if not self._schema.validateMessage(SCHEMA_STATUS, payload, check_format=True):
      return STAGE_SCHEMA
    resolver_id = payload["resolver_id"]
    if self._topic_value(topic, "resolver_id") != resolver_id:
      return STAGE_TOPIC
    try:
      session_ns = parse_timestamp_ns(payload["timestamp"])
    except ValueError:
      return STAGE_SCHEMA
    with self._lock:
      for state in self._states.values():
        state.tracker.on_status(resolver_id, payload["status"], session_ns)
    return None

  @staticmethod
  def _decode(raw: bytes):
    try:
      return orjson.loads(raw)
    except orjson.JSONDecodeError:
      return None

  @staticmethod
  def _topic_value(topic: str, key: str) -> Optional[str]:
    try:
      return (PubSub.parseTopic(topic) or {}).get(key)
    except (ValueError, KeyError):
      return None

  # Admission and visibility

  def admit(self, camera: Any, observation_ns: int,
            local_now_ns: Optional[int] = None) -> PTZAdmission:
    """Dwell decision for a detection message of a PTZ camera (never blocks or queues)."""
    now_ns, synchronized = self._clock()
    if local_now_ns is not None:
      now_ns = local_now_ns
    with self._lock:
      state = self._states.get(camera.cameraID)
      if state is None:
        self._report_unassigned(camera.cameraID)
        return _rejection(reasons.DETAIL_NO_SAMPLE, managed=False)
      decision = state.tracker.evaluate(observation_ns, now_ns)
      if not synchronized and decision.admitted:
        return _rejection(reasons.DETAIL_SAMPLE_STALE, pose=decision.pose, local_now_ns=now_ns,
                          dwell_elapsed_s=decision.dwell_elapsed_s)
      if not decision.admitted:
        return PTZAdmission(
          admitted=False, invalid_reason=decision.invalid_reason,
          reason_detail=decision.reason_detail, dwell_elapsed_s=decision.dwell_elapsed_s,
          **self._pose_fields(decision.pose, now_ns))
      pose = decision.pose
      return PTZAdmission(
        admitted=True, dwell_elapsed_s=decision.dwell_elapsed_s,
        context=PTZProjectionContext(
          source_id=pose.source_id, sequence=pose.sequence,
          calibration_version=pose.calibration_version, frame_id=pose.frame_id,
          pose_timestamp_ns=pose.timestamp_ns,
          timestamp_uncertainty_s=pose.timestamp_uncertainty_ns / NS_PER_S,
          dwell_elapsed_s=decision.dwell_elapsed_s,
          camera=self._projected(state, camera, pose)),
        **self._pose_fields(pose, now_ns))

  @staticmethod
  def _pose_fields(pose: Optional[PoseSnapshot], now_ns: int) -> Dict[str, Any]:
    if pose is None:
      return {}
    return {
      "sequence": pose.sequence,
      "calibration_version": pose.calibration_version,
      "pose_age_s": max(0.0, (now_ns - pose.timestamp_ns) / NS_PER_S),
      "timestamp_uncertainty_s": pose.timestamp_uncertainty_ns / NS_PER_S,
    }

  def _report_unassigned(self, camera_id: str) -> None:
    if camera_id in self._reported_unassigned:
      return
    self._reported_unassigned.add(camera_id)
    log.error(f"PTZ camera {camera_id} has no resolver in the positioning assignment "
              "manifest; its detections are dropped")

  def visibility_camera(self, camera: Any) -> Optional[Any]:
    """Camera to use for visibility: the static one, a per-frame view, or None (not visible).

    A PTZ camera without a valid, fresh, matching pose does not see anything; the
    home view region is never used as a fallback.
    """
    if not is_ptz_camera(camera) or not self.settings.enforcing:
      return camera
    now_ns, synchronized = self._clock()
    with self._lock:
      state = self._states.get(camera.cameraID)
      latest = state.tracker.latest_pose if state else None
      if latest is None or not synchronized or not self._usable_for_visibility(
          state, latest, now_ns):
        return None
      return self._projected(state, camera, latest)

  def _usable_for_visibility(self, state: _SourceState, pose: PoseSnapshot, now_ns: int) -> bool:
    tracker = state.tracker
    return (pose.valid and pose.frame_id == tracker.expected_frame_id
            and (tracker.expected_calibration_version is None
                 or pose.calibration_version == tracker.expected_calibration_version)
            and now_ns < pose.valid_until_ns
            and now_ns - pose.timestamp_ns < self._dwell_config.max_pose_age_ns)

  @staticmethod
  def _projected(state: _SourceState, camera: Any, pose: PoseSnapshot) -> ProjectedCamera:
    cached = state.projected
    if cached is None or cached.sequence != pose.sequence or cached.static_camera is not camera:
      cached = ProjectedCamera(camera, pose)
      state.projected = cached
    return cached
