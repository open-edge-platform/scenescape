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

import math
from typing import List, Optional, Sequence, Tuple


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


def quaternion_to_euler_xyz_degrees(x: float, y: float, z: float, w: float) -> List[float]:
  """Convert a ``[x, y, z, w]`` quaternion (scalar-last, the convention used
  by ``scipy.spatial.transform.Rotation.as_quat()``) into the ``[roll, pitch,
  yaw]`` intrinsic Euler-XYZ degrees representation used by Scenescape's
  camera ``rotation`` field (matching three.js's ``Euler`` with the default
  ``'XYZ'`` order, as used client-side by the manual calibration UI).

  Implemented from scratch (quaternion -> rotation matrix -> Euler-XYZ) to
  keep this service numpy/scipy-free; the matrix-to-Euler step mirrors
  three.js's ``Euler.setFromRotationMatrix()`` for order ``'XYZ'``.
  """
  # Quaternion -> 3x3 rotation matrix (row-major, transforms column vectors).
  m00 = 1 - 2 * (y * y + z * z)
  m01 = 2 * (x * y - w * z)
  m02 = 2 * (x * z + w * y)
  m11 = 1 - 2 * (x * x + z * z)
  m12 = 2 * (y * z - w * x)
  m21 = 2 * (y * z + w * x)
  m22 = 1 - 2 * (x * x + y * y)

  m02_clamped = max(-1.0, min(1.0, m02))
  pitch = math.asin(m02_clamped)
  if abs(m02_clamped) < 0.9999999:
    roll = math.atan2(-m12, m22)
    yaw = math.atan2(-m01, m00)
  else:
    roll = math.atan2(m21, m11)
    yaw = 0.0

  return [math.degrees(roll), math.degrees(pitch), math.degrees(yaw)]


def implausible_recalibration_reason(
    translation: Sequence[float],
    reference_translation: Optional[Sequence[float]] = None,
    min_height: float = 0.1,
    max_drift: float = 1.0,
) -> Optional[str]:
  """Sanity-checks a freshly auto-recalibrated camera translation before it's
  trusted and pushed to Scenescape.

  A PTZ camera's mounting position is physically fixed - only its pan/tilt
  orientation changes - so a legitimate recalibration's translation should
  barely move from the last known-good one. AprilTag pose estimation can
  occasionally return a degenerate/mirrored solution (a well-known PnP
  ambiguity for near-planar tag layouts, more likely at certain oblique
  pan/tilt angles), which tends to flip the camera to an implausible spot
  such as below the floor. Two independent checks catch this:

  - ``min_height``: the camera's world Z (translation[2], "up" in
    Scenescape's Z-up convention) must be above the floor plane.
  - ``max_drift``: the new translation must be within ``max_drift`` (in
    scene units, normally meters) of ``reference_translation`` (the
    previous known-good translation), if given.

  @return   None if the pose looks plausible, else a human-readable reason
            it was rejected.
  """
  z = translation[2]
  if z < min_height:
    return f"translation z={z:.3f} is below the minimum camera height {min_height} (below/at floor)"
  if reference_translation is not None:
    drift = math.sqrt(sum((a - b) ** 2 for a, b in zip(translation, reference_translation)))
    if drift > max_drift:
      return (f"translation moved {drift:.3f} from the last known-good position "
              f"(max allowed {max_drift}); a fixed PTZ mount shouldn't move")
  return None


def euler_xyz_degrees_to_matrix(rotation: Sequence[float]) -> List[List[float]]:
  """Intrinsic Euler-XYZ (degrees) -> 3x3 camera-to-world rotation matrix.

  Matches ``scipy.spatial.transform.Rotation.from_euler('XYZ', ..., degrees=True)``
  (i.e. ``R = Rx @ Ry @ Rz``), the convention Scenescape stores camera
  ``rotation`` in, expanded by hand to keep this module dependency-free.
  """
  rx, ry, rz = (math.radians(angle) for angle in rotation)
  cx, sx = math.cos(rx), math.sin(rx)
  cy, sy = math.cos(ry), math.sin(ry)
  cz, sz = math.cos(rz), math.sin(rz)
  return [
      [cy * cz, -cy * sz, sy],
      [cx * sz + sx * sy * cz, cx * cz - sx * sy * sz, -sx * cy],
      [sx * sz - cx * sy * cz, sx * cz + cx * sy * sz, cx * cy],
  ]


def project_world_points_to_pixels(
    points_3d: Sequence[Sequence[float]],
    rotation: Sequence[float],
    translation: Sequence[float],
    intrinsics: dict,
) -> Optional[List[List[float]]]:
  """Project world points into camera pixels for a given camera pose.

  Used to keep a camera's stored 3D-2D calibration correspondences valid
  after a PTZ move: the world points are physically fixed, so only their
  pixel positions change as the camera rotates. Verified to match
  ``cv2.projectPoints`` exactly for an undistorted pinhole model.

  Distortion is not applied; cameras calibrated through the AprilTag flow
  carry no distortion coefficients (the pipeline already works on an
  undistorted model).

  @param  intrinsics  dict with 'fx', 'fy', 'cx', 'cy'
  @return  list of [u, v] pixels, or None if any point falls at/behind the
           camera plane (pose can't be represented by these correspondences)
  """
  rot_mat = euler_xyz_degrees_to_matrix(rotation)
  fx, fy = intrinsics['fx'], intrinsics['fy']
  cx, cy = intrinsics['cx'], intrinsics['cy']

  pixels = []
  for point in points_3d:
    offset = [point[i] - translation[i] for i in range(3)]
    # Camera-frame coordinates: transpose of the camera-to-world rotation.
    x = sum(rot_mat[k][0] * offset[k] for k in range(3))
    y = sum(rot_mat[k][1] * offset[k] for k in range(3))
    z = sum(rot_mat[k][2] * offset[k] for k in range(3))
    if z <= 1e-6:
      return None
    pixels.append([fx * x / z + cx, fy * y / z + cy])
  return pixels


def split_point_correspondence_transforms(
    transforms: Sequence[float],
) -> Optional[Tuple[List[List[float]], List[List[float]]]]:
  """Split a stored '3d-2d point correspondence' transforms array.

  Layout is ``[u1, v1, ..., un, vn, x1, y1, z1, ..., xn, yn, zn]`` - all 2D
  camera points first, then the matching 3D map points (see
  ``scene_common.transform.CameraPose.arrayToDictionary``).

  @return  (points_2d, points_3d), or None if the array isn't that layout
  """
  count = len(transforms)
  if count == 0 or count % 5 != 0:
    return None
  n = count // 5
  points_2d = [list(transforms[i * 2:i * 2 + 2]) for i in range(n)]
  points_3d = [list(transforms[n * 2 + i * 3: n * 2 + i * 3 + 3]) for i in range(n)]
  return points_2d, points_3d


def join_point_correspondence_transforms(
    points_2d: Sequence[Sequence[float]],
    points_3d: Sequence[Sequence[float]],
) -> List[float]:
  """Flatten 2D/3D correspondences back into a stored transforms array."""
  flat = [float(v) for point in points_2d for v in point]
  flat.extend(float(v) for point in points_3d for v in point)
  return flat

