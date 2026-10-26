# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Sampled structured JSONL decision records for PTZ validation.

One JSON object per line on stdout; the acceptance harness collects them from the
container logs by `run_id`. Services never write artifact files. In shadow mode a
record also carries the candidate (PoseContext) projection of every detection and
its residual against the static home-pose projection.
"""

import copy
import sys
from typing import Any, Dict, List, Optional, TextIO

import numpy as np
import orjson

from scene_common import log

RECORD_TYPE = "ptz_shadow"
PROFILE = "controller"
MAX_RECORD_DETECTIONS = 50


class ShadowRecorder:
  """Deterministic sampling: every Nth decision per source, plus every decision change."""

  def __init__(self, run_id: str, sample_every_n: int, stream: Optional[TextIO] = None):
    self.run_id = run_id
    self.sample_every_n = sample_every_n
    self._stream = stream
    self._counts: Dict[str, int] = {}
    self._last_decision: Dict[str, tuple] = {}

  def _should_emit(self, source_id: str, decision: tuple) -> bool:
    count = self._counts.get(source_id, 0)
    self._counts[source_id] = count + 1
    changed = self._last_decision.get(source_id) != decision
    self._last_decision[source_id] = decision
    return changed or count % self.sample_every_n == 0

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
    stream = self._stream or sys.stdout
    stream.write(orjson.dumps(record, option=orjson.OPT_SERIALIZE_NUMPY).decode("utf-8") + "\n")
    stream.flush()
    return True


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
