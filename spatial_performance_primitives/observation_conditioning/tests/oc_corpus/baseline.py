# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Pack scenarios and their results into an OCB1 baseline, and unpack them again."""

import hashlib
import platform
import subprocess
from pathlib import Path

import numpy as np

from .scenarios import FLAGS, Scenario

PACKAGE_DIR = Path(__file__).resolve().parents[2]
ORIGINAL_COMMIT = "5cc7f08a82017511d9cd7394dc1a273d4b506adf"
ORIGINAL_SOURCES = (
  "spatial_performance_primitives/observation_conditioning/__init__.py",
  "spatial_performance_primitives/observation_conditioning/amodal_reasoner.py",
  "spatial_performance_primitives/observation_conditioning/constants.py",
  "spatial_performance_primitives/observation_conditioning/intersection_map.py",
)
OBSERVATION_KEYS = ("mu", "Sigma", "ray", "depth_est", "depth_sigma", "depth_lo", "depth_hi",
                    "score", "edge_valid")
# Flags that cannot be raised through generate() (see implementation.md).
UNREACHABLE_FLAGS = ("EMPTY_INTERVAL",)


def sha256(data):
  return hashlib.sha256(data).hexdigest()


def git_show(commit, path):
  """Bytes of `path` at `commit`, or None when git or the commit is unavailable."""
  try:
    return subprocess.run(
      ["git", "-c", "safe.directory=*", "show", f"{commit}:{path}"], cwd=PACKAGE_DIR,
      check=True, capture_output=True).stdout
  except (OSError, subprocess.CalledProcessError):
    return None


def environment_meta():
  import numpy
  import open3d
  import scipy
  return {
    "python": platform.python_version(), "numpy": numpy.__version__, "scipy": scipy.__version__,
    "open3d": open3d.__version__, "machine": platform.machine(),
  }


def pack_scenario(scenario, core, decisions):
  """Arrays of one scenario; the terrain mesh is stored once under its shared mesh id."""
  mesh_id = scenario.extra.get("mesh_id", scenario.name)
  arrays = {
    f"mesh/{mesh_id}/vertices": scenario.vertices, f"mesh/{mesh_id}/indices": scenario.indices,
  }
  prefix = f"s/{scenario.name}/"
  arrays[prefix + "cam/K"] = scenario.K
  arrays[prefix + "cam/pose"] = scenario.pose
  arrays[prefix + "cam/size"] = np.array([scenario.width, scenario.height], dtype=np.uint32)
  for key in OBSERVATION_KEYS:
    arrays[prefix + f"obs/{key}"] = scenario.observations[key]
  for key, value in core.items():
    arrays[prefix + key] = value
  for key, value in decisions.items():
    if not key.startswith("dec/_"):
      arrays[prefix + key] = value
  return arrays


def scenario_meta(scenario, reached):
  return {
    "description": scenario.description, "mesh_id": scenario.extra.get("mesh_id", scenario.name),
    "num_layers": scenario.num_layers, "map_stride": scenario.map_stride, "seed": scenario.seed,
    "expect": list(scenario.expect), "reached": list(reached), "objects": len(scenario.observations["depth_est"]),
  }


def source_meta():
  files = {}
  for path in ORIGINAL_SOURCES:
    data = git_show(ORIGINAL_COMMIT, path)
    if data is None:
      raise RuntimeError(f"cannot read {path} at {ORIGINAL_COMMIT}; run inside the repository")
    files[path] = sha256(data)
  return {"commit": ORIGINAL_COMMIT, "files": files}


def baseline_meta(scenarios_meta):
  return {
    "format": "OCB1", "kind": "mvp-original", "source": source_meta(),
    "environment": environment_meta(), "flags": FLAGS, "unreachable_flags": list(UNREACHABLE_FLAGS),
    "scenarios": scenarios_meta,
  }


def load_scenario(arrays, meta, name):
  """Rebuild a Scenario (inputs only) from a baseline."""
  info = meta["scenarios"][name]
  prefix = f"s/{name}/"
  size = arrays[prefix + "cam/size"]
  mesh_id = info["mesh_id"]
  return Scenario(
    name, info["description"], arrays[f"mesh/{mesh_id}/vertices"],
    arrays[f"mesh/{mesh_id}/indices"], arrays[prefix + "cam/K"], arrays[prefix + "cam/pose"],
    int(size[0]), int(size[1]), {key: arrays[prefix + f"obs/{key}"] for key in OBSERVATION_KEYS},
    num_layers=info["num_layers"], map_stride=info["map_stride"], expect=tuple(info["expect"]),
    seed=info["seed"], extra={"mesh_id": mesh_id})


def stored_results(arrays, name):
  """The recorded outputs of a scenario, keyed like capture.evaluate_core / capture_decisions."""
  prefix = f"s/{name}/"
  return {key[len(prefix):]: value for key, value in arrays.items()
          if key.startswith(prefix) and key.split("/")[2] in ("out", "map", "query", "cast", "dec")}
