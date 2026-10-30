#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Standalone AprilTag PTZ onboarding. See README.md before enabling camera motion."""

import argparse
import copy
import json
import sys
from pathlib import Path

from config import load_config, read_json, write_json


SNAPSHOT_KEYS = ("name", "scene", "resolution", "intrinsics", "distortion",
                 "rotation", "translation", "scale", "transform_type", "transforms",
                 "ptz_calibration")


def capture(config, kind):
  """Collect local data, always returning to approached home even after failure."""
  from devices import Camera, Manager, Tags

  manager = Manager(config)
  source = manager.camera(config["camera_uid"])
  snapshot = {key: source[key] for key in SNAPSHOT_KEYS if key in source}
  camera = Camera(config)
  tags = Tags(config)
  motion = config["motion"]
  home = motion["home"]
  if kind == "lens":
    positions = [("lens", p, t) for t in motion["lens_tilt"] for p in motion["lens_pan"]]
  else:
    positions = [("pan", home[0], home[1])]
    positions += [("pan", home[0] + d, home[1]) for d in motion["pan_path"]]
    positions += [("tilt", home[0], home[1] + d) for d in motion["tilt_path"]]
  result = {"kind": kind, "camera_uid": config["camera_uid"], "camera": snapshot,
            "home": home, "approach": motion["approach"],
            "approach_offset": motion["approach_offset"], "position_space": camera.space,
            "zoom": float(camera.zoom.x) if camera.zoom is not None else None, "stops": []}
  previous = home
  try:
    camera.home()
    for i, (axis, pan, tilt) in enumerate(positions):
      actual = camera.move(pan, tilt)
      stop = tags.collect()
      if not result["stops"]:
        # A camera's configured resolution may be stale; use the actual calibration stream.
        snapshot["resolution"] = stop["resolution"]
      axis_index = 0 if axis == "pan" else 1
      moved = actual[axis_index] - previous[axis_index]
      stop.update(axis=axis, pan=actual[0], tilt=actual[1],
                  direction="-" if abs(moved) <= motion["tolerance"] else
                  ("up" if moved > 0 else "down"))
      result["stops"].append(stop)
      previous = actual
      print(f"{i + 1}/{len(positions)}: {len(stop['points_2d'])} matched points", flush=True)
  finally:
    print("Returning to configured home using the calibrated approach", flush=True)
    camera.home()
  return result


def apply_model(config, bundle, verification, backup_path):
  """Apply one verified bundle atomically in a single Manager camera update."""
  from devices import Camera, Manager
  from model import digest, verify_model

  if verification["model_sha256"] != digest(bundle):
    raise ValueError("Verification belongs to a different model")
  checked = verify_model(bundle, verification["capture"], config["max_rms_px"])
  if config["camera_uid"] != bundle["camera_uid"]:
    raise ValueError("Config selects a different camera")
  camera = Camera(config)
  actual = camera.status().Position
  if camera.space != bundle["ptz_calibration"]["position_space"]:
    raise ValueError("ONVIF position space changed after measurement")
  if any(abs(a - h) > config["motion"]["tolerance"]
         for a, h in zip((actual.PanTilt.x, actual.PanTilt.y), bundle["home"])):
    raise ValueError("Camera is not at the measured home; repeat verification before applying")
  zoom = float(actual.Zoom.x) if actual.Zoom is not None else None
  if zoom != bundle["zoom"]:
    raise ValueError("Zoom changed after measurement; repeat measurements at a fixed zoom")
  manager = Manager(config)
  before = manager.camera(bundle["camera_uid"])
  if before["scene"] != bundle["camera_before"]["scene"]:
    raise ValueError("Camera was moved to a different scene after measurement")
  backup = {key: before[key] for key in SNAPSHOT_KEYS if key in before}
  write_json(backup_path, backup)
  calibration = copy.deepcopy(bundle["ptz_calibration"])
  calibration["quality"]["reprojection_rms_px"] = checked["rms_px"]
  update = {**bundle["lens"]["config"], "name": before["name"], "transform_type": "euler",
            "rotation": bundle["rotation"], "translation": bundle["translation"],
            "scale": [1.0, 1.0, 1.0], "ptz_calibration": calibration}
  manager.request("PUT", f"camera/{bundle['camera_uid']}", json=update)
  after = manager.camera(bundle["camera_uid"])
  for key in ("ptz_calibration", "resolution", "intrinsics", "distortion", "scale"):
    if after[key] != update[key]:
      raise RuntimeError(f"Manager read-back mismatch for {key}; inspect backup {backup_path}")
  import numpy as np
  from scipy.spatial.transform import Rotation
  expected = Rotation.from_euler("XYZ", update["rotation"], degrees=True)
  stored = Rotation.from_euler("XYZ", after["rotation"], degrees=True)
  if ((expected.inv() * stored).magnitude() > 1e-5 or
      not np.allclose(after["translation"], update["translation"], atol=1e-6)):
    raise RuntimeError(f"Manager home pose read-back mismatch; inspect backup {backup_path}")
  print(f"Applied and read back {bundle['camera_uid']}; held-out RMS {checked['rms_px']:.3f}px")


def main(argv=None):
  """Run one explicit, independently repeatable workflow step."""
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--config", required=True, help="Local camera JSON; see camera.example.json")
  commands = parser.add_subparsers(dest="command", required=True)
  commands.add_parser("inspect", help="Read ONVIF profile, position and advertised limits; no movement")
  commands.add_parser("check", help="Validate configuration, API, ONVIF and fresh tag visibility; no moves")
  sub = commands.add_parser("discover", help="MOVE inside approved limits; propose tag-visible paths")
  sub.add_argument("--output-dir", required=True, help="New directory for coverage and proposed config")
  sub.add_argument("--steps", type=int, choices=range(3, 10), default=5,
                   help="Grid points per axis plus home/approach points (3-9; default 5)")
  sub.add_argument("--yes", action="store_true")
  sub = commands.add_parser("onboard", help="MOVE camera; collect, fit and verify locally; no Manager writes")
  sub.add_argument("--output-dir", required=True, help="New directory for all results")
  sub.add_argument("--yes", action="store_true")
  for name in ("capture-lens", "capture-ptz"):
    sub = commands.add_parser(name, help="MOVE camera; collect data without Manager writes")
    sub.add_argument("--output", required=True)
    sub.add_argument("--yes", action="store_true", help="Confirm physical camera movement")
  sub = commands.add_parser("fit-lens", help="Offline lens fitting")
  sub.add_argument("--input", required=True)
  sub.add_argument("--output", required=True)
  sub = commands.add_parser("fit-ptz", help="Offline PTZ model fitting")
  sub.add_argument("--input", required=True)
  sub.add_argument("--lens", required=True)
  sub.add_argument("--degree", type=int, choices=(1, 2), default=1)
  sub.add_argument("--output", required=True)
  sub = commands.add_parser("verify", help="MOVE camera; independent held-out validation; no writes")
  sub.add_argument("--model", required=True)
  sub.add_argument("--output", required=True)
  sub.add_argument("--yes", action="store_true")
  sub = commands.add_parser("apply", help="Write verified lens, home pose and PTZ model to Manager")
  sub.add_argument("--model", required=True)
  sub.add_argument("--verification", required=True)
  sub.add_argument("--backup", required=True)
  sub.add_argument("--yes", action="store_true", help="Confirm Manager calibration replacement")
  args = parser.parse_args(argv)
  mode = {"inspect": "probe", "discover": "planning", "check": "probe"}.get(args.command, "full")
  config = load_config(args.config, motion_mode=mode)
  if args.command in ("discover", "onboard", "capture-lens", "capture-ptz", "verify", "apply") and not args.yes:
    parser.error("Explicit --yes is required; read the motion/write warnings in README.md")
  for name in ("output", "backup"):
    path = getattr(args, name, None)
    if path and (Path(path).exists() or not Path(path).parent.is_dir()):
      parser.error(f"{path}: must be a new file in an existing directory")
  return execute(args, config)


def execute(args, config):
  """Dispatch commands; fitting imports do not depend on running services."""
  from model import solve_lens, solve_model, verify_model

  if args.command == "inspect":
    from devices import Camera
    camera = Camera(config, validate_limits=False)
    position = camera.status().Position
    print(json.dumps({"profile_token": camera.token, "pan": position.PanTilt.x,
                      "tilt": position.PanTilt.y,
                      "zoom": position.Zoom.x if position.Zoom is not None else None,
                      "position_space": camera.space}, indent=2))
  elif args.command == "discover":
    from discovery import discover
    discover(config, Path(args.output_dir), args.steps)
  elif args.command == "onboard":
    directory = Path(args.output_dir)
    directory.mkdir(mode=0o700)
    data = capture(config, "lens")
    write_json(directory / "lens-capture.json", data)
    lens = solve_lens(data)
    write_json(directory / "lens.json", lens)
    data = capture(config, "ptz")
    write_json(directory / "ptz-capture.json", data)
    bundle = solve_model(data, lens)
    write_json(directory / "model.json", bundle)
    data = capture(config, "ptz")
    write_json(directory / "verify-capture.json", data)
    verification = verify_model(bundle, data, config["max_rms_px"])
    write_json(directory / "verification.json", verification)
    print(f"Verified RMS {verification['rms_px']:.3f}px. Manager unchanged. Results: {directory}")
  elif args.command == "check":
    from devices import Camera, Manager, Tags
    source = Manager(config).camera(config["camera_uid"])
    camera = Camera(config, validate_limits=False)
    stop = Tags(config).collect()
    print(f"Connected; {len(stop['points_2d'])} matched points; "
          f"frame resolution: {stop['resolution']}; position space: {camera.space}")
    if source["resolution"] != stop["resolution"]:
      print(f"WARNING: Manager resolution {source['resolution']} differs from the "
            "calibration stream; use matching approximate pixel intrinsics before fitting.")
  elif args.command.startswith("capture-"):
    write_json(args.output, capture(config, args.command.removeprefix("capture-")))
  elif args.command == "fit-lens":
    write_json(args.output, solve_lens(read_json(args.input)))
  elif args.command == "fit-ptz":
    write_json(args.output, solve_model(read_json(args.input), read_json(args.lens), args.degree))
  elif args.command == "verify":
    bundle = read_json(args.model)
    if (bundle["camera_uid"] != config["camera_uid"] or
        bundle["home"] != config["motion"]["home"] or
        bundle["approach"] != config["motion"]["approach"]):
      raise ValueError("Select the model's camera, home and approach before verification")
    result = verify_model(bundle, capture(config, "ptz"), config["max_rms_px"])
    write_json(args.output, result)
    print(f"Held-out RMS {result['rms_px']:.3f}px over {result['points']} points")
  elif args.command == "apply":
    apply_model(config, read_json(args.model), read_json(args.verification), args.backup)
  return 0


if __name__ == "__main__":
  sys.exit(main())
