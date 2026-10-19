# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Validation of the Positioning ptz_calibration v1 block at the Manager boundary.

Errors are reported as stable `<path>: <code>` strings, for example
`axes.pan.axis: not_unit_vector`. Codes are part of the API contract.
"""

import math

import numpy as np

PARAMETERIZATION_VERSION = "v1"
AXIS_NAMES = ("pan", "tilt")
COMPOSITION_ELEMENTS = ("pan", "home", "tilt")
FRAMES = ("world_home", "camera_local")
APPROACH_DIRECTIONS = ("increasing", "decreasing")
UNIT_AXIS_TOLERANCE = 1e-3

TOP_LEVEL_REQUIRED = (
  "parameterization_version", "calibration_version", "position_space",
  "settle_angular_threshold_deg", "settle_interval_s", "composition_order",
  "axes", "quality",
)
TOP_LEVEL_OPTIONAL = ("provenance",)
POSITION_SPACE_FIELDS = ("uri", "pan_min", "pan_max", "tilt_min", "tilt_max")
AXIS_FIELDS = (
  "axis", "frame", "curve", "home_position", "approach_direction", "backlash",
  "backlash_home_tolerance_deg", "backlash_history_s",
)
QUALITY_FIELDS = ("reprojection_rms_px",)

NOT_OBJECT = "not_object"
REQUIRED = "required"
UNKNOWN_FIELD = "unknown_field"
NOT_STRING = "not_string"
INVALID_LENGTH = "invalid_length"
NOT_NUMBER = "not_number"
NOT_FINITE = "not_finite"
NEGATIVE = "negative"
NOT_POSITIVE = "not_positive"
UNSUPPORTED_VERSION = "unsupported_version"
INVALID_RANGE = "invalid_range"
INVALID_COMPOSITION_ORDER = "invalid_composition_order"
NOT_ARRAY = "not_array"
INVALID_SIZE = "invalid_size"
NOT_UNIT_VECTOR = "not_unit_vector"
INVALID_CHOICE = "invalid_choice"
FRAME_ORDER_MISMATCH = "frame_order_mismatch"
CONSTANT_CURVE = "constant_curve"
OUT_OF_RANGE = "out_of_range"
INVALID_NODE = "invalid_node"
DUPLICATE_POSITION = "duplicate_position"
EXCEEDS_TRAVEL = "exceeds_travel"
THRESHOLD_NOT_CONFIGURED = "threshold_not_configured"
EXCEEDS_THRESHOLD = "exceeds_threshold"


class PTZCalibrationError(ValueError):
  def __init__(self, path, code):
    super().__init__(f"{path}: {code}")
    self.path = path
    self.code = code


def validate_ptz_calibration(value, residual_threshold_px):
  """Validate a non-null ptz_calibration block.

  @param value                  Decoded ptz_calibration JSON
  @param residual_threshold_px  Deployment import threshold (raw setting value)
  @raises PTZCalibrationError   on the first violation, with a stable path and code
  """
  _check_object(value, "ptz_calibration", TOP_LEVEL_REQUIRED, TOP_LEVEL_OPTIONAL)

  if value["parameterization_version"] != PARAMETERIZATION_VERSION:
    raise PTZCalibrationError("parameterization_version", UNSUPPORTED_VERSION)
  _check_string(value["calibration_version"], "calibration_version", 128)

  ranges = _check_position_space(value["position_space"])
  order = _check_composition_order(value["composition_order"])

  settle_threshold = _positive(value["settle_angular_threshold_deg"],
                               "settle_angular_threshold_deg")
  _positive(value["settle_interval_s"], "settle_interval_s")

  axes = value["axes"]
  _check_object(axes, "axes", AXIS_NAMES)
  for name in AXIS_NAMES:
    travel = _check_axis(axes[name], f"axes.{name}", name, order, ranges[name])
    if settle_threshold > travel:
      raise PTZCalibrationError("settle_angular_threshold_deg", EXCEEDS_TRAVEL)

  quality = value["quality"]
  _check_object(quality, "quality", QUALITY_FIELDS)
  residual = _nonnegative(quality["reprojection_rms_px"], "quality.reprojection_rms_px")
  limit = _residual_threshold(residual_threshold_px)
  if limit is None:
    raise PTZCalibrationError("quality.reprojection_rms_px", THRESHOLD_NOT_CONFIGURED)
  if residual > limit:
    raise PTZCalibrationError("quality.reprojection_rms_px", EXCEEDS_THRESHOLD)

  if "provenance" in value and not isinstance(value["provenance"], dict):
    raise PTZCalibrationError("provenance", NOT_OBJECT)
  return value


def axis_travel_deg(curve, position_range):
  """Angular span in degrees covered by `curve` over the calibrated position range."""
  lower, upper = position_range
  polynomial = np.polynomial.Polynomial(curve)
  positions = [lower, upper]
  for root in polynomial.deriv().roots():
    if abs(root.imag) < 1e-12 and lower < root.real < upper:
      positions.append(root.real)
  angles = polynomial(np.array(positions))
  return float(angles.max() - angles.min())


def _check_position_space(position):
  _check_object(position, "position_space", POSITION_SPACE_FIELDS)
  _check_string(position["uri"], "position_space.uri", 512)
  ranges = {}
  for name in AXIS_NAMES:
    lower = _finite(position[f"{name}_min"], f"position_space.{name}_min")
    upper = _finite(position[f"{name}_max"], f"position_space.{name}_max")
    if lower >= upper:
      raise PTZCalibrationError(f"position_space.{name}_min", INVALID_RANGE)
    ranges[name] = (lower, upper)
  return ranges


def _check_composition_order(order):
  if not isinstance(order, list) or len(order) != len(COMPOSITION_ELEMENTS) \
     or any(not isinstance(element, str) for element in order) \
     or sorted(order) != sorted(COMPOSITION_ELEMENTS):
    raise PTZCalibrationError("composition_order", INVALID_COMPOSITION_ORDER)
  return order


def _check_axis(axis, path, name, order, position_range):
  _check_object(axis, path, AXIS_FIELDS)

  vector = _array(axis["axis"], f"{path}.axis", 3, 3)
  vector = [_finite(component, f"{path}.axis") for component in vector]
  if abs(math.sqrt(sum(component * component for component in vector)) - 1.0) \
     > UNIT_AXIS_TOLERANCE:
    raise PTZCalibrationError(f"{path}.axis", NOT_UNIT_VECTOR)

  frame = axis["frame"]
  if frame not in FRAMES:
    raise PTZCalibrationError(f"{path}.frame", INVALID_CHOICE)
  expected_frame = "world_home" if order.index(name) < order.index("home") else "camera_local"
  if frame != expected_frame:
    raise PTZCalibrationError(f"{path}.frame", FRAME_ORDER_MISMATCH)

  curve = _array(axis["curve"], f"{path}.curve", 2, 8)
  curve = [_finite(coefficient, f"{path}.curve") for coefficient in curve]
  if all(coefficient == 0 for coefficient in curve[1:]):
    raise PTZCalibrationError(f"{path}.curve", CONSTANT_CURVE)

  home = _finite(axis["home_position"], f"{path}.home_position")
  if not position_range[0] <= home <= position_range[1]:
    raise PTZCalibrationError(f"{path}.home_position", OUT_OF_RANGE)

  if axis["approach_direction"] not in APPROACH_DIRECTIONS:
    raise PTZCalibrationError(f"{path}.approach_direction", INVALID_CHOICE)

  _check_backlash(axis["backlash"], f"{path}.backlash")

  travel = axis_travel_deg(curve, position_range)
  tolerance = _positive(axis["backlash_home_tolerance_deg"],
                        f"{path}.backlash_home_tolerance_deg")
  if tolerance > travel:
    raise PTZCalibrationError(f"{path}.backlash_home_tolerance_deg", EXCEEDS_TRAVEL)
  _positive(axis["backlash_history_s"], f"{path}.backlash_history_s")
  return travel


def _check_backlash(backlash, path):
  if not isinstance(backlash, list):
    _nonnegative(backlash, path)
    return
  _array(backlash, path, 1, 64)
  positions = set()
  for index, node in enumerate(backlash):
    node_path = f"{path}[{index}]"
    if not isinstance(node, list) or len(node) != 2:
      raise PTZCalibrationError(node_path, INVALID_NODE)
    position = _finite(node[0], node_path)
    _nonnegative(node[1], node_path)
    if position in positions:
      raise PTZCalibrationError(node_path, DUPLICATE_POSITION)
    positions.add(position)


def _residual_threshold(raw):
  try:
    limit = float(raw)
  except (TypeError, ValueError):
    return None
  if not math.isfinite(limit) or limit <= 0:
    return None
  return limit


def _check_object(data, path, required, optional=()):
  if not isinstance(data, dict):
    raise PTZCalibrationError(path, NOT_OBJECT)
  prefix = "" if path == "ptz_calibration" else f"{path}."
  missing = [field for field in required if field not in data]
  if missing:
    raise PTZCalibrationError(prefix + missing[0], REQUIRED)
  unknown = sorted(data.keys() - set(required) - set(optional))
  if unknown:
    raise PTZCalibrationError(prefix + unknown[0], UNKNOWN_FIELD)


def _check_string(value, path, max_length):
  if not isinstance(value, str):
    raise PTZCalibrationError(path, NOT_STRING)
  if not 1 <= len(value) <= max_length:
    raise PTZCalibrationError(path, INVALID_LENGTH)


def _array(value, path, min_items, max_items):
  if not isinstance(value, list):
    raise PTZCalibrationError(path, NOT_ARRAY)
  if not min_items <= len(value) <= max_items:
    raise PTZCalibrationError(path, INVALID_SIZE)
  return value


def _finite(value, path):
  if isinstance(value, bool) or not isinstance(value, (int, float)):
    raise PTZCalibrationError(path, NOT_NUMBER)
  try:
    number = float(value)
  except OverflowError:
    raise PTZCalibrationError(path, NOT_FINITE)
  if not math.isfinite(number):
    raise PTZCalibrationError(path, NOT_FINITE)
  return number


def _nonnegative(value, path):
  number = _finite(value, path)
  if number < 0:
    raise PTZCalibrationError(path, NEGATIVE)
  return number


def _positive(value, path):
  number = _finite(value, path)
  if number <= 0:
    raise PTZCalibrationError(path, NOT_POSITIVE)
  return number
