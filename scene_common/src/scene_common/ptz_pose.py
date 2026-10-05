# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Pure PTZ pose math shared by the pose resolver and its tests."""

import math
from typing import List, Optional, Sequence, Tuple, Union


def axis_angle_degrees(
    position: float,
    scale: float,
    curve: Optional[Sequence[float]] = None,
    invert: bool = False,
) -> float:
  """Map an ONVIF axis position to degrees using a scale or polynomial."""
  if curve:
    angle = sum(coefficient * position ** power
                for power, coefficient in enumerate(curve))
  else:
    angle = position * scale
  return -angle if invert else angle


def apply_backlash(
    previous_angle: Optional[float],
    reported_angle: float,
    backlash_degrees: float,
) -> float:
  """Estimate physical angle by constraining reported motion to the deadband."""
  if backlash_degrees <= 0.0 or previous_angle is None:
    return reported_angle
  half_backlash = backlash_degrees / 2.0
  return min(max(previous_angle, reported_angle - half_backlash),
             reported_angle + half_backlash)


def backlash_degrees_at(
    backlash: Union[float, Sequence[Sequence[float]]],
    position: float,
) -> float:
  """Return constant or linearly interpolated backlash at an axis position."""
  if not isinstance(backlash, (list, tuple)):
    return max(0.0, float(backlash or 0.0))
  if not backlash:
    return 0.0

  knots = sorted((float(point), float(degrees)) for point, degrees in backlash)
  if any(right[0] <= left[0] for left, right in zip(knots, knots[1:])):
    raise ValueError("Backlash positions must be unique")
  if position <= knots[0][0]:
    return max(0.0, knots[0][1])
  for (left_position, left_degrees), (right_position, right_degrees) in zip(
      knots, knots[1:]):
    if position <= right_position:
      fraction = ((position - left_position) /
                  (right_position - left_position))
      return max(0.0, left_degrees + (right_degrees - left_degrees) * fraction)
  return max(0.0, knots[-1][1])


def compose_ptz_rotation_matrix(
    home_rotation: Sequence[float],
    delta_pan_degrees: float,
    delta_tilt_degrees: float,
    pan_axis: Optional[Sequence[float]] = None,
) -> List[List[float]]:
  """Compose world-axis pan, calibrated home rotation, and local-X tilt."""
  pan_matrix = (rotation_matrix_axis(pan_axis, delta_pan_degrees) if pan_axis
                else rotation_matrix_z(delta_pan_degrees))
  home_matrix = euler_xyz_degrees_to_matrix(home_rotation)
  tilt_matrix = rotation_matrix_x(delta_tilt_degrees)
  return matrix_multiply(pan_matrix, matrix_multiply(home_matrix, tilt_matrix))


def compose_ptz_rotation(
    home_rotation: Sequence[float],
    delta_pan_degrees: float,
    delta_tilt_degrees: float,
    pan_axis: Optional[Sequence[float]] = None,
) -> List[float]:
  """Return the composed camera rotation in Scenescape Euler-XYZ degrees."""
  matrix = compose_ptz_rotation_matrix(
      home_rotation, delta_pan_degrees, delta_tilt_degrees, pan_axis)
  return matrix_to_euler_xyz_degrees(matrix)


def compose_ptz_transform(
    home_rotation: Sequence[float],
    translation: Sequence[float],
    delta_pan_degrees: float,
    delta_tilt_degrees: float,
    pan_axis: Optional[Sequence[float]] = None,
) -> List[List[float]]:
  """Return a row-major scene-from-camera rigid transform in metres."""
  if len(translation) != 3:
    raise ValueError("Camera translation must contain three values")
  rotation = compose_ptz_rotation_matrix(
      home_rotation, delta_pan_degrees, delta_tilt_degrees, pan_axis)
  return [
      [*rotation[0], translation[0]],
      [*rotation[1], translation[1]],
      [*rotation[2], translation[2]],
      [0.0, 0.0, 0.0, 1.0],
  ]


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
    pan_axis: Optional[Sequence[float]] = None,
) -> Tuple[List[float], float, float]:
  """Resolve a PTZ reading relative to calibrated home coordinates."""
  delta_pan = (axis_angle_degrees(pan, pan_scale, pan_curve, invert_pan) -
               axis_angle_degrees(home_pan, pan_scale, pan_curve, invert_pan))
  delta_tilt = (axis_angle_degrees(tilt, tilt_scale, tilt_curve, invert_tilt) -
                axis_angle_degrees(home_tilt, tilt_scale, tilt_curve, invert_tilt))
  rotation = compose_ptz_rotation(
      home_rotation, delta_pan, delta_tilt, pan_axis)
  return rotation, delta_pan, delta_tilt


def scale_from_fov(space_min: float, space_max: float, fov_degrees: float) -> float:
  """Calculate degrees per ONVIF position unit from the advertised range."""
  span = space_max - space_min
  if not math.isfinite(span) or span <= 0.0:
    raise ValueError("PTZ position-space range must be finite and increasing")
  if not math.isfinite(fov_degrees) or fov_degrees <= 0.0:
    raise ValueError("PTZ field of view must be finite and positive")
  return fov_degrees / span


def euler_xyz_degrees_to_matrix(rotation: Sequence[float]) -> List[List[float]]:
  """Convert intrinsic Euler-XYZ angles in degrees to a 3x3 matrix."""
  if len(rotation) != 3:
    raise ValueError("Euler-XYZ rotation must contain three values")
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
  """Convert a 3x3 rotation matrix to intrinsic Euler-XYZ degrees."""
  sy = max(-1.0, min(1.0, matrix[0][2]))
  pitch = math.asin(sy)
  if abs(sy) < 0.9999999:
    roll = math.atan2(-matrix[1][2], matrix[2][2])
    yaw = math.atan2(-matrix[0][1], matrix[0][0])
  else:
    roll = math.atan2(matrix[2][1], matrix[1][1])
    yaw = 0.0
  return [math.degrees(roll), math.degrees(pitch), math.degrees(yaw)]


def matrix_multiply(
    left: Sequence[Sequence[float]],
    right: Sequence[Sequence[float]],
) -> List[List[float]]:
  """Multiply two 3x3 matrices."""
  return [[sum(left[row][index] * right[index][column] for index in range(3))
           for column in range(3)] for row in range(3)]


def rotation_matrix_x(degrees: float) -> List[List[float]]:
  """Create a rotation matrix around the X axis."""
  cosine, sine = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
  return [[1.0, 0.0, 0.0],
          [0.0, cosine, -sine],
          [0.0, sine, cosine]]


def rotation_matrix_z(degrees: float) -> List[List[float]]:
  """Create a rotation matrix around the Z axis."""
  cosine, sine = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
  return [[cosine, -sine, 0.0],
          [sine, cosine, 0.0],
          [0.0, 0.0, 1.0]]


def rotation_matrix_axis(axis: Sequence[float], degrees: float) -> List[List[float]]:
  """Create a rotation matrix around an arbitrary axis using Rodrigues' formula."""
  if len(axis) != 3:
    raise ValueError("Pan axis must contain three values")
  norm = math.sqrt(sum(value * value for value in axis))
  if norm == 0.0 or not math.isfinite(norm):
    raise ValueError("Pan axis must be finite and non-zero")
  x, y, z = (value / norm for value in axis)
  cosine, sine = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
  one_minus_cosine = 1.0 - cosine
  return [
      [one_minus_cosine * x * x + cosine,
       one_minus_cosine * x * y - sine * z,
       one_minus_cosine * x * z + sine * y],
      [one_minus_cosine * x * y + sine * z,
       one_minus_cosine * y * y + cosine,
       one_minus_cosine * y * z - sine * x],
      [one_minus_cosine * x * z - sine * y,
       one_minus_cosine * y * z + sine * x,
       one_minus_cosine * z * z + cosine],
  ]
