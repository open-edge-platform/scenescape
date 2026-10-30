# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Configuration and measurement validation shared by the standalone commands."""

import json
import math
import re
from pathlib import Path


def read_json(path):
  """Read a JSON file."""
  with open(path, encoding="utf-8") as handle:
    return json.load(handle)


def write_json(path, value):
  """Save private local results; refuse to overwrite a previous measurement."""
  serialized = json.dumps(value, indent=2, allow_nan=False)
  with open(path, "x", encoding="utf-8", opener=_private_file) as handle:
    handle.write(serialized + "\n")


def _private_file(path, flags):
  import os
  return os.open(path, flags, 0o600)


def numbers(value, count=None):
  """Require a finite, non-empty numeric list."""
  if (not isinstance(value, list) or not value or
      (count is not None and len(value) != count) or
      any(isinstance(v, bool) or not isinstance(v, (int, float)) or
          not math.isfinite(v) for v in value)):
    raise ValueError(f"Expected {count or 'one or more'} finite numbers, got {value!r}")
  return value


def load_config(path, motion_mode="full"):
  """Validate explicit safe motion limits before any camera connection."""
  config = read_json(path)
  uid = config["camera_uid"]
  if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,255}", uid):
    raise ValueError("camera_uid must be a Manager camera UID without MQTT wildcards")
  for key in ("manager_url", "autocalibration_url"):
    if not config[key].startswith("https://"):
      raise ValueError(f"{key} must use HTTPS")
  for key in ("ca_cert", "manager_auth"):
    config[key] = str((Path(path).resolve().parent / config[key]).resolve())
  for section in ("mqtt", "onvif"):
    config[section]["auth"] = str(
      (Path(path).resolve().parent / config[section]["auth"]).resolve())
  skew = config["mqtt"].get("max_clock_skew_s", 0.1)
  numbers([skew], 1)
  if skew < 0:
    raise ValueError("mqtt.max_clock_skew_s must be non-negative")
  if motion_mode == "probe":
    return config
  motion = config["motion"]
  home = numbers(motion["home"], 2)
  offsets = numbers(motion["approach_offset"], 2)
  if motion["approach"] not in ([a, b] for a in ("increasing", "decreasing")
                                for b in ("increasing", "decreasing")):
    raise ValueError("approach must specify increasing/decreasing for pan and tilt")
  for i, axis in enumerate(("pan", "tilt")):
    low, high = numbers(motion[f"{axis}_range"], 2)
    if low >= high or offsets[i] <= 0:
      raise ValueError(f"{axis}: ordered limits and a positive approach_offset are required")
    before = home[i] + (offsets[i] if motion["approach"][i] == "decreasing" else -offsets[i])
    targets = [home[i], before]
    if motion_mode == "full":
      targets += [*numbers(motion[f"lens_{axis}"]),
                  *(home[i] + d for d in numbers(motion[f"{axis}_path"]))]
    if any(not low <= v <= high for v in targets):
      raise ValueError(f"{axis}: home, approach, lens and path targets must be inside safe limits")
    if motion_mode != "full":
      continue
    if len(set(motion[f"lens_{axis}"])) < 2:
      raise ValueError(f"lens_{axis} needs at least two distinct positions")
    if len(set(motion[f"{axis}_path"])) < 3 or motion[f"{axis}_path"][-1] != 0:
      raise ValueError(f"{axis}_path needs three distinct offsets and must end at zero")
    moves = [b - a for a, b in zip([0, *motion[f"{axis}_path"]], motion[f"{axis}_path"])]
    if not any(d > 0 for d in moves) or not any(d < 0 for d in moves):
      raise ValueError(f"{axis}_path must measure both travel directions")
  for key in ("settle_s", "timeout_s", "tolerance"):
    numbers([motion[key]], 1)
    if motion[key] <= 0:
      raise ValueError(f"{key} must be positive")
  if motion_mode == "full" and len(set(motion["lens_pan"])) * len(set(motion["lens_tilt"])) < 6:
    raise ValueError("The lens grid needs at least six distinct views")
  if motion["tolerance"] >= min(offsets) / 2:
    raise ValueError("tolerance must be less than half the home approach offsets")
  numbers([config["max_rms_px"]], 1)
  if config["max_rms_px"] <= 0:
    raise ValueError("max_rms_px must be positive")
  return config


def validate_points(stop):
  """Reject missing, insufficient, malformed or non-finite correspondences."""
  p2, p3 = stop["points_2d"], stop["points_3d"]
  if len(p2) < 6 or len(p2) != len(p3):
    raise ValueError("Each measured stop needs at least six matched AprilTag points")
  for point in p2:
    numbers(point, 2)
  for point in p3:
    numbers(point, 3)
