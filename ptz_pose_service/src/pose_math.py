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


def axis_angle_degrees(
    position: float,
    scale: float,
    curve: Optional[Sequence[float]] = None,
    invert: bool = False,
) -> float:
  """Absolute rotation angle an axis is at for a given ONVIF position.

  A single degrees-per-unit ``scale`` assumes the axis turns uniformly across
  its travel. Real heads need not: on the camera used for development the
  tilt axis measured 53.8 deg/unit near the middle of its range and
  60.6 deg/unit near the top, so a constant scale fitted mid-range
  undershoots at one end and overshoots at the other. Passing ``curve``
  instead models the position-to-angle relationship as a polynomial
  (coefficients in increasing power, so ``[0, 42.05, 9.41]`` means
  ``42.05*t + 9.41*t^2``). Only differences between two positions are ever
  used, so any constant term cancels.
  """
  if curve:
    angle = sum(c * position ** i for i, c in enumerate(curve))
  else:
    angle = position * scale
  return -angle if invert else angle


def apply_backlash(
    previous_angle: Optional[float],
    reported_angle: float,
    backlash_degrees: float,
) -> float:
  """Where an axis physically is, given where it reports being.

  Gear slack puts the position encoder on the motor side of the gearbox, so
  when travel reverses the encoder moves while the camera does not, until the
  slack is taken up. The camera therefore trails the reported position by up
  to half the slack either side, which is the classic backlash deadband:
  the physical angle only moves when the reported angle drags it past the
  edge of that band.

  Measured on the development camera by arriving at the same reported tilt
  from each direction: 2.83 deg of slack on tilt (consistent to 0.7 deg
  across its travel) and none measurable on pan.

  @param  previous_angle    last known physical angle, or None to start
                            centred on the reported one
  @param  reported_angle    angle implied by the camera's reported position
  @param  backlash_degrees  total slack; 0 disables the model
  @return                   physical angle in degrees
  """
  if backlash_degrees <= 0.0 or previous_angle is None:
    return reported_angle
  half = backlash_degrees / 2.0
  return min(max(previous_angle, reported_angle - half), reported_angle + half)


def compose_ptz_rotation(
    home_rotation: Sequence[float],
    delta_pan_degrees: float,
    delta_tilt_degrees: float,
) -> List[float]:
  """Rotate a camera's home pose by pan/tilt deltas already in degrees.

  A pan/tilt head rotates the camera about two fixed mechanical axes: pan
  swings the whole head about the world vertical (Z) axis, and tilt pivots
  the camera about its own horizontal (local X) axis. That composes as
  ``R_new = Rz(dpan) @ R_home @ Rx(dtilt)``. Both were confirmed on a real
  head: the recovered axes were within 2 degrees of world Z and camera X.

  This must be done on rotation matrices rather than by adding the deltas to
  the stored ``[roll, pitch, yaw]`` triple: those are *intrinsic* Euler
  angles, so their third component is a rotation about an already-rotated
  local axis, not the world vertical. Measured against ground-truth poses, a
  pure pan move changes all three Euler components (e.g. roll -14 deg,
  pitch +34 deg, yaw +20 deg), so adding a delta to yaw alone produces a
  badly wrong pose.
  """
  rotated = matrix_multiply(
      rotation_matrix_z(delta_pan_degrees),
      matrix_multiply(euler_xyz_degrees_to_matrix(home_rotation),
                      rotation_matrix_x(delta_tilt_degrees)))
  return matrix_to_euler_xyz_degrees(rotated)


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
    pan_curve: Optional[Sequence[float]] = None,
    tilt_curve: Optional[Sequence[float]] = None,
) -> Tuple[List[float], float, float]:
  """Compute an updated camera rotation from a pan/tilt reading.

  Convenience wrapper over ``axis_angle_degrees`` and
  ``compose_ptz_rotation`` for callers that don't model backlash; see those
  for the details.

  @param      home_rotation   [roll, pitch, yaw] in degrees, the camera's
                              calibrated rotation stored in Scenescape
  @param      home_pan        ONVIF pan value at the calibrated position
  @param      home_tilt       ONVIF tilt value at the calibrated position
  @param      pan             current ONVIF pan value
  @param      tilt            current ONVIF tilt value
  @param      pan_scale       degrees rotated about world Z per unit of ONVIF pan
  @param      tilt_scale      degrees rotated about camera X per unit of ONVIF tilt
  @param      invert_pan      flip the sign of the pan contribution
  @param      invert_tilt     flip the sign of the tilt contribution
  @param      pan_curve       optional polynomial replacing ``pan_scale``
  @param      tilt_curve      optional polynomial replacing ``tilt_scale``
  @return     (new_rotation, delta_pan_degrees, delta_tilt_degrees)
  """
  delta_pan_degrees = (axis_angle_degrees(pan, pan_scale, pan_curve, invert_pan)
                       - axis_angle_degrees(home_pan, pan_scale, pan_curve, invert_pan))
  delta_tilt_degrees = (axis_angle_degrees(tilt, tilt_scale, tilt_curve, invert_tilt)
                        - axis_angle_degrees(home_tilt, tilt_scale, tilt_curve, invert_tilt))
  return (compose_ptz_rotation(home_rotation, delta_pan_degrees, delta_tilt_degrees),
          delta_pan_degrees, delta_tilt_degrees)


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


def matrix_to_euler_xyz_degrees(matrix: Sequence[Sequence[float]]) -> List[float]:
  """3x3 rotation matrix -> intrinsic Euler-XYZ degrees.

  Inverse of ``euler_xyz_degrees_to_matrix``; matches
  ``scipy.spatial.transform.Rotation.as_euler('XYZ', degrees=True)``.
  """
  sy = max(-1.0, min(1.0, matrix[0][2]))
  pitch = math.asin(sy)
  if abs(sy) < 0.9999999:
    roll = math.atan2(-matrix[1][2], matrix[2][2])
    yaw = math.atan2(-matrix[0][1], matrix[0][0])
  else:
    # Gimbal lock: roll and yaw are degenerate, so fold everything into roll.
    roll = math.atan2(matrix[2][1], matrix[1][1])
    yaw = 0.0
  return [math.degrees(roll), math.degrees(pitch), math.degrees(yaw)]


def matrix_multiply(a: Sequence[Sequence[float]],
                    b: Sequence[Sequence[float]]) -> List[List[float]]:
  """Multiply two 3x3 matrices."""
  return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def rotation_matrix_x(degrees: float) -> List[List[float]]:
  """Rotation of ``degrees`` about the X axis."""
  c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
  return [[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]]


def rotation_matrix_z(degrees: float) -> List[List[float]]:
  """Rotation of ``degrees`` about the Z axis."""
  c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
  return [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]


def project_world_points_to_pixels(
    points_3d: Sequence[Sequence[float]],
    rotation: Sequence[float],
    translation: Sequence[float],
    intrinsics: dict,
    distortion: Optional[dict] = None,
) -> Optional[List[List[float]]]:
  """Project world points into camera pixels for a given camera pose.

  Used to keep a camera's stored 3D-2D calibration correspondences valid
  after a PTZ move: the world points are physically fixed, so only their
  pixel positions change as the camera rotates. Verified to match
  ``cv2.projectPoints`` exactly.

  The camera's distortion coefficients must be applied here whenever it has
  any, because Scenescape re-derives the pose from these pixels with
  ``cv2.solvePnP`` using that same model; projecting as a plain pinhole
  while it un-distorts would silently bias the recovered pose.

  @param  intrinsics  dict with 'fx', 'fy', 'cx', 'cy'
  @param  distortion  optional dict with 'k1', 'k2', 'p1', 'p2', 'k3'
  @return  list of [u, v] pixels, or None if any point falls at/behind the
           camera plane (pose can't be represented by these correspondences)
  """
  rot_mat = euler_xyz_degrees_to_matrix(rotation)
  fx, fy = intrinsics['fx'], intrinsics['fy']
  cx, cy = intrinsics['cx'], intrinsics['cy']
  distortion = distortion or {}
  k1 = distortion.get('k1') or 0.0
  k2 = distortion.get('k2') or 0.0
  p1 = distortion.get('p1') or 0.0
  p2 = distortion.get('p2') or 0.0
  k3 = distortion.get('k3') or 0.0

  pixels = []
  for point in points_3d:
    offset = [point[i] - translation[i] for i in range(3)]
    # Camera-frame coordinates: transpose of the camera-to-world rotation.
    x = sum(rot_mat[k][0] * offset[k] for k in range(3))
    y = sum(rot_mat[k][1] * offset[k] for k in range(3))
    z = sum(rot_mat[k][2] * offset[k] for k in range(3))
    if z <= 1e-6:
      return None
    xn, yn = x / z, y / z
    r2 = xn * xn + yn * yn
    radial = 1.0 + k1 * r2 + k2 * r2 * r2 + k3 * r2 * r2 * r2
    xd = xn * radial + 2.0 * p1 * xn * yn + p2 * (r2 + 2.0 * xn * xn)
    yd = yn * radial + p1 * (r2 + 2.0 * yn * yn) + 2.0 * p2 * xn * yn
    pixels.append([fx * xd + cx, fy * yd + cy])
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

