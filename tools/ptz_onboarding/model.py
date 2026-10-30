# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Offline lens/PTZ fitting and held-out verification using the lab algorithms."""

import datetime
import hashlib
import json

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

import fitting
from config import numbers, validate_points
from lens import fit_lens


def digest(value):
  """Identify the exact local calibration bundle being verified."""
  return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def check_capture(data, kind):
  """Require complete measurements on both axes at one fixed resolution."""
  if data["kind"] != kind:
    raise ValueError(f"Expected {kind} capture")
  for stop in data["stops"]:
    validate_points(stop)
    if stop["resolution"] != data["camera"]["resolution"]:
      raise ValueError("Mixed frame resolutions; keep one stream profile throughout")
  if kind == "ptz":
    for axis in fitting.AXES:
      positions = [s[axis] for s in data["stops"] if s["axis"] == axis]
      if len(set(positions)) < 3:
        raise ValueError(f"At least three distinct measured {axis} positions are required")
      directions = {s["direction"] for s in data["stops"] if s["axis"] == axis}
      if not {"up", "down"} <= directions:
        raise ValueError(f"Both measured {axis} approach directions are required")
  elif len({(s["pan"], s["tilt"]) for s in data["stops"]}) < 6:
    raise ValueError("Lens calibration needs at least six distinct views")


def solve_lens(data):
  """Fit conservatively; do not allow poorly constrained lens settings to pass."""
  check_capture(data, "lens")
  result = fit_lens({"views": data["stops"], "image_size": data["camera"]["resolution"]},
                    data["camera"])
  if result["poorly_constrained"]:
    raise ValueError("Lens fit is poorly constrained: spread tags across image edges and depth")
  result["camera_uid"] = data["camera_uid"]
  result["scene"] = data["camera"]["scene"]
  result["zoom"] = data["zoom"]
  result["dataset_sha256"] = digest(data)
  return result


def home_pose(stop, lens):
  """Recover scene-from-camera pose from raw tag points with the fitted lens."""
  k = lens["intrinsics"]
  matrix = np.array([[k["fx"], 0, k["cx"]], [0, k["fy"], k["cy"]], [0, 0, 1]], dtype=float)
  distortion = np.array([lens["distortion"][key] for key in ("k1", "k2", "p1", "p2", "k3")])
  ok, rvec, tvec = cv2.solvePnP(np.array(stop["points_3d"], dtype=float),
                              np.array(stop["points_2d"], dtype=float), matrix, distortion)
  if not ok:
    raise ValueError("AprilTag home pose could not be solved")
  rotation = Rotation.from_rotvec(rvec.ravel()).inv()
  translation = -rotation.apply(tvec.ravel())
  return rotation.as_euler("XYZ", degrees=True).tolist(), translation.tolist()


def measurement_data(data, lens, rotation, translation):
  """Adapt standalone captures to the original lab fitter's input contract."""
  if (data["camera_uid"] != lens["camera_uid"] or data["zoom"] != lens["zoom"] or
      data["camera"]["scene"] != lens["scene"] or
      data["camera"]["resolution"] != lens["config"]["resolution"]):
    raise ValueError("Lens and PTZ datasets must use the same camera, zoom and resolution")
  return {
    "start_pan": data["home"][0], "start_tilt": data["home"][1],
    "config": {"pan_scale": 90, "tilt_scale": 90},
    "stops": [{**stop, **lens["config"], "rotation": rotation, "translation": translation,
               "errors": []} for stop in data["stops"]],
  }


def solve_model(data, lens, degree=1):
  """Fit curves, axis and backlash; default to the simplest linear model."""
  check_capture(data, "ptz")
  rotation, translation = home_pose(data["stops"][0], lens["config"])
  adapted = measurement_data(data, lens, rotation, translation)
  reference = Rotation.from_euler("XYZ", rotation, degrees=True)
  for i, axis in enumerate(fitting.AXES):
    slopes = []
    for stop in data["stops"]:
      offset = stop[axis] - data["home"][i]
      if stop["axis"] != axis or abs(offset) < 1e-8:
        continue
      observed, _ = home_pose(stop, lens["config"])
      pose = Rotation.from_euler("XYZ", observed, degrees=True)
      relative = pose * reference.inv() if axis == "pan" else reference.inv() * pose
      angle = np.degrees(relative.as_rotvec())[2 if axis == "pan" else 0]
      slopes.append(angle / offset)
    scale = float(np.median(slopes))
    if not np.isfinite(scale) or abs(scale) < 1e-6:
      raise ValueError(f"{axis}: tag poses do not constrain an angular scale")
    adapted["config"][f"{axis}_scale"] = scale
  settings = fitting.load_settings(adapted)
  settings["home_approaches"] = dict(zip(fitting.AXES, data["approach"]))
  rejected = fitting.reject_bad_stops(adapted["stops"], Rotation.from_euler("XYZ", rotation,
                                                                         degrees=True))
  check_capture({**data, "stops": [s for i, s in enumerate(data["stops"]) if i not in rejected]},
                "ptz")
  fit, x = fitting.solve_best(adapted, settings, dict.fromkeys(fitting.AXES, degree),
                             True, True, False, rejected)
  pose, _, backlash, pan_axis, curves = fit.unpack(x)
  now = datetime.datetime.now(datetime.timezone.utc)
  axes = {}
  for i, axis in enumerate(fitting.AXES):
    positions = [s[axis] for s in data["stops"] if s["axis"] == axis]
    limits = [data["position_space"][f"{axis}_min"], data["position_space"][f"{axis}_max"]]
    warning = fitting.extrapolation_warning(curves[axis], positions, limits)
    if warning:
      raise ValueError(f"{axis}: {warning}; widen measurement coverage or use degree 1")
    offset = data["approach_offset"][i]
    before = data["home"][i] + (offset if data["approach"][i] == "decreasing" else -offset)
    travel = abs(fitting.angle(curves[axis], before) -
                 fitting.angle(curves[axis], data["home"][i]))
    if travel <= max(b for _, b in backlash[axis]) + 0.2:
      raise ValueError(f"{axis}: increase approach_offset to take up the fitted backlash")
    axes[axis] = {
      "axis": pan_axis.tolist() if axis == "pan" else [1.0, 0.0, 0.0],
      "frame": "world_home" if axis == "pan" else "camera_local",
      "curve": [float(v) for v in curves[axis]],
      "home_position": data["home"][i], "approach_direction": data["approach"][i],
      "backlash": fitting.backlash_config(backlash[axis]),
      "backlash_home_tolerance_deg": 0.2, "backlash_history_s": 10.0,
    }
  calibration = {
    "parameterization_version": "v1",
    "calibration_version": f"apriltag-{now.strftime('%Y%m%dT%H%M%S%fZ')}",
    "position_space": data["position_space"],
    "settle_angular_threshold_deg": 0.1, "settle_interval_s": 0.6,
    "composition_order": ["pan", "home", "tilt"], "axes": axes,
    "quality": {"reprojection_rms_px": float(np.sqrt(np.mean(fit.errors(x) ** 2)))},
    "provenance": {"measurement_tool": "tools/ptz_onboarding",
                   "measurement_date": now.isoformat(), "dataset_sha256": digest(data),
                   "lens_dataset_sha256": lens["dataset_sha256"],
                   "notes": "Tilt axis is nominal camera-local X; fixed zoom only"},
  }
  return {"camera_uid": data["camera_uid"], "zoom": data["zoom"],
          "camera_before": data["camera"],
          "home": data["home"], "approach": data["approach"],
          "lens": lens, "rotation": pose.as_euler("XYZ", degrees=True).tolist(),
          "translation": translation, "ptz_calibration": calibration,
          "fit_rejected_stops": sorted(rejected)}


def verify_model(bundle, data, max_rms):
  """Evaluate held-out points without refitting pose, curves, axis or backlash."""
  check_capture(data, "ptz")
  if (bundle["camera_uid"] != data["camera_uid"] or bundle["home"] != data["home"] or
      bundle["approach"] != data["approach"] or
      bundle["ptz_calibration"]["position_space"] != data["position_space"]):
    raise ValueError("Verification must use the model's camera, position space and approached home")
  adapted = measurement_data(data, bundle["lens"], bundle["rotation"], bundle["translation"])
  calibration = bundle["ptz_calibration"]
  deltas = {}
  for axis in fitting.AXES:
    spec = calibration["axes"][axis]
    curve = spec["curve"]
    direction = 1 if spec["approach_direction"] == "increasing" else -1
    fraction = -np.sign(fitting.slope(curve, spec["home_position"])) * direction
    deltas[axis] = fitting.angle_deltas(
      curve, [s[axis] for s in data["stops"]], spec["home_position"],
      fitting.backlash_table(spec["backlash"]), fraction)
  pose = Rotation.from_euler("XYZ", bundle["rotation"], degrees=True)
  axis = np.array(calibration["axes"]["pan"]["axis"])
  errors = []
  for i, stop in enumerate(adapted["stops"]):
    rotation = (Rotation.from_rotvec(axis * np.radians(deltas["pan"][i])) * pose *
                Rotation.from_euler("x", deltas["tilt"][i], degrees=True))
    world = np.array(stop["points_3d"]) - np.array(stop["translation"])
    if np.any((world @ rotation.as_matrix())[:, 2] <= 0):
      raise ValueError("Model projects a verification point behind the camera")
    errors.extend(fitting.stop_errors(stop, pose, deltas["pan"][i], deltas["tilt"][i], axis))
  numbers([float(e) for e in errors])
  rms = float(np.sqrt(np.mean(np.square(errors))))
  if rms > max_rms:
    raise ValueError(f"Held-out RMS {rms:.3f}px exceeds {max_rms:.3f}px; model not accepted")
  return {"model_sha256": digest(bundle), "rms_px": rms, "points": len(errors),
          "max_px": float(max(errors)), "capture": data}
