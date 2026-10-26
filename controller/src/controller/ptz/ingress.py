# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Ingress gate for PTZ camera detection messages.

Enforcing mode drops a message the dwell contract rejects and hands an admitted one
a per-frame projection context. Shadow mode computes the decision and the candidate
projection for the record only; the message always continues on the static path.
"""

from typing import Any, Dict, Optional, Tuple

from scene_common.positioning_dwell import parse_timestamp_ns, seconds_to_ns
from controller.observability import metrics
from controller.ptz.config import MODE_ENFORCE, MODE_SHADOW, PTZSettings
from controller.ptz.projection import PTZProjectionContext
from controller.ptz.registry import PTZAdmission, PTZPoseRegistry, is_ptz_camera
from controller.ptz.shadow import ShadowRecorder, candidate_residuals


class PTZIngress:

  def __init__(self, settings: PTZSettings, registry: PTZPoseRegistry,
               recorder: ShadowRecorder):
    self.settings = settings
    self.registry = registry
    self.recorder = recorder

  def filter(self, scene: Any, camera_id: str, jdata: Dict[str, Any],
             when: float) -> Tuple[bool, Optional[PTZProjectionContext]]:
    """Decide how a camera message continues.

    @return (process, context): process=False drops the message; a non-None context
            must be passed to Scene.processCameraData for per-frame projection
    """
    camera = scene.cameraWithID(camera_id)
    if camera is None or not is_ptz_camera(camera):
      return True, None

    admission = self.registry.admit(camera, self._observation_ns(jdata, when))
    self._count(admission)
    detections = None
    if self.settings.shadow and admission.admitted and hasattr(camera, 'pose'):
      detections = candidate_residuals(scene, jdata, when, camera, admission.context.camera)
    self.recorder.record(self.settings.mode, scene, camera_id, jdata, admission, detections)

    if self.settings.mode == MODE_SHADOW:
      return True, None
    return admission.admitted, admission.context

  @staticmethod
  def _observation_ns(jdata: Dict[str, Any], when: float) -> int:
    try:
      return parse_timestamp_ns(jdata['timestamp'])
    except (KeyError, TypeError, ValueError):
      return seconds_to_ns(when)

  def _count(self, admission: PTZAdmission) -> None:
    mode = MODE_ENFORCE if self.settings.enforcing else MODE_SHADOW
    if admission.admitted:
      metrics.inc_ptz_admitted({"mode": mode})
      return
    metrics.inc_ptz_rejected({"mode": mode, "reason_detail": admission.reason_detail})
