#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Pure-math helpers that turn an ONVIF PTZ pan/tilt reading into an updated
Scenescape camera rotation.

Deliberately dependency-free (no numpy/scipy) since this service only needs
to add a pan/tilt offset (in degrees) on top of the camera's calibrated
("home") rotation.

Scope / limitations (first iteration):
  - Zoom is ignored.
  - Roll is never touched (assumed constant, taken from the home rotation).
  - Pan is mapped to yaw (rotation about the world Z axis) and tilt is mapped
    to pitch (rotation about the camera's X axis), matching the
    ``rotation`` = [roll, pitch, yaw] convention used by
    ``scene_common.transform.CameraPose`` (Euler 'XYZ', degrees).
  - The pan/tilt -> degrees mapping is a simple linear scale + optional sign
    inversion (``pan_scale``/``tilt_scale``/``invert_pan``/``invert_tilt``).
    ONVIF cameras report PTZ position in a vendor/profile-specific space;
    some report signed degrees directly (scale=1.0), others report a
    normalized generic range (e.g. [-1, 1] mapped to the physical sweep) that
    requires a scale factor to convert to degrees. ``scale_from_fov()``
    derives that scale automatically from the camera's own advertised
    position-space range and its real physical field of view, so cameras
    with different sweep ranges (e.g. 360° vs 90° pan) don't need a manually
    guessed scale; an explicit ``pan_scale``/``tilt_scale`` is still honored
    as an override.
  - Composition is a simple additive offset on the Euler angles, not a full
    quaternion/matrix composition. This is accurate for small-to-moderate
    deviations from the home position and keeps the service simple; it can
    be revisited if larger sweeps or roll interaction become relevant.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple


def normalize_degrees(angle: float) -> float:
  """Wrap an angle in degrees to the range ``(-180, 180]``."""
  angle = angle % 360.0
  if angle > 180.0:
    angle -= 360.0
  elif angle <= -180.0:
    angle += 360.0
  return angle


def rotation_from_ptz_delta(
    home_rotation: Sequence[float],
    home_pan: float,
    home_tilt: float,
    pan: float,
    tilt: float,
    pan_scale: float = 1.0,
    tilt_scale: float = 1.0,
    invert_pan: bool = False,
    invert_tilt: bool = False,
) -> Tuple[List[float], float, float]:
  """Compute an updated camera rotation from a pan/tilt reading.

  @param      home_rotation   [roll, pitch, yaw] in degrees, the camera's
                              calibrated rotation stored in Scenescape
  @param      home_pan        ONVIF pan value at the calibrated position
  @param      home_tilt       ONVIF tilt value at the calibrated position
  @param      pan             current ONVIF pan value
  @param      tilt            current ONVIF tilt value
  @param      pan_scale       degrees of yaw per unit of ONVIF pan delta
  @param      tilt_scale      degrees of pitch per unit of ONVIF tilt delta
  @param      invert_pan      flip the sign of the pan contribution
  @param      invert_tilt     flip the sign of the tilt contribution
  @return     (new_rotation, delta_pan_degrees, delta_tilt_degrees)
  """
  roll, pitch, yaw = home_rotation

  delta_pan_degrees = (pan - home_pan) * pan_scale * (-1.0 if invert_pan else 1.0)
  delta_tilt_degrees = (tilt - home_tilt) * tilt_scale * (-1.0 if invert_tilt else 1.0)

  new_yaw = normalize_degrees(yaw + delta_pan_degrees)
  new_pitch = normalize_degrees(pitch + delta_tilt_degrees)

  return [roll, new_pitch, new_yaw], delta_pan_degrees, delta_tilt_degrees


def rotation_delta_magnitude(rotation_a: Sequence[float], rotation_b: Sequence[float]) -> float:
  """Largest per-axis absolute difference (degrees) between two rotations."""
  return max(
      abs(normalize_degrees(a - b))
      for a, b in zip(rotation_a, rotation_b)
  )


def scale_from_fov(space_min: float, space_max: float, fov_degrees: float) -> float:
  """Degrees-per-unit scale factor for one PTZ axis.

  ONVIF cameras report GetStatus position in the axis's own unit range
  (e.g. a normalized ``[-1, 1]`` generic space, or sometimes real degrees
  already) rather than physical degrees. ``space_min``/``space_max`` are
  that unit range as advertised by the camera itself (its
  ``AbsolutePanTiltPositionSpace`` ``XRange``/``YRange``, queried via ONVIF
  ``GetNodes``); ``fov_degrees`` is the axis's real physical field of view
  (from the camera's datasheet, e.g. 360 for a full pan turret or 90 for a
  limited-sweep camera). Dividing the two normalizes a raw ONVIF delta into
  degrees regardless of which convention this particular camera uses.

  @param      space_min       minimum value of the camera's reported position range
  @param      space_max       maximum value of the camera's reported position range
  @param      fov_degrees     physical field of view of this axis, in degrees
  @return                     degrees per unit of raw ONVIF position delta
  """
  span = space_max - space_min
  if span <= 0:
    raise ValueError(f"Invalid PTZ position space range: [{space_min}, {space_max}]")
  return fov_degrees / span

