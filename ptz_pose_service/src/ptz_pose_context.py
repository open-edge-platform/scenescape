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
import time
from dataclasses import dataclass, field
from typing import List

from scene_common import log
from scene_common.rest_client import RESTClient

from dlstreamer.onvif import (
    discover_onvif_cameras,
    find_ptz_capable_profiles,
    PTZController,
)

from pose_math import rotation_from_ptz_delta, rotation_delta_magnitude, scale_from_fov


@dataclass
class TrackedCamera:
  """Runtime state for one ONVIF PTZ camera bound to a Scenescape camera."""

  scene_camera_uid: str
  camera_name: str
  onvif_host: str
  onvif_port: int
  controller: PTZController
  home_rotation: List[float]
  home_pan: float
  home_tilt: float
  pan_scale: float = 1.0
  tilt_scale: float = 1.0
  invert_pan: bool = False
  invert_tilt: bool = False
  last_applied_rotation: List[float] = field(default_factory=list)
  label: str = ""

  def __post_init__(self):
    if not self.last_applied_rotation:
      self.last_applied_rotation = list(self.home_rotation)
    if not self.label:
      self.label = f"{self.onvif_host}:{self.onvif_port} -> {self.scene_camera_uid}"
    return


class PTZPoseContext:
  """Discovers/loads configured PTZ cameras and keeps their Scenescape pose
  synchronized with the camera's live pan/tilt position."""

  def __init__(self, resturl, restauth, rootcert, config_path,
               onvif_username="", onvif_password="",
               poll_hz=5.0, min_delta_deg=0.2,
               default_pan_scale=1.0, default_tilt_scale=1.0,
               default_invert_pan=False, default_invert_tilt=False):
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

    @return     ((pan_min, pan_max), (tilt_min, tilt_max)) in the camera's
                own reported units (e.g. normalized [-1, 1] or degrees,
                depending on the camera), or None if the camera doesn't
                advertise an AbsolutePanTiltPositionSpace.
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
      return (float(x_range.Min), float(x_range.Max)), (float(y_range.Min), float(y_range.Max))
    return None

  def _resolveAxisScales(self, controller, host, port, entry):
    """Determine degrees-per-unit pan/tilt scale factors for a camera.

    Priority: an explicit ``pan_scale``/``tilt_scale`` in the config always
    wins. Otherwise, if ``pan_degrees``/``tilt_degrees`` (the camera's real
    physical field of view, e.g. from its datasheet) is configured, the
    scale is derived from the camera's own advertised
    AbsolutePanTiltPositionSpace range (queried via ONVIF GetNodes) so that
    cameras with different position-reporting units and different physical
    sweep ranges (e.g. 360° vs. 90° pan) are all normalized correctly.
    Falls back to the CLI --pan-scale/--tilt-scale defaults.
    """
    pan_scale = entry.get('pan_scale')
    tilt_scale = entry.get('tilt_scale')
    if pan_scale is not None and tilt_scale is not None:
      return float(pan_scale), float(tilt_scale)

    pan_fov = entry.get('pan_degrees')
    tilt_fov = entry.get('tilt_degrees')
    ranges = self._getAbsolutePanTiltRange(controller) if (pan_fov or tilt_fov) else None

    if ranges is None:
      if pan_fov is not None or tilt_fov is not None:
        log.warning(
            f"{host}:{port} did not report an absolute PTZ position range; "
            "ignoring configured pan_degrees/tilt_degrees, using pan_scale/tilt_scale defaults")
      return (
          float(pan_scale) if pan_scale is not None else self.default_pan_scale,
          float(tilt_scale) if tilt_scale is not None else self.default_tilt_scale,
      )

    (pan_min, pan_max), (tilt_min, tilt_max) = ranges
    log.info(
        f"{host}:{port} PTZ position space: pan range=[{pan_min}, {pan_max}] "
        f"tilt range=[{tilt_min}, {tilt_max}]")

    if pan_scale is None:
      pan_scale = (scale_from_fov(pan_min, pan_max, pan_fov)
                   if pan_fov is not None else self.default_pan_scale)
    if tilt_scale is None:
      tilt_scale = (scale_from_fov(tilt_min, tilt_max, tilt_fov)
                    if tilt_fov is not None else self.default_tilt_scale)
    return float(pan_scale), float(tilt_scale)

  def _fetchCameraInfo(self, scene_camera_uid):
    """Fetch a camera's calibrated rotation and name from Scenescape.

    The name is required because the REST API's partial-update validation
    rejects any update that isn't scene-only relink unless 'name' is
    included, so every pose update must resend it alongside 'rotation'.
    """
    result = self.rest.getCamera(scene_camera_uid)
    if result.errors:
      raise RuntimeError(f"Failed to fetch camera {scene_camera_uid}: {result.errors}")
    rotation = result.get('rotation')
    if not rotation or len(rotation) != 3:
      raise RuntimeError(
          f"Camera {scene_camera_uid} has no valid 'rotation' set; calibrate it first")
    name = result.get('name')
    if not name:
      raise RuntimeError(f"Camera {scene_camera_uid} has no 'name' set")
    return [float(v) for v in rotation], name

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

        home_rotation, camera_name = self._fetchCameraInfo(scene_uid)

        home_pan = entry.get('home_pan')
        home_tilt = entry.get('home_tilt')
        if home_pan is None or home_tilt is None:
          status = controller.get_status()
          home_pan = status.position.pan if home_pan is None else home_pan
          home_tilt = status.position.tilt if home_tilt is None else home_tilt
          log.info(
              f"No home_pan/home_tilt configured for {host}:{port}, using current "
              f"position as home: pan={home_pan} tilt={home_tilt}")

        pan_scale, tilt_scale = self._resolveAxisScales(controller, host, port, entry)

        camera = TrackedCamera(
            scene_camera_uid=scene_uid,
            camera_name=camera_name,
            onvif_host=host,
            onvif_port=port,
            controller=controller,
            home_rotation=home_rotation,
            home_pan=float(home_pan),
            home_tilt=float(home_tilt),
            pan_scale=pan_scale,
            tilt_scale=tilt_scale,
            invert_pan=bool(entry.get('invert_pan', self.default_invert_pan)),
            invert_tilt=bool(entry.get('invert_tilt', self.default_invert_tilt)),
        )
        self.cameras.append(camera)
        log.info(f"Tracking PTZ camera {camera.label} (home rotation={home_rotation})")
      except Exception as err:
        log.error(f"Skipping camera {host}:{port} ({scene_uid}): {err}")
    return

  def pollCamera(self, camera: TrackedCamera):
    status = camera.controller.get_status()
    pan = status.position.pan
    tilt = status.position.tilt

    new_rotation, delta_pan, delta_tilt = rotation_from_ptz_delta(
        camera.home_rotation, camera.home_pan, camera.home_tilt, pan, tilt,
        pan_scale=camera.pan_scale, tilt_scale=camera.tilt_scale,
        invert_pan=camera.invert_pan, invert_tilt=camera.invert_tilt)

    if rotation_delta_magnitude(new_rotation, camera.last_applied_rotation) < self.min_delta_deg:
      return

    result = self.rest.updateCamera(
        camera.scene_camera_uid, {'name': camera.camera_name, 'rotation': new_rotation})
    if result.errors:
      log.error(f"Failed to update pose for {camera.label}: {result.errors}")
      return

    log.info(
        f"Camera {camera.label} pose updated: pan={pan:.3f} (Δ{delta_pan:+.2f}°) "
        f"tilt={tilt:.3f} (Δ{delta_tilt:+.2f}°) rotation={new_rotation}")
    camera.last_applied_rotation = new_rotation
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
