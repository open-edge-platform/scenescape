# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Versioned PTZ calibration model (parameterization v1).

Mirrors docs/user-guide/api-docs/positioning/v1/ptz_calibration.schema.json and adds the semantic
checks JSON Schema cannot express (finite values, unit axes, range ordering,
frame/composition consistency).
"""

import math
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Tuple, Union

PARAMETERIZATION_VERSION = "v1"
FRAME_WORLD_HOME = "world_home"
FRAME_CAMERA_LOCAL = "camera_local"
APPROACH_DIRECTIONS = ("increasing", "decreasing")
COMPOSITION_ELEMENTS = ("pan", "home", "tilt")
AXIS_NAMES = ("pan", "tilt")
UNIT_AXIS_TOLERANCE = 1e-3

Backlash = Union[float, Tuple[Tuple[float, float], ...]]

_TOP_LEVEL_KEYS = {
  "parameterization_version", "calibration_version", "position_space",
  "settle_angular_threshold_deg", "settle_interval_s", "composition_order",
  "axes", "quality", "provenance",
}
_AXIS_KEYS = {
  "axis", "frame", "curve", "home_position", "approach_direction", "backlash",
  "backlash_home_tolerance_deg", "backlash_history_s",
}
_POSITION_SPACE_KEYS = {"uri", "pan_min", "pan_max", "tilt_min", "tilt_max"}


class PTZCalibrationError(ValueError):
  """Raised when a ptz_calibration payload is missing, malformed, or inconsistent."""


@dataclass(frozen=True)
class PositionSpace:
  uri: str
  pan_min: float
  pan_max: float
  tilt_min: float
  tilt_max: float


@dataclass(frozen=True)
class AxisSpec:
  axis: Tuple[float, float, float]
  frame: str
  curve: Tuple[float, ...]
  home_position: float
  approach_direction: str
  backlash: Backlash
  backlash_home_tolerance_deg: float
  backlash_history_s: float


@dataclass(frozen=True)
class PTZAxisModel:
  parameterization_version: str
  calibration_version: str
  position_space: PositionSpace
  settle_angular_threshold_deg: float
  settle_interval_s: float
  composition_order: Tuple[str, ...]
  pan: AxisSpec
  tilt: AxisSpec
  reprojection_rms_px: float
  provenance: Optional[Mapping[str, Any]] = None

  def axis_spec(self, name: str) -> AxisSpec:
    return self.pan if name == "pan" else self.tilt


def load_ptz_model(payload: Mapping[str, Any]) -> PTZAxisModel:
  """Validate a ptz_calibration payload and build a PTZAxisModel.

  @raises PTZCalibrationError on any missing, malformed, or inconsistent value
  """
  _require_mapping(payload, "ptz_calibration")
  _check_keys(payload, _TOP_LEVEL_KEYS, _TOP_LEVEL_KEYS - {"provenance"}, "ptz_calibration")

  if payload["parameterization_version"] != PARAMETERIZATION_VERSION:
    raise PTZCalibrationError(
      f"Unsupported parameterization_version: {payload['parameterization_version']!r}")
  calibration_version = payload["calibration_version"]
  if not isinstance(calibration_version, str) or not 0 < len(calibration_version) <= 128:
    raise PTZCalibrationError("calibration_version must be a 1-128 character string")

  space = _load_position_space(payload["position_space"])
  order = _load_composition_order(payload["composition_order"])

  axes = payload["axes"]
  _require_mapping(axes, "axes")
  _check_keys(axes, set(AXIS_NAMES), set(AXIS_NAMES), "axes")
  ranges = {"pan": (space.pan_min, space.pan_max), "tilt": (space.tilt_min, space.tilt_max)}
  specs = {name: _load_axis(axes[name], name, ranges[name]) for name in AXIS_NAMES}

  home_index = order.index("home")
  for name in AXIS_NAMES:
    expected = FRAME_WORLD_HOME if order.index(name) < home_index else FRAME_CAMERA_LOCAL
    if specs[name].frame != expected:
      raise PTZCalibrationError(
        f"axes.{name}.frame must be {expected!r} for composition_order {list(order)}")

  quality = payload["quality"]
  _require_mapping(quality, "quality")
  _check_keys(quality, {"reprojection_rms_px"}, {"reprojection_rms_px"}, "quality")

  provenance = payload.get("provenance")
  if provenance is not None:
    _require_mapping(provenance, "provenance")

  return PTZAxisModel(
    parameterization_version=PARAMETERIZATION_VERSION,
    calibration_version=calibration_version,
    position_space=space,
    settle_angular_threshold_deg=_nonnegative(
      payload["settle_angular_threshold_deg"], "settle_angular_threshold_deg"),
    settle_interval_s=_nonnegative(payload["settle_interval_s"], "settle_interval_s"),
    composition_order=order,
    pan=specs["pan"],
    tilt=specs["tilt"],
    reprojection_rms_px=_nonnegative(
      quality["reprojection_rms_px"], "quality.reprojection_rms_px"),
    provenance=provenance,
  )


def _load_position_space(value) -> PositionSpace:
  _require_mapping(value, "position_space")
  _check_keys(value, _POSITION_SPACE_KEYS, _POSITION_SPACE_KEYS, "position_space")
  uri = value["uri"]
  if not isinstance(uri, str) or not 0 < len(uri) <= 512:
    raise PTZCalibrationError("position_space.uri must be a 1-512 character string")
  bounds = {key: _finite(value[key], f"position_space.{key}")
            for key in ("pan_min", "pan_max", "tilt_min", "tilt_max")}
  for axis in AXIS_NAMES:
    if bounds[f"{axis}_min"] >= bounds[f"{axis}_max"]:
      raise PTZCalibrationError(f"position_space.{axis}_min must be < {axis}_max")
  return PositionSpace(uri=uri, **bounds)


def _load_composition_order(value) -> Tuple[str, ...]:
  if (not isinstance(value, (list, tuple)) or len(value) != len(COMPOSITION_ELEMENTS)
      or sorted(value) != sorted(COMPOSITION_ELEMENTS)):
    raise PTZCalibrationError(
      "composition_order must contain 'pan', 'home' and 'tilt' exactly once")
  return tuple(value)


def _load_axis(value, name: str, position_range: Tuple[float, float]) -> AxisSpec:
  label = f"axes.{name}"
  _require_mapping(value, label)
  _check_keys(value, _AXIS_KEYS, _AXIS_KEYS, label)

  raw_axis = value["axis"]
  if not isinstance(raw_axis, (list, tuple)) or len(raw_axis) != 3:
    raise PTZCalibrationError(f"{label}.axis must have three components")
  components = [_finite(c, f"{label}.axis") for c in raw_axis]
  norm = math.sqrt(sum(c * c for c in components))
  if abs(norm - 1.0) > UNIT_AXIS_TOLERANCE:
    raise PTZCalibrationError(f"{label}.axis must be a unit vector (norm {norm:.6f})")
  axis = tuple(c / norm for c in components)

  frame = value["frame"]
  if frame not in (FRAME_WORLD_HOME, FRAME_CAMERA_LOCAL):
    raise PTZCalibrationError(f"{label}.frame must be 'world_home' or 'camera_local'")

  curve = value["curve"]
  if not isinstance(curve, (list, tuple)) or not 2 <= len(curve) <= 8:
    raise PTZCalibrationError(f"{label}.curve must have 2-8 coefficients")
  curve = tuple(_finite(c, f"{label}.curve") for c in curve)
  if all(c == 0.0 for c in curve[1:]):
    raise PTZCalibrationError(f"{label}.curve must not be constant")

  home_position = _finite(value["home_position"], f"{label}.home_position")
  if not position_range[0] <= home_position <= position_range[1]:
    raise PTZCalibrationError(f"{label}.home_position is outside the advertised position space")

  approach = value["approach_direction"]
  if approach not in APPROACH_DIRECTIONS:
    raise PTZCalibrationError(f"{label}.approach_direction must be one of {APPROACH_DIRECTIONS}")

  return AxisSpec(
    axis=axis,
    frame=frame,
    curve=curve,
    home_position=home_position,
    approach_direction=approach,
    backlash=_load_backlash(value["backlash"], f"{label}.backlash"),
    backlash_home_tolerance_deg=_nonnegative(
      value["backlash_home_tolerance_deg"], f"{label}.backlash_home_tolerance_deg"),
    backlash_history_s=_nonnegative(value["backlash_history_s"], f"{label}.backlash_history_s"),
  )


def _load_backlash(value, label: str) -> Backlash:
  if not isinstance(value, (list, tuple)):
    return _nonnegative(value, label)
  if not 1 <= len(value) <= 64:
    raise PTZCalibrationError(f"{label} must have 1-64 nodes")
  nodes = []
  for node in value:
    if not isinstance(node, (list, tuple)) or len(node) != 2:
      raise PTZCalibrationError(f"{label} nodes must be [position, degrees] pairs")
    nodes.append((_finite(node[0], label), _nonnegative(node[1], label)))
  nodes.sort()
  if any(a[0] == b[0] for a, b in zip(nodes, nodes[1:])):
    raise PTZCalibrationError(f"{label} node positions must be distinct")
  return tuple(nodes)


def _require_mapping(value, label: str) -> None:
  if not isinstance(value, Mapping):
    raise PTZCalibrationError(f"{label} must be an object")


def _check_keys(value: Mapping, allowed: set, required: set, label: str) -> None:
  missing = required - value.keys()
  if missing:
    raise PTZCalibrationError(f"{label} is missing {sorted(missing)}")
  unknown = value.keys() - allowed
  if unknown:
    raise PTZCalibrationError(f"{label} has unsupported fields {sorted(unknown)}")


def _finite(value, label: str) -> float:
  if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
    raise PTZCalibrationError(f"{label} must be a finite number")
  return float(value)


def _nonnegative(value, label: str) -> float:
  number = _finite(value, label)
  if number < 0.0:
    raise PTZCalibrationError(f"{label} must be >= 0")
  return number
