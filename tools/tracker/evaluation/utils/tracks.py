# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared track helpers for tracker evaluation."""

import argparse
import math
from typing import Dict, List, Tuple

import numpy as np
from scipy.optimize import linear_sum_assignment

# Which position axes a measure uses: all three (default), the ground plane or the height.
SPACES = ("xyz", "xy", "z")
SPACE_AXES = {"xyz": (0, 1, 2), "xy": (0, 1), "z": (2,)}

# Minimum number of overlapping frames required for a valid track match.
# Pairs with fewer overlapping frames receive infinite cost and are excluded.
MIN_OVERLAP_FRAMES = 10

# Large finite sentinel substituted for infinite cost entries so that
# ``linear_sum_assignment`` always has a feasible solution.  Matched pairs that
# resolve to this sentinel are discarded after solving.
_INFEASIBLE_SENTINEL = 1e9


def space_axes(space: str) -> Tuple[int, ...]:
  """Position indices (x=0, y=1, z=2) used by `space`; ValueError for an unknown space."""
  if space not in SPACE_AXES:
    raise ValueError(f"space must be one of {', '.join(SPACES)}, not {space!r}")
  return SPACE_AXES[space]


def present_axes(space: str, size: int) -> List[int]:
  """Axes of `space` that positions with `size` coordinates have.

  Planar (x, y) positions skip z, so "xyz" is the planar measure; "z" needs a z (ValueError).
  """
  axes = [axis for axis in space_axes(space) if axis < size]
  if not axes:
    raise ValueError(f"space {space!r} needs positions with a z")
  return axes


def position_distance(first, second, space: str = "xyz") -> float:
  """Euclidean distance of two positions over the axes of `space`.

  Positions are (x, y) or (x, y, z); axes that one of them lacks are skipped, see `present_axes`.
  """
  axes = present_axes(space, min(len(first), len(second)))
  return math.sqrt(sum((first[axis] - second[axis]) ** 2 for axis in axes))


def add_space_arguments(parser: argparse.ArgumentParser) -> None:
  """Add --xy-only and --z-only; the namespace gets `space`, "xyz" by default."""
  group = parser.add_mutually_exclusive_group()
  group.add_argument("--xy-only", dest="space", action="store_const", const="xy",
                     help="measure the ground plane (x, y) only; default is x, y and z")
  group.add_argument("--z-only", dest="space", action="store_const", const="z",
                     help="measure the height (z) only; default is x, y and z")
  parser.set_defaults(space="xyz")


def match_tracks(
  output_tracks: Dict[str, Dict[int, tuple]],
  gt_tracks: Dict[str, Dict[int, tuple]],
  space: str = "xyz",
) -> List[Tuple[str, str]]:
  """Bipartite assignment minimizing mean Euclidean distance.

  Args:
    output_tracks: {track_id: {frame_index: (x, y, z)}} of the tracker output,
      e.g. from ``utils.timeline.ingest_frames``; (x, y) positions are accepted too.
    gt_tracks: Ground-truth tracks in the same form.
    space: Axes of the distance, see `position_distance`.

  Returns:
    List of (output_track_id, gt_track_id) tuples.
  """
  space_axes(space)
  output_ids = list(output_tracks.keys())
  gt_ids = list(gt_tracks.keys())
  n = len(output_ids)
  m = len(gt_ids)

  if n == 0 or m == 0:
    return []

  cost = np.full((n, m), np.inf)
  for i, oid in enumerate(output_ids):
    out_frames = set(output_tracks[oid])
    for j, gid in enumerate(gt_ids):
      overlap = out_frames & set(gt_tracks[gid])
      if len(overlap) >= MIN_OVERLAP_FRAMES:
        cost[i, j] = np.mean([
          position_distance(output_tracks[oid][f], gt_tracks[gid][f], space) for f in overlap
        ])

  if not np.any(np.isfinite(cost)):
    return []

  # ``linear_sum_assignment`` raises "cost matrix is infeasible" when the
  # finite entries do not admit a complete matching of size min(n, m).  This
  # happens with large, sparse track populations where most output/GT pairs
  # never share frames.  Solve on a matrix where infinities are replaced by a
  # large finite sentinel, then discard any matched pair whose original cost
  # was non-finite.
  solve_cost = np.where(np.isfinite(cost), cost, _INFEASIBLE_SENTINEL)
  row_ind, col_ind = linear_sum_assignment(solve_cost)
  matches = []
  for r, c in zip(row_ind, col_ind):
    if np.isfinite(cost[r, c]):
      matches.append((output_ids[r], gt_ids[c]))
  return matches
