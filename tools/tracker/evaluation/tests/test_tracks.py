# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the shared track helpers."""

import sys
from pathlib import Path

# Add evaluation root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# pylint: disable-next=wrong-import-position
from utils.tracks import MIN_OVERLAP_FRAMES, match_tracks  # noqa: E402


def _track(x, y, frames=range(MIN_OVERLAP_FRAMES)):
  return {frame: (x, y) for frame in frames}


def test_matches_closest_pairs():
  """Each output track gets the ground-truth track with the lowest mean distance."""
  outputs = {"a": _track(0.1, 0.0), "b": _track(5.0, 0.2)}
  ground_truth = {"1": _track(5.0, 0.0), "2": _track(0.0, 0.0)}

  assert sorted(match_tracks(outputs, ground_truth)) == [("a", "2"), ("b", "1")]


def test_requires_minimum_overlap():
  """Pairs sharing fewer than MIN_OVERLAP_FRAMES frames are not matched."""
  short = _track(0.0, 0.0, range(MIN_OVERLAP_FRAMES - 1))

  assert not match_tracks({"a": short}, {"1": _track(0.0, 0.0)})
  assert match_tracks({"a": _track(0.0, 0.0)}, {"1": _track(0.0, 0.0)}) == [("a", "1")]


def test_unmatchable_tracks_stay_unmatched():
  """Tracks without any valid partner are dropped instead of being force-assigned."""
  outputs = {"a": _track(0.0, 0.0), "late": _track(0.0, 0.0, range(100, 120))}
  ground_truth = {"1": _track(0.0, 0.0), "2": _track(9.0, 9.0)}

  assert match_tracks(outputs, ground_truth) == [("a", "1")]


def test_empty_inputs():
  """No tracks on either side gives no matches."""
  assert not match_tracks({}, {"1": _track(0.0, 0.0)})
  assert not match_tracks({"a": _track(0.0, 0.0)}, {})
