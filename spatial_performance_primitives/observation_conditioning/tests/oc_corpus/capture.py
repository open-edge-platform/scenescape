# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Evaluate a scenario with an AmodalReasoner implementation and capture its decisions.

`evaluate_core` works with any implementation that offers the MVP API (the original MVP,
the cleaned reference, the native backend). `capture_decisions` instruments the *original*
MVP's private stages to extract the per-object decision flags; it is how the pre-cleanup
baseline gets its decisions (the cleaned reference emits them natively).
"""

import numpy as np

from .scenarios import FLAGS, UP, sample_queries

VERTICAL_BAND_DEG = (75.0, 115.0)
WALL_DROP_EPS = 0.1


def tensor_mesh(vertices, indices):
  """Service-style mesh: legacy mesh -> tensor mesh (float32 vertices, int64 indices)."""
  import open3d as o3d
  legacy = o3d.geometry.TriangleMesh(
    o3d.utility.Vector3dVector(vertices.astype(np.float64)),
    o3d.utility.Vector3iVector(indices.astype(np.int32)))
  return o3d.t.geometry.TriangleMesh.from_legacy(legacy)


def build_reasoner(scenario, reasoner_cls):
  return reasoner_cls(
    mesh=tensor_mesh(scenario.vertices, scenario.indices), rwc_z_up=UP.copy(),
    camera_intrinsics=scenario.K, camera_extrinsics=scenario.pose,
    width=scenario.width, height=scenario.height, num_layers=scenario.num_layers)


def evaluate_core(scenario, reasoner_cls):
  """Outputs of generate, the depth maps (strided), query and cast_np; all float as-is."""
  reasoner = build_reasoner(scenario, reasoner_cls)
  obs = {key: value.copy() for key, value in scenario.observations.items()}
  with np.errstate(all="ignore"):
    depth, var = reasoner.generate(obs)
    depth_map = reasoner.depth_map
    stride = scenario.map_stride
    points, origins, dirs = sample_queries(scenario)
    q_t, q_n = depth_map.query(points)
    c_n, c_t = depth_map.cast_np(dirs, origins)
  return {
    "out/depth": np.asarray(depth, dtype=np.float64), "out/var": np.asarray(var, dtype=np.float64),
    "map/t_hit": np.ascontiguousarray(depth_map.t_hit_map[::stride, ::stride]),
    "map/normals": np.ascontiguousarray(depth_map.normal_map[::stride, ::stride]),
    "query/points": points, "query/t_hit": np.asarray(q_t), "query/normals": np.asarray(q_n),
    "cast/origins": origins, "cast/dirs": dirs, "cast/t_hit": np.asarray(c_t),
    "cast/normals": np.asarray(c_n),
  }


def capture_decisions(scenario, reasoner_cls):
  """Per-object decisions of the original MVP, via instrumentation of its stages."""
  reasoner = build_reasoner(scenario, reasoner_cls)
  reasoner.debug = True
  calls = {}

  def wrap(name):
    original = getattr(reasoner, name)

    def wrapper(*args, **kwargs):
      result = original(*args, **kwargs)
      calls.setdefault(name, []).append((args, result))
      return result
    setattr(reasoner, name, wrapper)

  stages = ("_get_free_3d_mask", "_get_occlusion_depth", "_get_wall_depth", "_signed_wall_angle",
            "_wall_spectrum", "_total_occlusion", "_update_depth_gaussian")
  for stage in stages:
    wrap(stage)
  obs = {key: value.copy() for key, value in scenario.observations.items()}
  with np.errstate(all="ignore"):
    depth, var = reasoner.generate(obs)
    free3d = calls["_get_free_3d_mask"][0][1]
    occ_pre = calls["_get_occlusion_depth"][0][1]
    wall_pre = calls["_get_wall_depth"][0][1]
    angle = calls["_signed_wall_angle"][0][1]
    spec_wall, _ = calls["_wall_spectrum"][0][1]
    total_occ, _ = calls["_total_occlusion"][0][1]
    update_args = calls["_update_depth_gaussian"][0][0]
    occ_post, wall_post = update_args[2], update_args[3]
    frac = np.asarray(reasoner.trace["total_occ_frac"], dtype=np.float64)

    vertical = (angle >= VERTICAL_BAND_DEG[0]) & (angle < VERTICAL_BAND_DEG[1])
    occluded = np.isfinite(occ_post)
    walled = np.isfinite(wall_post)
    dropped = occluded & walled & (wall_post <= occ_post + WALL_DROP_EPS)
    walled = walled & ~dropped
    lower = np.where(occluded, occ_post, -np.inf)
    upper = np.where(walled, wall_post, np.inf)
    empty = lower >= upper
    updated = ~free3d & (occluded | walled)
  flags = np.zeros(len(depth), dtype=np.uint16)
  for name, mask in (("FREE_3D", free3d), ("OCCLUDED", occluded), ("WALL_VERTICAL", vertical),
                     ("WALL_SPECTRUM", ~vertical & spec_wall), ("TOTAL_OCCLUSION", total_occ),
                     ("WALL_DROPPED", dropped), ("EMPTY_INTERVAL", empty & updated),
                     ("UPDATED", updated)):
    flags |= np.where(mask, FLAGS[name], 0).astype(np.uint16)
  return {
    "dec/flags": flags,
    "dec/signed_angle": np.asarray(angle, dtype=np.float64),
    "dec/total_occ_fraction": frac,
    "dec/occlusion_pre": np.asarray(occ_pre, dtype=np.float64),
    "dec/wall_pre": np.asarray(wall_pre, dtype=np.float64),
    "dec/occlusion_post": np.asarray(occ_post, dtype=np.float64),
    "dec/wall_post": np.asarray(wall_post, dtype=np.float64),
    "dec/_depth": np.asarray(depth, dtype=np.float64), "dec/_var": np.asarray(var, dtype=np.float64),
  }


def native_decisions(scenario, reasoner_cls):
  """Per-object decisions from the implementation's own debug trace (`trace["decisions"]`)."""
  reasoner = build_reasoner(scenario, reasoner_cls)
  reasoner.debug = True
  obs = {key: value.copy() for key, value in scenario.observations.items()}
  with np.errstate(all="ignore"):
    reasoner.generate(obs)
  decisions = reasoner.trace["decisions"]
  return {f"dec/{key}": np.asarray(value) for key, value in decisions.items()}


def reached_flags(flags):
  """Names of the decision flags raised by at least one object."""
  return sorted(name for name, bit in FLAGS.items() if np.any(flags & bit))
