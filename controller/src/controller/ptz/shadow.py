# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""PTZ decision logging for validation.

By default the Controller logs one human-readable line per camera each time a new
parked pose is applied, summarizing the decisions since the previous line. With
`shadow.per_decision` it instead writes sampled per-decision JSONL records to stdout,
which the acceptance harness collects from the container logs by `run_id`. Services
never write artifact files. In shadow mode both carry the residual of the candidate
(PoseContext) projection of every detection against the static home-pose projection.
"""

import collections
import copy
import sys
from typing import Any, Callable, Dict, List, Optional, Set, TextIO, Tuple

import numpy as np
import orjson

from scene_common import log
from scene_common.positioning_dwell import parse_timestamp_ns

RECORD_TYPE = "ptz_shadow"
PROFILE = "controller"
MAX_RECORD_DETECTIONS = 50
MAX_SUMMARY_SAMPLES = 10000
ADMITTED_KEY = "admitted"
TRANSLATION_REPORT_M = 0.001


def _write(stream: Optional[TextIO], record: Dict[str, Any]) -> None:
  out = stream or sys.stdout
  out.write(orjson.dumps(record, option=orjson.OPT_SERIALIZE_NUMPY).decode("utf-8") + "\n")
  out.flush()


class ShadowRecorder:
  """Deterministic sampling per source: every Nth decision, plus the first occurrence of
  each distinct decision within that window of N.

  A new state (moving, settling, ...) is recorded as soon as it appears, while
  decisions that alternate frame by frame (admitted / no_sample on a parked camera)
  cost at most one record each per window instead of one per frame.
  """

  def __init__(self, run_id: str, sample_every_n: int, stream: Optional[TextIO] = None):
    self.run_id = run_id
    self.sample_every_n = sample_every_n
    self._stream = stream
    self._counts: Dict[str, int] = {}
    self._window_decisions: Dict[str, Set[tuple]] = {}

  def _should_emit(self, source_id: str, decision: tuple) -> bool:
    count = self._counts.get(source_id, 0)
    self._counts[source_id] = count + 1
    if count % self.sample_every_n == 0:
      self._window_decisions[source_id] = {decision}
      return True
    seen = self._window_decisions.setdefault(source_id, set())
    if decision in seen:
      return False
    seen.add(decision)
    return True

  def record(self, mode: str, scene: Any, source_id: str, jdata: Dict[str, Any],
             admission: Any, detections: Optional[List[Dict[str, Any]]] = None) -> bool:
    """Emit a record when sampling selects it; returns whether one was written."""
    decision = (admission.admitted, admission.reason_detail)
    if not self._should_emit(source_id, decision):
      return False
    record = {
      "record_type": RECORD_TYPE,
      "profile": PROFILE,
      "mode": mode,
      "run_id": self.run_id,
      "scene_id": scene.uid,
      "source_id": source_id,
      "sequence": admission.sequence,
      "calibration_version": admission.calibration_version,
      "observation_timestamp": jdata.get("timestamp"),
      "pose_age_s": admission.pose_age_s,
      "timestamp_uncertainty_s": admission.timestamp_uncertainty_s,
      "dwell_elapsed_s": admission.dwell_elapsed_s,
      "admitted": admission.admitted,
      "managed": admission.managed,
      "invalid_reason": admission.invalid_reason,
      "reason_detail": admission.reason_detail,
      "detections": (detections or [])[:MAX_RECORD_DETECTIONS],
    }
    _write(self._stream, record)
    return True


class _Period:
  """Decisions of one source since its previous summary."""

  def __init__(self):
    self.first_ns: Optional[int] = None
    self.last_ns: Optional[int] = None
    self.decisions: collections.Counter = collections.Counter()
    self.residuals = collections.deque(maxlen=MAX_SUMMARY_SAMPLES)
    self.detections = 0

  def add(self, observation: Any, admission: Any,
          detections: Optional[List[Dict[str, Any]]]) -> None:
    observation_ns = _timestamp_ns(observation)
    if observation_ns is not None:
      if self.first_ns is None:
        self.first_ns = observation_ns
      self.last_ns = observation_ns
    self.decisions[ADMITTED_KEY if admission.admitted else str(admission.reason_detail)] += 1
    for detection in detections or []:
      self.detections += 1
      self.residuals.append(detection["residual_m"])

  def describe(self) -> str:
    total = sum(self.decisions.values())
    if total == 0:
      return "no earlier decisions"
    duration = ""
    if self.first_ns is not None and self.last_ns is not None:
      duration = f" {(self.last_ns - self.first_ns) / 1e9:.1f} s"
    admitted = self.decisions.get(ADMITTED_KEY, 0)
    rejected = ", ".join(f"{reason} {count}" for reason, count in self.decisions.most_common()
                         if reason != ADMITTED_KEY)
    text = (f"previous{duration}: {total} decisions, "
            f"{100.0 * admitted / total:.0f}% admitted")
    if rejected:
      text += f" (rejected: {rejected})"
    text += f", {self.detections} detections"
    if self.residuals:
      data = np.asarray(self.residuals, dtype=float)
      text += (f", residual median {np.median(data):.2f} m, "
               f"p95 {np.percentile(data, 95):.2f} m, max {data.max():.2f} m")
    return text


class SummaryRecorder:
  """One Controller log line per source whenever a new parked pose is first applied.

  A pose is new when the dwell that admits it started at a different time, which
  happens after the camera moved, or after a reset (sequence gap, Resolver restart,
  calibration change). The line describes the applied pose and summarizes every
  decision since the previous line, so a parked camera logs nothing.
  """

  def __init__(self, emit: Optional[Callable[[str], None]] = None):
    self._emit = emit or log.info
    self._periods: Dict[str, _Period] = {}
    self._applied: Dict[str, int] = {}

  def record(self, mode: str, scene: Any, source_id: str, jdata: Dict[str, Any],
             admission: Any, detections: Optional[List[Dict[str, Any]]] = None) -> bool:
    """Account for one decision; returns whether a summary was logged."""
    written = False
    since_ns = getattr(admission, "stationary_since_ns", None)
    if admission.admitted and since_ns is not None and self._applied.get(source_id) != since_ns:
      self._applied[source_id] = since_ns
      self._emit(self._summary(mode, source_id, admission))
      self._periods[source_id] = _Period()
      written = True
    period = self._periods.setdefault(source_id, _Period())
    period.add(jdata.get("timestamp"), admission, detections)
    return written

  def _summary(self, mode: str, source_id: str, admission: Any) -> str:
    period = self._periods.get(source_id) or _Period()
    rotation, translation = _offset_from_home(admission.context)
    offset = "offset from home unknown" if rotation is None \
      else f"{rotation:.2f} deg from home"
    if translation is not None and translation >= TRANSLATION_REPORT_M:
      offset += f", {translation:.3f} m from home position"
    return (f"PTZ camera {source_id}: pose applied ({mode}); {offset}, "
            f"dwell {_number(admission.dwell_elapsed_s, 1)} s, "
            f"pose age {_number(admission.pose_age_s, 2)} s; "
            f"calibration={admission.calibration_version}; {period.describe()}")


def _number(value: Optional[float], digits: int) -> str:
  return "?" if value is None else f"{value:.{digits}f}"


def _timestamp_ns(text: Any) -> Optional[int]:
  try:
    return parse_timestamp_ns(text)
  except (AttributeError, TypeError, ValueError):
    return None


def _rotation(matrix: np.ndarray) -> np.ndarray:
  u, _, vt = np.linalg.svd(np.asarray(matrix, dtype=float)[:3, :3])
  return u @ vt


def _offset_from_home(context: Any) -> Tuple[Optional[float], Optional[float]]:
  """Rotation angle (deg) and translation (m) of the applied pose relative to the home pose."""
  try:
    applied = np.asarray(context.camera.pose.pose_mat, dtype=float)
    home = np.asarray(context.camera.static_camera.pose.pose_mat, dtype=float)
    relative = _rotation(home).T @ _rotation(applied)
    cosine = np.clip((np.trace(relative) - 1.0) / 2.0, -1.0, 1.0)
    return (float(np.degrees(np.arccos(cosine))),
            float(np.linalg.norm(applied[:3, 3] - home[:3, 3])))
  except (AttributeError, TypeError, ValueError, np.linalg.LinAlgError):
    return None, None


def candidate_residuals(scene: Any, jdata: Dict[str, Any], when: float, static_camera: Any,
                        candidate_camera: Any) -> Optional[List[Dict[str, Any]]]:
  """Scene locations of every detection projected with the candidate and static cameras.

  Works on copies and never touches tracker state, so it cannot affect live tracking.
  Returns None if the comparison fails; shadow mode must never break the live path.
  """
  try:
    return _residuals(scene, jdata, when, static_camera, candidate_camera)
  except Exception as error:  # shadow observation must not interfere with live tracking
    log.warning(f"PTZ shadow projection failed for {static_camera.cameraID}: {error}")
    return None


def _residuals(scene, jdata, when, static_camera, candidate_camera):
  intrinsics = static_camera.pose.intrinsics
  results = []
  for detection_type, detections in jdata.get("objects", {}).items():
    if not detections:
      continue
    prepared = copy.deepcopy(detections)
    if "intrinsics" not in jdata:
      scene.convertPixelBoundingBoxesToMeters(prepared, intrinsics.intrinsics, intrinsics.distortion)
    static_objects = scene.createMovingObjectsForDetection(
      detection_type, copy.deepcopy(prepared), when, static_camera)
    candidate_objects = scene.createMovingObjectsForDetection(
      detection_type, copy.deepcopy(prepared), when, candidate_camera)
    for static_object, candidate_object in zip(static_objects, candidate_objects):
      static_xyz = np.asarray(static_object.sceneLoc.asCartesianVector, dtype=float)
      candidate_xyz = np.asarray(candidate_object.sceneLoc.asCartesianVector, dtype=float)
      results.append({
        "type": detection_type,
        "static_xyz": static_xyz.tolist(),
        "candidate_xyz": candidate_xyz.tolist(),
        "residual_m": float(np.linalg.norm(candidate_xyz - static_xyz)),
      })
  return results
