# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared track helpers for tracker evaluation."""

import math
from typing import Dict, List, Tuple

import numpy as np
from scipy.optimize import linear_sum_assignment

# Minimum number of overlapping frames required for a valid track match.
# Pairs with fewer overlapping frames receive infinite cost and are excluded.
MIN_OVERLAP_FRAMES = 10

# Large finite sentinel substituted for infinite cost entries so that
# ``linear_sum_assignment`` always has a feasible solution.  Matched pairs that
# resolve to this sentinel are discarded after solving.
_INFEASIBLE_SENTINEL = 1e9


def match_tracks(
  output_tracks: Dict[str, Dict[int, tuple]],
  gt_tracks: Dict[str, Dict[int, tuple]],
) -> List[Tuple[str, str]]:
  """Bipartite assignment minimizing mean Euclidean distance.

  Args:
    output_tracks: {track_id: {frame_index: (x, y)}} of the tracker output,
      e.g. from ``utils.timeline.ingest_frames``.
    gt_tracks: Ground-truth tracks in the same form.

  Returns:
    List of (output_track_id, gt_track_id) tuples.
  """
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
        dists = []
        for f in overlap:
          ox, oy = output_tracks[oid][f]
          gx, gy = gt_tracks[gid][f]
          dists.append(math.sqrt((ox - gx) ** 2 + (oy - gy) ** 2))
        cost[i, j] = np.mean(dists)

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
