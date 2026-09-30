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
    pan_axis: Optional[Sequence[float]] = None,
) -> List[float]:
  """Rotate a camera's home pose by pan/tilt deltas already in degrees.

  A pan/tilt head rotates the camera about two fixed mechanical axes: pan
  swings the whole head about the world vertical (Z) axis, and tilt pivots
  the camera about its own horizontal (local X) axis. That composes as
  ``R_new = Rz(dpan) @ R_home @ Rx(dtilt)``.

  ``pan_axis`` replaces world Z with the head's actual pan axis in world
  coordinates, for a mount that isn't level (or a home pose with a small tilt
  error): on the development camera it leaned ~7 deg, which no pan scale or
  curve can compensate since the error grows with the pan angle.

  This must be done on rotation matrices rather than by adding the deltas to
  the stored ``[roll, pitch, yaw]`` triple: those are *intrinsic* Euler
  angles, so their third component is a rotation about an already-rotated
  local axis, not the world vertical. Measured against ground-truth poses, a
  pure pan move changes all three Euler components (e.g. roll -14 deg,
  pitch +34 deg, yaw +20 deg), so adding a delta to yaw alone produces a
  badly wrong pose.
  """
  pan = (rotation_matrix_axis(pan_axis, delta_pan_degrees) if pan_axis
         else rotation_matrix_z(delta_pan_degrees))
  rotated = matrix_multiply(
      pan,
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
  """Angle (degrees) of the rotation taking one Euler-XYZ pose to the other.

  Compared as matrices, not per Euler component: the same orientation has
  more than one Euler triple, and Scenescape may store a different one than
  was written.
  """
  a = euler_xyz_degrees_to_matrix(rotation_a)
  b = euler_xyz_degrees_to_matrix(rotation_b)
  trace = sum(a[k][i] * b[k][i] for i in range(3) for k in range(3))
  return math.degrees(math.acos(max(-1.0, min(1.0, (trace - 1.0) / 2.0))))


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


def rotation_matrix_axis(axis: Sequence[float], degrees: float) -> List[List[float]]:
  """Rotation of ``degrees`` about an arbitrary axis (Rodrigues' formula)."""
  norm = math.sqrt(sum(v * v for v in axis))
  x, y, z = (v / norm for v in axis)
  c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
  t = 1.0 - c
  return [
      [t * x * x + c, t * x * y - s * z, t * x * z + s * y],
      [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
      [t * x * z - s * y, t * y * z + s * x, t * z * z + c],
  ]


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
  pixels = []
  for point in _project_points(points_3d, rotation, translation, intrinsics, distortion):
    if point is None:
      return None
    pixels.append(point[:2])
  return pixels


def visible_point_correspondences(
    points_3d: Sequence[Sequence[float]],
    rotation: Sequence[float],
    translation: Sequence[float],
    intrinsics: dict,
    distortion: Optional[dict] = None,
) -> Tuple[List[List[float]], List[List[float]]]:
  """Project world points, keeping only those the camera can actually see.

  A PTZ move takes some calibration points out of frame. Projecting those
  anyway is actively harmful with a barrel-distortion model: ``1 + k1*r^2``
  folds back beyond a certain radius (r ~ 0.95 for k1 = -0.37), so a point
  far outside the frame lands *inside* it at a wrong pixel - and beyond
  ``r^2 = -1/k1`` mirrors to the opposite side. solvePnP can't undo that,
  so every such point corrupts the pose Scenescape re-derives. Points behind
  the camera, past the fold, or outside the image (assumed ``2*cx`` x
  ``2*cy``) are therefore dropped.

  @return  (points_2d, points_3d) for the visible points only
  """
  width, height = 2.0 * intrinsics['cx'], 2.0 * intrinsics['cy']
  limit_r2 = max_monotonic_radius_squared(distortion)
  points_2d, kept_3d = [], []
  for world, point in zip(points_3d, _project_points(
      points_3d, rotation, translation, intrinsics, distortion)):
    if point is None:
      continue
    u, v, r2 = point
    if r2 >= limit_r2 or not (0.0 <= u < width and 0.0 <= v < height):
      continue
    points_2d.append([u, v])
    kept_3d.append(list(world))
  return points_2d, kept_3d


def max_monotonic_radius_squared(distortion: Optional[dict] = None) -> float:
  """Squared normalized radius at which the radial distortion model folds back.

  Distorted radius is ``r*(1 + k1*r^2 + k2*r^4 + k3*r^6)``; past the first
  point where its derivative reaches zero, distinct rays map to the same
  pixel and the model no longer describes the lens.
  """
  distortion = distortion or {}
  k1 = distortion.get('k1') or 0.0
  k2 = distortion.get('k2') or 0.0
  k3 = distortion.get('k3') or 0.0
  r2 = 0.0
  while r2 < 100.0:
    if 1.0 + 3.0 * k1 * r2 + 5.0 * k2 * r2 * r2 + 7.0 * k3 * r2 ** 3 <= 0.0:
      return r2
    r2 += 1e-3
  return math.inf


def _project_points(points_3d, rotation, translation, intrinsics, distortion):
  """Yield ``(u, v, r2)`` per world point, or None for one at/behind the camera."""
  rot_mat = euler_xyz_degrees_to_matrix(rotation)
  fx, fy = intrinsics['fx'], intrinsics['fy']
  cx, cy = intrinsics['cx'], intrinsics['cy']
  distortion = distortion or {}
  k1 = distortion.get('k1') or 0.0
  k2 = distortion.get('k2') or 0.0
  p1 = distortion.get('p1') or 0.0
  p2 = distortion.get('p2') or 0.0
  k3 = distortion.get('k3') or 0.0

  for point in points_3d:
    offset = [point[i] - translation[i] for i in range(3)]
    # Camera-frame coordinates: transpose of the camera-to-world rotation.
    x = sum(rot_mat[k][0] * offset[k] for k in range(3))
    y = sum(rot_mat[k][1] * offset[k] for k in range(3))
    z = sum(rot_mat[k][2] * offset[k] for k in range(3))
    if z <= 1e-6:
      yield None
      continue
    xn, yn = x / z, y / z
    r2 = xn * xn + yn * yn
    radial = 1.0 + k1 * r2 + k2 * r2 * r2 + k3 * r2 * r2 * r2
    xd = xn * radial + 2.0 * p1 * xn * yn + p2 * (r2 + 2.0 * xn * xn)
    yd = yn * radial + p1 * (r2 + 2.0 * yn * yn) + 2.0 * p2 * xn * yn
    yield [fx * xd + cx, fy * yd + cy, r2]


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

