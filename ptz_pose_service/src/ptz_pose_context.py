#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Core logic for the PTZ Pose Service.

For each configured ONVIF PTZ camera, this polls its pan/tilt position at a
fixed rate, compares it against the position where the camera was calibrated
for the scene ("home"), and pushes an updated ``rotation`` to the matching
Scenescape camera via the REST API whenever the change is significant.
"""

from __future__ import annotations

import json
import os
import signal
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional

from scene_common import log
from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient

from dlstreamer.onvif import (
    discover_onvif_cameras,
    find_ptz_capable_profiles,
    PTZController,
)

from pose_math import (
    rotation_delta_magnitude, scale_from_fov, axis_angle_degrees, apply_backlash,
    compose_ptz_rotation, implausible_recalibration_reason,
    visible_point_correspondences, split_point_correspondence_transforms,
    join_point_correspondence_transforms,
)
from auto_recalibration import AutoRecalibrator

# Scenescape transform type used by the AprilTag/auto calibration flow.
POINT_CORRESPONDENCE_TRANSFORM = '3d-2d point correspondence'
# Scenescape's solvePnP falls back to P3P below 6 non-coplanar points, which
# only accepts exactly 4, so require enough for its iterative solver.
MIN_PNP_POINTS = 6
HOME_APPROACHES = ('increasing', 'decreasing')

# An ONVIF AbsolutePanTiltPositionSpace whose URI advertises the generic,
# normalized space (conventionally [-1, 1]) - or whose reported range simply
# isn't wide enough to plausibly already be real degrees - can't be trusted
# as a 1:1 degrees-per-unit mapping. Such cameras need an explicitly
# configured pan_degrees/tilt_degrees (the camera's real physical sweep, from
# its datasheet) to convert their readings into degrees.
GENERIC_SPACE_SPAN_THRESHOLD_DEG = 4.0

# Assumed position-reporting range when a camera's ONVIF profile doesn't
# advertise an AbsolutePanTiltPositionSpace at all, so a manually-configured
# pan_degrees/tilt_degrees FOV still has something to scale against (see
# PTZPoseContext._resolveAxisScales).
DEFAULT_POSITION_SPACE = (-1.0, 1.0)

# How a camera's Scenescape pose is kept in sync with its live PTZ position:
#   MODE_PTZ_DELTA  - rotate the calibrated "home" pose by the pan/tilt delta,
#                     converted to degrees via pan_degrees/tilt_degrees (or an
#                     explicit pan_scale/tilt_scale). Fast, no video needed.
#   MODE_AUTOCALIBRATION - run a full AprilTag re-calibration after each move.
#                     Opt-in: needs a clear view of well-distributed tags, and
#                     is rejected outright when that geometry is degenerate.
MODE_PTZ_DELTA = "ptz_delta"
MODE_AUTOCALIBRATION = "autocalibration"
POSE_UPDATE_MODES = (MODE_PTZ_DELTA, MODE_AUTOCALIBRATION)


@dataclass
class TrackedCamera:
  """Runtime state for one ONVIF PTZ camera bound to a Scenescape camera."""

  scene_camera_uid: str
  camera_name: str
  onvif_host: str
  onvif_port: int
  controller: PTZController
  home_rotation: List[float]
  home_translation: List[float]
  home_pan: float
  home_tilt: float
  pan_scale: float = 1.0
  tilt_scale: float = 1.0
  # Optional polynomials replacing the constant scales for heads whose travel
  # isn't uniform (see pose_math.axis_delta_degrees).
  pan_curve: Optional[List[float]] = None
  tilt_curve: Optional[List[float]] = None
  # Gear slack, in degrees, and the physical angle each axis is tracked to be
  # at within it (see pose_math.apply_backlash).
  pan_backlash_deg: float = 0.0
  tilt_backlash_deg: float = 0.0
  pan_physical_deg: Optional[float] = None
  tilt_physical_deg: Optional[float] = None
  home_pan_physical_deg: float = 0.0
  home_tilt_physical_deg: float = 0.0
  # Direction the ONVIF position was moving when the home pose was calibrated
  # ('increasing'/'decreasing'), or None if unknown.
  pan_home_approach: Optional[str] = None
  tilt_home_approach: Optional[str] = None
  # World-frame pan axis; None means world vertical.
  pan_axis: Optional[List[float]] = None
  invert_pan: bool = False
  invert_tilt: bool = False
  last_applied_rotation: List[float] = field(default_factory=list)
  label: str = ""
  pose_update_mode: str = MODE_PTZ_DELTA
  # Calibration correspondences reprojected on each pose update so the UI's
  # 2D calibration view keeps its points (see _buildPoseUpdate).
  home_points_3d: Optional[List[List[float]]] = None
  intrinsics: Optional[dict] = None
  distortion: Optional[dict] = None
  last_raw_pan: float = 0.0
  last_raw_tilt: float = 0.0
  last_raw_change_time: float = 0.0
  pending_recal: bool = False
  recal_in_progress: bool = False
  last_observed_rotation: List[float] = field(default_factory=list)
  last_pose_change_time: float = 0.0
  pose_settle_s: float = 0.5
  # Pose last written by this service, used to tell its own updates apart from
  # a calibration applied elsewhere (see PTZPoseContext._rebaselineIfRecalibrated).
  last_written_transforms: Optional[List[float]] = None
  last_written_rotation: Optional[List[float]] = None
  last_rebaseline_check: float = 0.0

  @property
  def needs_recalibration(self) -> bool:
    return self.pose_update_mode == MODE_AUTOCALIBRATION

  def __post_init__(self):
    if not self.last_applied_rotation:
      self.last_applied_rotation = list(self.home_rotation)
    if not self.last_observed_rotation:
      self.last_observed_rotation = list(self.home_rotation)
    if not self.label:
      self.label = f"{self.onvif_host}:{self.onvif_port} -> {self.scene_camera_uid}"
    if not self.last_raw_change_time:
      self.last_raw_change_time = time.monotonic()
    return


class PTZPoseContext:
  """Discovers/loads configured PTZ cameras and keeps their Scenescape pose
  synchronized with the camera's live pan/tilt position."""

  def __init__(self, resturl, restauth, rootcert, config_path,
               onvif_username="", onvif_password="",
               poll_hz=5.0, min_delta_deg=0.2,
               default_pan_scale=1.0, default_tilt_scale=1.0,
               default_invert_pan=False, default_invert_tilt=False,
               broker="broker.scenescape.intel.com", brokerauth=None, brokerrootcert=None,
               autocalibration_url="https://autocalibration.scenescape.intel.com:8443/v1",
               autocalibration_rootcert=None,
               min_raw_delta=0.02, recal_settle_s=2.0,
               min_camera_height=0.1, max_translation_drift=1.0,
               default_pose_update_mode=MODE_PTZ_DELTA,
               rebaseline_check_s=2.0, rebaseline_tolerance_deg=0.5,
               notify_ui=True, pose_settle_s=0.5):
    self.resturl = resturl
    self.restauth = restauth
    self.rootcert = rootcert
    self.config_path = config_path
    self.onvif_username = onvif_username
    self.onvif_password = onvif_password
    self.poll_period = 1.0 / poll_hz if poll_hz > 0 else 0.2
    self.min_delta_deg = min_delta_deg
    self.default_pan_scale = default_pan_scale
    self.default_tilt_scale = default_tilt_scale
    self.default_invert_pan = default_invert_pan
    self.default_invert_tilt = default_invert_tilt
    self.default_pose_update_mode = default_pose_update_mode
    self.pose_settle_s = pose_settle_s
    # How often to check whether the stored pose was changed by someone else
    # (e.g. a manual re-calibration), and how much difference counts as one.
    self.rebaseline_check_s = rebaseline_check_s
    self.rebaseline_tolerance_deg = rebaseline_tolerance_deg
    self.notify_ui = notify_ui
    self.notify_pubsub = None

    self.broker = broker
    self.brokerauth = brokerauth
    self.brokerrootcert = brokerrootcert
    self.autocalibration_url = autocalibration_url
    self.autocalibration_rootcert = autocalibration_rootcert
    # Minimum raw ONVIF pan/tilt unit change (not degrees - these cameras'
    # units can't be reliably converted) before a camera in recalibration
    # fallback mode is considered to have moved.
    self.min_raw_delta = min_raw_delta
    # How long a camera's raw pan/tilt must stay still before triggering
    # recalibration, so a single pan/tilt sweep doesn't retrigger repeatedly.
    self.recal_settle_s = recal_settle_s
    # Sanity thresholds applied to every auto-recalibration result before
    # it's trusted (see pose_math.implausible_recalibration_reason).
    self.min_camera_height = min_camera_height
    self.max_translation_drift = max_translation_drift
    self.recalibrator: Optional[AutoRecalibrator] = None

    self.rest = RESTClient(resturl, rootcert=rootcert, auth=restauth)
    self.cameras: List[TrackedCamera] = []
    self._running = True
    signal.signal(signal.SIGTERM, self._handleShutdown)
    signal.signal(signal.SIGINT, self._handleShutdown)
    return

  def _handleShutdown(self, signum, frame):
    log.info(f"Received signal {signum}, shutting down")
    self._running = False
    return

  @staticmethod
  def logDiscoveredCameras(onvif_username="", onvif_password=""):
    """Discover ONVIF cameras on the network and log which ones are PTZ
    capable. Informational only; does not affect the polling loop and does
    not require a Scenescape REST connection. Useful for populating the
    camera map config file."""
    log.info("Discovering ONVIF cameras on the network...")
    cameras = list(discover_onvif_cameras())
    if not cameras:
      log.info("No ONVIF cameras discovered")
      return
    for cam in cameras:
      log.info(f"Discovered ONVIF camera {cam['hostname']}:{cam['port']}")
    ptz_profiles = list(find_ptz_capable_profiles(
        cameras, onvif_username, onvif_password))
    if not ptz_profiles:
      log.info("No PTZ-capable profiles found on discovered cameras")
      return
    for profile in ptz_profiles:
      log.info(
          f"PTZ-capable profile: host={profile.hostname} port={profile.port} "
          f"profile_token={profile.profile_token} name={profile.profile_name}")
    return

  def _loadConfig(self):
    if not os.path.exists(self.config_path):
      log.warning(f"Config file {self.config_path} not found, no cameras configured")
      return []
    with open(self.config_path, encoding='utf-8') as f:
      data = json.load(f)
    return data.get('cameras', [])

  def _resolveProfileToken(self, host, port, profile_token):
    if profile_token:
      return profile_token
    profiles = list(find_ptz_capable_profiles(
        [{"hostname": host, "port": port}], self.onvif_username, self.onvif_password))
    if not profiles:
      raise RuntimeError(f"No PTZ-capable profile found on {host}:{port}")
    return profiles[0].profile_token

  @staticmethod
  def _getAbsolutePanTiltRange(controller):
    """Query the camera's advertised absolute pan/tilt position range.

    @return     ((pan_min, pan_max, pan_uri), (tilt_min, tilt_max, tilt_uri))
                in the camera's own reported units (e.g. normalized [-1, 1]
                or degrees, depending on the camera), or None if the camera
                doesn't advertise an AbsolutePanTiltPositionSpace.
    """
    try:
      nodes = controller.get_nodes()
    except Exception:
      return None
    for node in nodes:
      spaces = getattr(node, 'SupportedPTZSpaces', None)
      abs_spaces = getattr(spaces, 'AbsolutePanTiltPositionSpace', None) if spaces else None
      if not abs_spaces:
        continue
      space = abs_spaces[0]
      x_range = getattr(space, 'XRange', None)
      y_range = getattr(space, 'YRange', None)
      if x_range is None or y_range is None:
        continue
      uri = getattr(space, 'URI', '') or ''
      return ((float(x_range.Min), float(x_range.Max), uri),
              (float(y_range.Min), float(y_range.Max), uri))
    return None

  @staticmethod
  def _isReliableDegreeSpace(pan_range, tilt_range):
    """Heuristic: is an advertised AbsolutePanTiltPositionSpace usable as a
    1:1 degrees-per-unit mapping (i.e. its raw values can be treated as
    degrees directly, scale=1.0), without a configured pan_degrees/
    tilt_degrees field of view to derive a scale from?

    ONVIF's generic normalized space (conventionally [-1, 1], URI containing
    "Generic") never qualifies. Beyond that, a narrow range (e.g. [-1, 1])
    that isn't explicitly flagged "Generic" is still not trustworthy as
    real degrees, so a minimum span is also required.
    """
    (pan_min, pan_max, pan_uri) = pan_range
    (tilt_min, tilt_max, tilt_uri) = tilt_range
    if 'generic' in pan_uri.lower() or 'generic' in tilt_uri.lower():
      return False
    if (pan_max - pan_min) <= GENERIC_SPACE_SPAN_THRESHOLD_DEG:
      return False
    if (tilt_max - tilt_min) <= GENERIC_SPACE_SPAN_THRESHOLD_DEG:
      return False
    return True

  def _resolveAxisScales(self, controller, host, port, entry):
    """Determine degrees-per-unit pan/tilt scale factors for a camera, and
    whether that mapping can be trusted at all.

    Priority: an explicit ``pan_scale``/``tilt_scale`` in the config always
    wins (assumed reliable). Otherwise, if ``pan_degrees``/``tilt_degrees``
    (the camera's real physical field of view, e.g. from its datasheet) is
    configured, the scale is derived from the camera's own advertised
    AbsolutePanTiltPositionSpace range (queried via ONVIF GetNodes) so that
    cameras with different position-reporting units and different physical
    sweep ranges (e.g. 360° vs. 90° pan) are all normalized correctly. If the
    camera's ONVIF profile doesn't advertise a position range at all,
    ``pan_degrees``/``tilt_degrees`` is still honored by assuming the
    standard ONVIF generic normalized range (``[-1, 1]``) - the vast
    majority of ONVIF PTZ cameras report GetStatus position in that space
    even when GetNodes doesn't expose it - so a manually-configured FOV
    isn't silently discarded just because a camera omits that metadata.

    If neither is configured, the camera's advertised position space is
    inspected: a real degree-reporting space is trusted with scale 1.0, but
    a generic/normalized space (see ``_isReliableDegreeSpace``) is flagged
    as unreliable so the caller can fall back to auto-recalibration instead
    of guessing a linear approximation.

    @return     (pan_scale, tilt_scale, reliable)
    """
    pan_scale = entry.get('pan_scale')
    tilt_scale = entry.get('tilt_scale')
    if pan_scale is not None and tilt_scale is not None:
      return float(pan_scale), float(tilt_scale), True

    pan_fov = entry.get('pan_degrees')
    tilt_fov = entry.get('tilt_degrees')
    ranges = self._getAbsolutePanTiltRange(controller)

    if ranges is None:
      if pan_fov is not None or tilt_fov is not None:
        log.warning(
            f"{host}:{port} did not report an absolute PTZ position range; "
            f"assuming the standard ONVIF generic normalized range {DEFAULT_POSITION_SPACE} "
            "to apply the configured pan_degrees/tilt_degrees")
        return (
            float(pan_scale) if pan_scale is not None
            else scale_from_fov(*DEFAULT_POSITION_SPACE, pan_fov) if pan_fov is not None
            else self.default_pan_scale,
            float(tilt_scale) if tilt_scale is not None
            else scale_from_fov(*DEFAULT_POSITION_SPACE, tilt_fov) if tilt_fov is not None
            else self.default_tilt_scale,
            True,
        )
      return (
          float(pan_scale) if pan_scale is not None else self.default_pan_scale,
          float(tilt_scale) if tilt_scale is not None else self.default_tilt_scale,
          True,
      )

    (pan_min, pan_max, pan_uri), (tilt_min, tilt_max, tilt_uri) = ranges
    log.info(
        f"{host}:{port} PTZ position space: pan range=[{pan_min}, {pan_max}] "
        f"tilt range=[{tilt_min}, {tilt_max}]")

    if pan_fov is not None or tilt_fov is not None:
      if pan_scale is None:
        pan_scale = (scale_from_fov(pan_min, pan_max, pan_fov)
                     if pan_fov is not None else self.default_pan_scale)
      if tilt_scale is None:
        tilt_scale = (scale_from_fov(tilt_min, tilt_max, tilt_fov)
                      if tilt_fov is not None else self.default_tilt_scale)
      return float(pan_scale), float(tilt_scale), True

    reliable = self._isReliableDegreeSpace(
        (pan_min, pan_max, pan_uri), (tilt_min, tilt_max, tilt_uri))
    if not reliable:
      log.warning(
          f"{host}:{port} reports a generic/normalized PTZ position space "
          f"(pan URI={pan_uri!r}, pan range=[{pan_min}, {pan_max}], "
          f"tilt range=[{tilt_min}, {tilt_max}]) with no pan_degrees/tilt_degrees "
          f"configured, so its readings can't be converted to degrees; pose updates will "
          f"use the --pan-scale/--tilt-scale defaults "
          f"({self.default_pan_scale}/{self.default_tilt_scale}) and are unlikely to be "
          "accurate. Set pan_degrees/tilt_degrees (the camera's physical sweep, from its "
          f"datasheet) for this camera, or switch it to '{MODE_AUTOCALIBRATION}' mode.")
    return self.default_pan_scale, self.default_tilt_scale, reliable

  def _fetchCameraInfo(self, scene_camera_uid):
    """Fetch a camera's calibrated rotation/translation and name from Scenescape.

    The name is required because the REST API's partial-update validation
    rejects any update that isn't scene-only relink unless 'name' is
    included. ``translation``/``scale``/``transform_type`` must also all be
    resent alongside ``rotation`` on every update: 'rotation' and
    'translation' are read-only computed fields unless the request also
    includes ``transform_type: "euler"`` and ``scale`` (see
    ``manager.serializers.CamSerializer.map_transform_fields``); without
    that, a PATCH with only 'rotation' is silently accepted (200 OK) but
    has no effect on cameras calibrated via point-correspondence (e.g. the
    auto/AprilTag calibration flow).
    """
    result = self.rest.getCamera(scene_camera_uid)
    if result.errors:
      raise RuntimeError(f"Failed to fetch camera {scene_camera_uid}: {result.errors}")
    rotation = result.get('rotation')
    if not rotation or len(rotation) != 3:
      raise RuntimeError(
          f"Camera {scene_camera_uid} has no valid 'rotation' set; calibrate it first")
    translation = result.get('translation')
    if not translation or len(translation) != 3:
      raise RuntimeError(
          f"Camera {scene_camera_uid} has no valid 'translation' set; calibrate it first")
    name = result.get('name')
    if not name:
      raise RuntimeError(f"Camera {scene_camera_uid} has no 'name' set")
    # Cameras calibrated through the AprilTag/auto flow store 3D-2D point
    # correspondences that the UI draws in the 2D calibration view. Keep them
    # so pose updates can reproject rather than discard them (see
    # _buildPoseUpdate).
    points_2d = points_3d = None
    if result.get('transform_type') == POINT_CORRESPONDENCE_TRANSFORM:
      split = split_point_correspondence_transforms(result.get('transforms') or [])
      if split is not None:
        points_2d, points_3d = split
    info = {
        'rotation': [float(v) for v in rotation],
        'translation': [float(v) for v in translation],
        'name': name,
        'intrinsics': result.get('intrinsics'),
        'distortion': result.get('distortion'),
        'transforms': result.get('transforms'),
        'points_2d': points_2d,
        'points_3d': points_3d,
    }
    return info

  def _applyConfiguredIntrinsics(self, scene_camera_uid, entry):
    """Push any ``intrinsics``/``distortion``/``resolution`` configured for a
    camera to Scenescape before its pose is read.

    Scenescape defaults a newly added camera to a rough guess (a single FOV
    value), but AprilTag calibration and pose reprojection both solve against
    these numbers, so using the camera's real datasheet/calibration values
    materially improves accuracy. Declaring them in the camera map makes them
    survive a database reset instead of having to be re-entered in the UI.
    """
    update = {key: entry[key] for key in ('intrinsics', 'distortion', 'resolution')
              if entry.get(key) is not None}
    if not update:
      return

    result = self.rest.getCamera(scene_camera_uid)
    if result.errors:
      raise RuntimeError(f"Failed to fetch camera {scene_camera_uid}: {result.errors}")
    if all(result.get(key) == value for key, value in update.items()):
      return

    update['name'] = result.get('name')
    result = self.rest.updateCamera(scene_camera_uid, update)
    if result.errors:
      log.error(f"Failed to apply configured intrinsics to {scene_camera_uid}: {result.errors}")
      return
    log.info(f"Applied configured intrinsics to {scene_camera_uid}: {update}")
    return

  def _buildPoseUpdate(self, camera: "TrackedCamera", rotation, translation):
    """Builds the REST payload to persist a new camera pose.

    For a camera calibrated from 3D-2D point correspondences, the stored
    world points are physically fixed, so the new pose is expressed by
    reprojecting them to their new pixel positions. That keeps the camera on
    its native transform type (the 2D calibration view still has points to
    draw) and Scenescape re-derives the same pose from them via solvePnP.

    Otherwise a plain euler pose is used. ``transform_type`` and ``scale``
    must be included alongside ``rotation``/``translation`` (see
    ``_fetchCameraInfo``) or the update is silently ignored.

    @return  the update payload, or None if this pose can't be represented
             without destroying the camera's calibration points
    """
    if camera.home_points_3d and camera.intrinsics:
      points_2d, points_3d = visible_point_correspondences(
          camera.home_points_3d, rotation, translation, camera.intrinsics,
          camera.distortion)
      if len(points_3d) < MIN_PNP_POINTS:
        # Writing a euler pose here would drop the correspondences entirely
        # and they could only be recovered by re-calibrating, so leave the
        # stored pose alone until the camera points somewhere usable again.
        log.warning(
            f"{camera.label}: only {len(points_3d)} of {len(camera.home_points_3d)} "
            f"calibration points visible (need {MIN_PNP_POINTS}); keeping the previous pose")
        return None
      return {
          'name': camera.camera_name,
          'transform_type': POINT_CORRESPONDENCE_TRANSFORM,
          'transforms': join_point_correspondence_transforms(points_2d, points_3d),
      }

    return {
        'name': camera.camera_name,
        'transform_type': 'euler',
        'rotation': rotation,
        'translation': translation,
        'scale': [1.0, 1.0, 1.0],
    }

  def _rotationFor(self, camera: "TrackedCamera", pan, tilt):
    """Rotation the camera is at now, tracking each axis through its backlash.

    The physical angle is carried between polls because backlash is history
    dependent: the same reported position means different things depending on
    which way the head last travelled.
    """
    reported_pan = axis_angle_degrees(pan, camera.pan_scale, camera.pan_curve,
                                      camera.invert_pan)
    reported_tilt = axis_angle_degrees(tilt, camera.tilt_scale, camera.tilt_curve,
                                       camera.invert_tilt)
    camera.pan_physical_deg = apply_backlash(
        camera.pan_physical_deg, reported_pan, camera.pan_backlash_deg)
    camera.tilt_physical_deg = apply_backlash(
        camera.tilt_physical_deg, reported_tilt, camera.tilt_backlash_deg)

    delta_pan = camera.pan_physical_deg - camera.home_pan_physical_deg
    delta_tilt = camera.tilt_physical_deg - camera.home_tilt_physical_deg
    return (compose_ptz_rotation(camera.home_rotation, delta_pan, delta_tilt, camera.pan_axis),
            delta_pan, delta_tilt)

  def _resetBacklashState(self, camera: "TrackedCamera"):
    """Initialise backlash tracking at the camera's home position.

    The physical angle trails the reported one by half the slack on the side
    the head last came from. If that direction was declared (``*_home_approach``)
    it is used; otherwise the angle is assumed mid-band, which leaves up to
    half the slack of error in *both* directions.
    """
    camera.home_pan_physical_deg = self._homePhysicalAngle(
        camera.home_pan, camera.pan_scale, camera.pan_curve, camera.invert_pan,
        camera.pan_backlash_deg, camera.pan_home_approach)
    camera.home_tilt_physical_deg = self._homePhysicalAngle(
        camera.home_tilt, camera.tilt_scale, camera.tilt_curve, camera.invert_tilt,
        camera.tilt_backlash_deg, camera.tilt_home_approach)
    camera.pan_physical_deg = camera.home_pan_physical_deg
    camera.tilt_physical_deg = camera.home_tilt_physical_deg
    return

  @staticmethod
  def _homePhysicalAngle(position, scale, curve, invert, backlash_deg, approach):
    reported = axis_angle_degrees(position, scale, curve, invert)
    if not approach or backlash_deg <= 0.0:
      return reported
    if approach not in HOME_APPROACHES:
      raise ValueError(f"Unknown home approach {approach!r}; expected one of {HOME_APPROACHES}")
    # Sign of d(angle)/d(position): scale, curve and invert can all flip it.
    ahead = axis_angle_degrees(position + 1e-3, scale, curve, invert)
    direction = 1.0 if ahead >= reported else -1.0
    if approach == 'decreasing':
      direction = -direction
    return reported - direction * backlash_deg / 2.0

  def _notifyCalibrationUI(self, camera: "TrackedCamera", update):
    """Publish a pose update so an open calibration page can redraw at once.

    Writing to the database alone leaves a calibration page showing the pose
    it loaded with. Publishing on the camera's pose topic lets the UI redraw
    immediately, and keeps this service independent of the autocalibration
    service - the browser subscribes to the broker directly. Best-effort: a
    failure here only costs the live redraw, so it must never interrupt
    tracking.
    """
    if not self.notify_ui:
      return
    if update.get('transform_type') != POINT_CORRESPONDENCE_TRANSFORM:
      return
    split = split_point_correspondence_transforms(update.get('transforms') or [])
    if split is None:
      return
    try:
      if self.notify_pubsub is None:
        self.notify_pubsub = PubSub(self.brokerauth, None, self.brokerrootcert, self.broker)
        self.notify_pubsub.connect()
        self.notify_pubsub.loopStart()
      points_2d, points_3d = split
      self.notify_pubsub.publish(
          PubSub.formatTopic(PubSub.DATA_AUTOCALIB_CAM_POSE,
                             camera_id=camera.scene_camera_uid),
          json.dumps({'status': 'success',
                      'camera_id': camera.scene_camera_uid,
                      'calibration_points_2d': points_2d,
                      'calibration_points_3d': points_3d}))
    except Exception as err:
      log.warning(f"Could not publish pose update for {camera.label}: {err}")
      self.notify_pubsub = None
    return

  def _rebaselineIfRecalibrated(self, camera: "TrackedCamera", pan, tilt):
    """Adopt an externally applied calibration as the new home reference.

    The camera's pose can be re-calibrated at any time from the Scenescape UI
    while this service is running. Without noticing that, the service would
    keep rotating the pose it cached at startup and write back that stale
    snapshot - including its stale set of calibration points, silently
    replacing the ones the new calibration produced.

    A stored pose that differs from what this service last wrote can only
    have come from somewhere else, so it is taken as the new home, paired
    with the pan/tilt the camera is at right now.
    """
    now = time.monotonic()
    if now - camera.last_rebaseline_check < self.rebaseline_check_s:
      return
    camera.last_rebaseline_check = now

    try:
      info = self._fetchCameraInfo(camera.scene_camera_uid)
    except Exception as err:
      log.error(f"Could not check {camera.label} for external re-calibration: {err}")
      return

    reference = camera.last_written_rotation or camera.home_rotation
    if rotation_delta_magnitude(info['rotation'], reference) < self.rebaseline_tolerance_deg:
      return
    # Scenescape re-derives rotation from written correspondences via solvePnP,
    # and that value drifts a little from the one used to generate them, so the
    # rotation alone would flag this service's own updates as external. The
    # stored correspondences are compared instead: they are reproduced exactly.
    if camera.last_written_transforms is not None and info['transforms'] is not None:
      if len(camera.last_written_transforms) == len(info['transforms']) and all(
          abs(a - b) < 1e-6
          for a, b in zip(camera.last_written_transforms, info['transforms'])):
        return

    camera.home_rotation = info['rotation']
    camera.home_translation = info['translation']
    camera.home_points_3d = info['points_3d']
    camera.intrinsics = info['intrinsics']
    camera.distortion = info['distortion']
    camera.home_pan = pan
    camera.home_tilt = tilt
    camera.last_applied_rotation = list(info['rotation'])
    camera.last_observed_rotation = list(info['rotation'])
    camera.last_pose_change_time = time.monotonic()
    camera.last_written_rotation = None
    camera.last_written_transforms = None
    # The tracker already knows which side of the slack each axis is on, so
    # keep that rather than re-centring (which would add half the slack of error).
    self._rotationFor(camera, pan, tilt)
    camera.home_pan_physical_deg = camera.pan_physical_deg
    camera.home_tilt_physical_deg = camera.tilt_physical_deg
    points = len(info['points_3d']) if info['points_3d'] else 0
    log.info(
        f"{camera.label} was re-calibrated externally; adopting it as the new home "
        f"(rotation={info['rotation']}, {points} calibration points, "
        f"pan={pan:.6f} tilt={tilt:.6f})")
    return

  def setup(self):
    """Load the camera map, resolve ONVIF profiles, fetch each camera's
    calibrated pose from Scenescape, and record the pan/tilt home
    reference. Cameras that fail to initialize are logged and skipped;
    they don't block the others."""
    entries = self._loadConfig()
    if not entries:
      log.warning(
          "No cameras configured; run with --discover-only to list available "
          "ONVIF PTZ cameras and populate the config file")
      return

    for entry in entries:
      host = entry['onvif_host']
      port = int(entry.get('onvif_port', 80))
      scene_uid = entry['scene_camera_uid']
      try:
        profile_token = self._resolveProfileToken(host, port, entry.get('profile_token'))
        controller = PTZController(
            host, port, profile_token, self.onvif_username, self.onvif_password)

        self._applyConfiguredIntrinsics(scene_uid, entry)

        info = self._fetchCameraInfo(scene_uid)
        home_rotation = info['rotation']
        home_translation = info['translation']
        camera_name = info['name']

        home_pan = entry.get('home_pan')
        home_tilt = entry.get('home_tilt')
        if home_pan is None or home_tilt is None:
          status = controller.get_status()
          home_pan = status.position.pan if home_pan is None else home_pan
          home_tilt = status.position.tilt if home_tilt is None else home_tilt
          log.info(
              f"No home_pan/home_tilt configured for {host}:{port}, using current "
              f"position as home: pan={home_pan} tilt={home_tilt}")

        pan_scale, tilt_scale, reliable = self._resolveAxisScales(controller, host, port, entry)
        pose_update_mode = entry.get('pose_update_mode', self.default_pose_update_mode)
        if pose_update_mode not in POSE_UPDATE_MODES:
          raise ValueError(
              f"Unknown pose_update_mode {pose_update_mode!r}; expected one of {POSE_UPDATE_MODES}")

        camera = TrackedCamera(
            scene_camera_uid=scene_uid,
            camera_name=camera_name,
            onvif_host=host,
            onvif_port=port,
            controller=controller,
            home_rotation=home_rotation,
            home_translation=home_translation,
            home_pan=float(home_pan),
            home_tilt=float(home_tilt),
            pan_scale=pan_scale,
            tilt_scale=tilt_scale,
            pan_curve=entry.get('pan_curve'),
            pan_axis=entry.get('pan_axis'),
            tilt_curve=entry.get('tilt_curve'),
            pan_backlash_deg=float(entry.get('pan_backlash_deg') or 0.0),
            tilt_backlash_deg=float(entry.get('tilt_backlash_deg') or 0.0),
            pose_settle_s=float(entry.get('pose_settle_s', self.pose_settle_s)),
            pan_home_approach=entry.get('pan_home_approach'),
            tilt_home_approach=entry.get('tilt_home_approach'),
            invert_pan=bool(entry.get('invert_pan', self.default_invert_pan)),
            invert_tilt=bool(entry.get('invert_tilt', self.default_invert_tilt)),
            pose_update_mode=pose_update_mode,
            home_points_3d=info['points_3d'],
            intrinsics=info['intrinsics'],
            distortion=info['distortion'],
            last_raw_pan=float(home_pan),
            last_raw_tilt=float(home_tilt),
        )
        self.cameras.append(camera)
        self._resetBacklashState(camera)
        points_note = (f", reprojecting {len(info['points_3d'])} calibration points"
                       if info['points_3d'] and info['intrinsics'] else "")
        log.info(
            f"Tracking PTZ camera {camera.label} in '{pose_update_mode}' mode "
            f"(home rotation={home_rotation}{points_note})")
      except Exception as err:
        log.error(f"Skipping camera {host}:{port} ({scene_uid}): {err}")

    if any(camera.needs_recalibration for camera in self.cameras) and self.recalibrator is None:
      self.recalibrator = AutoRecalibrator(
          self.autocalibration_url, self.autocalibration_rootcert,
          self.broker, self.brokerauth, self.brokerrootcert)
    return

  def pollCamera(self, camera: TrackedCamera):
    if camera.needs_recalibration:
      self._pollRecalibratingCamera(camera)
      return

    status = camera.controller.get_status()
    pan = status.position.pan
    tilt = status.position.tilt

    self._rebaselineIfRecalibrated(camera, pan, tilt)

    new_rotation, delta_pan, delta_tilt = self._rotationFor(camera, pan, tilt)

    now = time.monotonic()
    if rotation_delta_magnitude(new_rotation, camera.last_observed_rotation) >= self.min_delta_deg:
      camera.last_observed_rotation = new_rotation
      camera.last_pose_change_time = now
    if camera.pose_settle_s > 0 and now - camera.last_pose_change_time < camera.pose_settle_s:
      return

    if rotation_delta_magnitude(new_rotation, camera.last_applied_rotation) < self.min_delta_deg:
      return

    update = self._buildPoseUpdate(camera, new_rotation, camera.home_translation)
    if update is None:
      return
    result = self.rest.updateCamera(camera.scene_camera_uid, update)
    if result.errors:
      log.error(f"Failed to update pose for {camera.label}: {result.errors}")
      return

    log.info(
        f"Camera {camera.label} pose updated: pan={pan:.3f} (Δ{delta_pan:+.2f}°) "
        f"tilt={tilt:.3f} (Δ{delta_tilt:+.2f}°) rotation={new_rotation}")
    camera.last_applied_rotation = new_rotation
    camera.last_written_rotation = list(new_rotation)
    camera.last_written_transforms = update.get('transforms')
    self._notifyCalibrationUI(camera, update)
    return

  def _pollRecalibratingCamera(self, camera: TrackedCamera):
    """Poll loop body for a camera whose PTZ position space can't be
    reliably converted to degrees (see ``_isReliableDegreeSpace``). Instead
    of a linear approximation, this watches for the raw pan/tilt reading to
    move and settle, then triggers a full AprilTag-based recalibration in a
    background thread so the poll loop isn't blocked on it."""
    status = camera.controller.get_status()
    pan = status.position.pan
    tilt = status.position.tilt

    moved = (abs(pan - camera.last_raw_pan) > self.min_raw_delta or
             abs(tilt - camera.last_raw_tilt) > self.min_raw_delta)
    now = time.monotonic()
    if moved:
      camera.last_raw_pan = pan
      camera.last_raw_tilt = tilt
      camera.last_raw_change_time = now
      camera.pending_recal = True
      return

    if not camera.pending_recal or camera.recal_in_progress:
      return
    if (now - camera.last_raw_change_time) < self.recal_settle_s:
      return

    camera.pending_recal = False
    camera.recal_in_progress = True

    def _doRecalibrate():
      try:
        result = self.recalibrator.recalibrate(camera.scene_camera_uid)
        if result is None:
          log.warning(
              f"Auto-recalibration failed for {camera.label}; will retry on next pose change")
          return
        reject_reason = implausible_recalibration_reason(
            result['translation'], camera.home_translation,
            min_height=self.min_camera_height, max_drift=self.max_translation_drift)
        if reject_reason:
          log.error(
              f"Rejecting auto-recalibration result for {camera.label}: {reject_reason} "
              f"(rotation={result['rotation']} translation={result['translation']}); "
              "keeping previous pose")
          return
        update = self._buildPoseUpdate(camera, result['rotation'], result['translation'])
        if update is None:
          return
        rest_result = self.rest.updateCamera(camera.scene_camera_uid, update)
        if rest_result.errors:
          log.error(f"Failed to save recalibrated pose for {camera.label}: {rest_result.errors}")
          return
        camera.home_rotation = result['rotation']
        camera.home_translation = result['translation']
        camera.home_pan = pan
        camera.home_tilt = tilt
        camera.last_applied_rotation = result['rotation']
        log.info(
            f"Auto-recalibrated {camera.label}: rotation={result['rotation']} "
            f"translation={result['translation']}")
      finally:
        camera.recal_in_progress = False
      return

    threading.Thread(target=_doRecalibrate, daemon=True).start()
    return

  def loop_forever(self):
    if not self.cameras:
      log.error("No cameras being tracked, nothing to do")
      return

    log.info(
        f"Polling {len(self.cameras)} PTZ camera(s) every {self.poll_period:.2f}s")
    while self._running:
      cycle_start = time.monotonic()
      for camera in self.cameras:
        try:
          self.pollCamera(camera)
        except Exception as err:
          log.error(f"Error polling {camera.label}: {err}")
      elapsed = time.monotonic() - cycle_start
      remaining = self.poll_period - elapsed
      if remaining > 0 and self._running:
        time.sleep(remaining)
    log.info("PTZ Pose Service stopped")
    return
