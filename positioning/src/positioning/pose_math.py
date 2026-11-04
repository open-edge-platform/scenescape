# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""PTZ pose math: raw ONVIF pan/tilt -> scene_from_camera orientation.

Rotations use scipy.spatial.transform.Rotation, matching
scene_common.transform.CameraPose (intrinsic Euler 'XYZ', degrees).
Pan/tilt deltas are composed as matrices about the calibrated axes, never
added to Euler components.
"""

import math
from typing import Optional, Sequence, Tuple

import numpy as np
from scipy.spatial.transform import Rotation

from positioning.ptz_model import AxisSpec, Backlash, PTZAxisModel

_APPROACH_STEP = 1e-6


def axis_angle_degrees(position: float, curve: Sequence[float]) -> float:
  """Absolute axis angle (degrees) for an ONVIF position.

  ``curve`` holds polynomial coefficients in increasing power, so
  ``[0, 42.05, 9.41]`` means ``42.05*t + 9.41*t^2``. Only differences between
  positions are used, so the constant term cancels.
  """
  return sum(c * position ** i for i, c in enumerate(curve))


def apply_backlash(previous_angle: Optional[float], reported_angle: float,
                   backlash_degrees: float) -> float:
  """Physical axis angle given the reported one (backlash deadband).

  The camera trails the encoder by up to half the slack either side; the
  physical angle only moves when the reported angle drags it past the band.

  @param  previous_angle    last known physical angle, or None to start centred
  @param  reported_angle    angle implied by the reported position
  @param  backlash_degrees  total slack; 0 disables the model
  """
  if backlash_degrees <= 0.0 or previous_angle is None:
    return reported_angle
  half = backlash_degrees / 2.0
  return min(max(previous_angle, reported_angle - half), reported_angle + half)


def backlash_degrees_at(backlash: Backlash, position: float) -> float:
  """Backlash at an ONVIF position.

  ``backlash`` is a scalar in degrees or ``[[position, degrees], ...]``
  interpolated linearly and held constant beyond the end nodes.
  """
  if not isinstance(backlash, (list, tuple)):
    return max(0.0, float(backlash or 0.0))
  knots = sorted((float(p), float(d)) for p, d in backlash)
  if position <= knots[0][0]:
    return max(0.0, knots[0][1])
  for (p0, d0), (p1, d1) in zip(knots, knots[1:]):
    if position <= p1:
      return max(0.0, d0 + (d1 - d0) * (position - p0) / (p1 - p0))
  return max(0.0, knots[-1][1])


def physical_home_angle(spec: AxisSpec) -> float:
  """Physical home angle (degrees) implied by the calibrated approach.

  ``approach_direction`` is the ONVIF position travel direction. The curve maps
  it to the angular travel direction, and the physical axis trails the reported
  angle by half the home backlash on that side of the deadband.
  """
  home_angle = axis_angle_degrees(spec.home_position, spec.curve)
  half = backlash_degrees_at(spec.backlash, spec.home_position) / 2.0
  position_direction = 1.0 if spec.approach_direction == "increasing" else -1.0
  previous_angle = axis_angle_degrees(
    spec.home_position - position_direction * _APPROACH_STEP, spec.curve)
  angle_direction = math.copysign(1.0, home_angle - previous_angle) \
    if home_angle != previous_angle else 0.0
  return home_angle - angle_direction * half


def axis_rotation(axis: Sequence[float], angle_degrees: float) -> Rotation:
  """Rotation of ``angle_degrees`` about ``axis`` (normalized here)."""
  unit = np.asarray(axis, dtype=float)
  unit = unit / np.linalg.norm(unit)
  return Rotation.from_rotvec(math.radians(angle_degrees) * unit)


def compose_ptz_rotation(model: PTZAxisModel, home_rotation: Rotation,
                         delta_pan_degrees: float, delta_tilt_degrees: float) -> Rotation:
  """Rotate the home orientation by pan/tilt deltas about the calibrated axes.

  The result is the left-to-right product in ``model.composition_order``,
  e.g. ``["pan", "home", "tilt"]`` -> ``R_pan @ R_home @ R_tilt``. Axes left of
  ``home`` are in the home scene frame; axes right of it are in the home camera
  frame (enforced by ``load_ptz_model``).
  """
  factors = {
    "home": home_rotation,
    "pan": axis_rotation(model.pan.axis, delta_pan_degrees),
    "tilt": axis_rotation(model.tilt.axis, delta_tilt_degrees),
  }
  result = Rotation.identity()
  for element in model.composition_order:
    result = result * factors[element]
  return result


def rotation_from_ptz_delta(model: PTZAxisModel, home_rotation: Rotation,
                            pan: float, tilt: float) -> Tuple[Rotation, float, float]:
  """Orientation for a raw pan/tilt reading, ignoring backlash.

  @return (rotation, delta_pan_degrees, delta_tilt_degrees)
  """
  delta_pan = (axis_angle_degrees(pan, model.pan.curve)
               - axis_angle_degrees(model.pan.home_position, model.pan.curve))
  delta_tilt = (axis_angle_degrees(tilt, model.tilt.curve)
                - axis_angle_degrees(model.tilt.home_position, model.tilt.curve))
  return compose_ptz_rotation(model, home_rotation, delta_pan, delta_tilt), delta_pan, delta_tilt


def rotation_delta_magnitude(rotation_a: Rotation, rotation_b: Rotation) -> float:
  """Angle (degrees) of the rotation taking ``rotation_a`` to ``rotation_b``."""
  return math.degrees((rotation_a.inv() * rotation_b).magnitude())


def scene_from_camera_matrix(rotation: Rotation, translation: Sequence[float]) -> np.ndarray:
  """Row-major 4x4 rigid scene_from_camera transform (translation in metres)."""
  matrix = np.eye(4)
  matrix[:3, :3] = rotation.as_matrix()
  matrix[:3, 3] = np.asarray(translation, dtype=float)
  return matrix
