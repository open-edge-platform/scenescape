# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the shared track helpers."""

import argparse
import sys
from pathlib import Path

import pytest

# Add evaluation root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# pylint: disable-next=wrong-import-position
from utils.tracks import (  # noqa: E402
  MIN_OVERLAP_FRAMES,
  add_space_arguments,
  match_tracks,
  position_distance,
)


def _track(x, y, frames=range(MIN_OVERLAP_FRAMES)):
  return {frame: (x, y) for frame in frames}


def _track_3d(x, y, z, frames=range(MIN_OVERLAP_FRAMES)):
  return {frame: (x, y, z) for frame in frames}


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


def test_distance_over_the_axes_of_a_space():
  """x, y and z by default; the plane or the height on request."""
  first, second = (0.0, 0.0, 0.0), (3.0, 4.0, 12.0)

  assert position_distance(first, second) == pytest.approx(13.0)
  assert position_distance(first, second, "xy") == pytest.approx(5.0)
  assert position_distance(first, second, "z") == pytest.approx(12.0)


def test_distance_skips_missing_z():
  """Planar positions are compared in the plane; the height needs a z on both sides."""
  assert position_distance((0.0, 0.0), (3.0, 4.0, 12.0)) == pytest.approx(5.0)
  with pytest.raises(ValueError, match="needs positions with a z"):
    position_distance((0.0, 0.0), (3.0, 4.0, 12.0), "z")


def test_rejects_unknown_space():
  """Only xyz, xy and z exist."""
  with pytest.raises(ValueError, match="space must be one of"):
    position_distance((0.0, 0.0), (1.0, 1.0), "xz")
  with pytest.raises(ValueError, match="space must be one of"):
    match_tracks({}, {}, "xz")


def test_matching_follows_the_space():
  """Tracks that cross in the plane but differ in height are paired by all axes or by the height."""
  outputs = {"a": _track_3d(0.0, 0.0, 0.0), "b": _track_3d(1.0, 0.0, 5.0)}
  ground_truth = {"1": _track_3d(1.0, 0.0, 0.0), "2": _track_3d(0.0, 0.0, 5.0)}

  assert sorted(match_tracks(outputs, ground_truth)) == [("a", "1"), ("b", "2")]
  assert sorted(match_tracks(outputs, ground_truth, "xy")) == [("a", "2"), ("b", "1")]
  assert sorted(match_tracks(outputs, ground_truth, "z")) == [("a", "1"), ("b", "2")]


def test_space_arguments():
  """3D by default, --xy-only and --z-only select the plane or the height, not both."""
  parser = argparse.ArgumentParser()
  add_space_arguments(parser)

  assert parser.parse_args([]).space == "xyz"
  assert parser.parse_args(["--xy-only"]).space == "xy"
  assert parser.parse_args(["--z-only"]).space == "z"
  with pytest.raises(SystemExit):
    parser.parse_args(["--xy-only", "--z-only"])
