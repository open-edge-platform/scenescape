# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Find a sampled tag-visible rectangle without exceeding operator-approved limits."""

import copy
from itertools import product

import numpy as np

from config import load_config, write_json
from devices import Camera, Manager, Tags, TagCoverageError


def grid(motion, steps):
  """Include the exact home and backlash approach coordinates in the probe grid."""
  result = []
  for i, axis in enumerate(("pan", "tilt")):
    home = motion["home"][i]
    sign = 1 if motion["approach"][i] == "decreasing" else -1
    before = home + sign * motion["approach_offset"][i]
    values = np.linspace(*motion[f"{axis}_range"], steps).tolist()
    result.append(sorted(set([*values, home, before])))
  return result


def select_rectangle(pans, tilts, observations, motion):
  """Choose the largest fully sampled rectangle including home and its approach."""
  usable = {(s["requested_pan"], s["requested_tilt"]) for s in observations if s["usable"]}
  required = []
  for i, values in enumerate((pans, tilts)):
    home = motion["home"][i]
    before = home + (1 if motion["approach"][i] == "decreasing" else -1) * motion["approach_offset"][i]
    required.append(sorted((values.index(home), values.index(before))))
  candidates = []
  for xs, ys in product(_intervals(pans, required[0]), _intervals(tilts, required[1])):
    if all((x, y) in usable for x in xs for y in ys):
      area = (xs[-1] - xs[0]) * (ys[-1] - ys[0])
      candidates.append((area, len(xs) * len(ys), xs, ys))
  if not candidates:
    raise ValueError("No sampled 3x3 tag-visible rectangle includes home and its approach. "
                     "Improve tags, choose another home, or refine the safe discovery grid.")
  _, _, xs, ys = max(candidates)
  return xs, ys


def _intervals(values, required):
  return [values[left:right + 1]
          for left in range(required[0] + 1)
          for right in range(max(left + 2, required[1]), len(values))]


def discover(config, output_dir, steps):
  """Probe a bounded grid, report rejected views and write a separate proposed config."""
  directory = output_dir
  directory.mkdir(mode=0o700)
  Manager(config).camera(config["camera_uid"])
  camera, tags = Camera(config), Tags(config)
  motion = config["motion"]
  pans, tilts = grid(motion, steps)
  observations = []
  resolution = None
  try:
    camera.home()
    # Fail before exploring if the starting reference has no usable tags.
    initial = tags.collect()
    resolution = initial["resolution"]
    for tilt in tilts:
      for pan in pans:
        actual = camera.move(pan, tilt)
        observation = {"requested_pan": pan, "requested_tilt": tilt, "actual": actual}
        try:
          stop = tags.collect()
        except TagCoverageError as error:
          observation.update(usable=False, reason=str(error))
          print(f"pan={pan:.6f} tilt={tilt:.6f}: REJECTED: {error}", flush=True)
        else:
          if stop["resolution"] != resolution:
            raise ValueError("Calibration stream resolution changed during coverage discovery")
          observation.update(usable=True, points=len(stop["points_2d"]))
          print(f"pan={pan:.6f} tilt={tilt:.6f}: {observation['points']} matched points", flush=True)
        observations.append(observation)
  finally:
    try:
      camera.home()
    finally:
      write_json(directory / "coverage.json", {
        "camera_uid": config["camera_uid"], "pans": pans, "tilts": tilts,
        "home": motion["home"], "observations": observations})
  xs, ys = select_rectangle(pans, tilts, observations, motion)
  proposed = copy.deepcopy(config)
  selected = proposed["motion"]
  for i, (axis, values) in enumerate((("pan", xs), ("tilt", ys))):
    home = motion["home"][i]
    selected[f"lens_{axis}"] = values
    offsets = [v - home for v in values]
    selected[f"{axis}_path"] = [0, *offsets, *reversed(offsets), 0]
  path = directory / "camera.discovered.json"
  write_json(path, proposed)
  load_config(path)
  print(f"Review {path} before onboarding. Safe limits are unchanged; "
        "only sampled grid points are proven tag-visible, not the area between them.")
