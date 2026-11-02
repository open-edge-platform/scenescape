# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Compare two sets of robot-vision scenario recordings, e.g. before and after a change.

Usage (from tools/tracker/evaluation):
  python visualization/compare_scenarios.py BEFORE_DIR AFTER_DIR [--warm-up SECONDS] [--fps FPS]
                                            [--rel-tol 0.05] [--abs-tol 0.01]
                                            [--metrics NAME,...] [--fail-on-worse]
                                            [--xy-only | --z-only]

BEFORE_DIR and AFTER_DIR are roots of recordings, $RV_SCENARIO_DIR/<Suite>.<Test>/<case>/, made
by two builds. Every directory below a root that holds groundtruth.jsonl is a scenario, named by
its path relative to the root. Scenarios present in both roots are compared; the others are
only listed. Only groundtruth.jsonl and tracks.jsonl are read, so builds with different filter
state sizes can be compared.

Per scenario each track is paired with a ground-truth object as in plot_scenario.py
(utils.tracks.match_tracks, by x, y and z distance; --xy-only: the ground plane, --z-only: the
height) and its rows are matched to the ground truth in time. Rows before the
warm-up and rows without ground truth are ignored. Metrics, all errors (lower is better):

- horizontal_rms, horizontal_max: distance in x/y only [m].
- vertical_rms, vertical_max: |z - z_gt| only [m].
- final_speed_error: |hypot(vx, vy) - speed_gt| at the last row of each pair, mean over pairs [m/s].
- final_vz_error: |vz - vz_gt| at the last row of each pair, mean over pairs [m/s].

A value is marked WORSE when after > before * (1 + rel_tol) + abs_tol, or when it was computed before
but is NaN after (the track or the ground truth is gone); it is marked better when
after < before * (1 - rel_tol) - abs_tol. With --fail-on-worse the exit code is 1 if any
value is WORSE. final_speed_error is a horizontal speed; the recorder's truth speed is too.
"""

import argparse
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pylint: disable=wrong-import-position
from utils.tracks import add_space_arguments  # noqa: E402
from visualization.scenario_data import (  # noqa: E402
  GROUND_TRUTH_FILE,
  Scenario,
  align_track_to_truth,
  frame_rate,
  load_scenario,
  match_tracks_to_truth,
)
# pylint: enable=wrong-import-position

METRICS = ["horizontal_rms", "horizontal_max", "vertical_rms", "vertical_max",
           "final_speed_error", "final_vz_error"]
WORSE = "WORSE"
BETTER = "better"
DEFAULT_WARM_UP = 2.0  # [s]
DEFAULT_REL_TOL = 0.05
DEFAULT_ABS_TOL = 0.01
TABLE_COLUMNS = ["metric", "before", "after", "delta", "verdict"]


def _pair_frames(scenario: Scenario, warm_up: float, fps: Optional[float],
                 space: str = "xyz") -> List[pd.DataFrame]:
  """Aligned rows of every paired track after the warm-up that have ground truth."""
  tolerance = 0.5 / (frame_rate(scenario.ground_truth) or 1.0)
  frames = []
  for track_id, object_id in match_tracks_to_truth(scenario, fps, space):
    rows = align_track_to_truth(scenario, track_id, object_id, tolerance)
    rows = rows[(rows["t"] >= warm_up) & rows["x_gt"].notna()]
    if not rows.empty:
      frames.append(rows)
  return frames


def _rms(values: pd.Series) -> float:
  return float(np.sqrt(np.mean(np.square(values)))) if len(values) else math.nan


def _maximum(values: pd.Series) -> float:
  return float(values.max()) if len(values) else math.nan


def _final_error(frames: List[pd.DataFrame], column: str, estimate) -> float:
  """Mean over pairs of |estimate(last row) - <column>_gt at that row|; NaN ignored."""
  errors = [abs(estimate(frame.iloc[-1]) - frame.iloc[-1][column]) for frame in frames]
  errors = [error for error in errors if not math.isnan(error)]
  return float(np.mean(errors)) if errors else math.nan


def scenario_metrics(directory, warm_up: float = DEFAULT_WARM_UP,
                     fps: Optional[float] = None, space: str = "xyz") -> Dict[str, float]:
  """Accuracy metrics of one recording; NaN where nothing can be computed.

  Tracks are paired with ground-truth objects as in plot_scenario.py, by the distance over the
  axes of `space` ("xyz", "xy" or "z"); the metrics themselves are per plane or height. `warm_up`
  seconds from the first timestamp are skipped. `fps` defaults to the ground-truth frame rate.
  `tracks` is the number of paired tracks.
  """
  frames = _pair_frames(load_scenario(directory), warm_up, fps, space)
  metrics = {name: math.nan for name in METRICS}
  metrics["tracks"] = float(len(frames))
  if not frames:
    return metrics
  rows = pd.concat(frames, ignore_index=True)
  horizontal = np.hypot(rows["x"] - rows["x_gt"], rows["y"] - rows["y_gt"])
  vertical = (rows["z"] - rows["z_gt"]).abs().dropna()
  metrics.update(horizontal_rms=_rms(horizontal), horizontal_max=_maximum(horizontal),
                 vertical_rms=_rms(vertical), vertical_max=_maximum(vertical))
  metrics["final_speed_error"] = _final_error(
    frames, "speed_gt", lambda row: math.hypot(row["vx"], row["vy"]))
  metrics["final_vz_error"] = _final_error(frames, "vz_gt", lambda row: row["vz"])
  return metrics


def find_scenarios(root) -> Dict[str, Path]:
  """Every directory below `root`, root included, with a groundtruth.jsonl, by relative path."""
  root = Path(root)
  found = {}
  for ground_truth in sorted(root.rglob(GROUND_TRUTH_FILE)):
    directory = ground_truth.parent
    found[directory.relative_to(root).as_posix()] = directory
  return found


def compare_recordings(before, after, warm_up: float = DEFAULT_WARM_UP,
                       fps: Optional[float] = None, space: str = "xyz") -> pd.DataFrame:
  """Metrics of the scenarios present in both roots.

  One row per scenario and metric, with the columns scenario, metric, before, after and
  delta (after - before). `space` selects the axes of the track pairing.
  """
  before_scenarios, after_scenarios = find_scenarios(before), find_scenarios(after)
  rows = []
  for name in sorted(before_scenarios.keys() & after_scenarios.keys()):
    old = scenario_metrics(before_scenarios[name], warm_up, fps, space)
    new = scenario_metrics(after_scenarios[name], warm_up, fps, space)
    for metric in METRICS:
      rows.append({"scenario": name, "metric": metric, "before": old[metric],
                   "after": new[metric], "delta": new[metric] - old[metric]})
  return pd.DataFrame(rows, columns=["scenario", "metric", "before", "after", "delta"])


def verdict(before: float, after: float, rel_tol: float, abs_tol: float) -> str:
  """WORSE, better or an empty string; errors only, so lower is better.

  A value that was computed before but is NaN after (no track or no ground truth left) is WORSE;
  NaN before, or on both sides, is not judged.
  """
  if math.isnan(after):
    return "" if math.isnan(before) else WORSE
  if math.isnan(before):
    return ""
  if after > before * (1 + rel_tol) + abs_tol:
    return WORSE
  if after < before * (1 - rel_tol) - abs_tol:
    return BETTER
  return ""


def _format_table(rows: List[List[str]]) -> List[str]:
  widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
  lines = []
  for row in rows:
    cells = [cell.ljust(widths[0]) if i == 0 else cell.rjust(widths[i])
             for i, cell in enumerate(row[:-1])]
    lines.append("  ".join(cells + [row[-1]]).rstrip())
  return lines


def _scenario_table(rows: pd.DataFrame, rel_tol: float, abs_tol: float) -> List[List[str]]:
  table = [TABLE_COLUMNS]
  for row in rows.itertuples():
    mark = verdict(row.before, row.after, rel_tol, abs_tol)
    table.append([row.metric, f"{row.before:.4f}", f"{row.after:.4f}", f"{row.delta:+.4f}", mark])
  return table


def _print_only_in(label: str, names: Sequence[str]) -> None:
  if names:
    print(f"\nOnly in {label} ({len(names)}):")
    for name in names:
      print(f"  {name}")


def _build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description="Compare the tracking accuracy of two sets of scenario recordings.")
  parser.add_argument("before", type=Path, help="root of the recordings made before")
  parser.add_argument("after", type=Path, help="root of the recordings made after")
  parser.add_argument("--warm-up", type=float, default=DEFAULT_WARM_UP, metavar="SECONDS",
                      help="seconds ignored at the start, default %(default)s")
  parser.add_argument("--fps", type=float, default=None,
                      help="frame rate for pairing tracks, default the ground-truth rate")
  parser.add_argument("--rel-tol", type=float, default=DEFAULT_REL_TOL,
                      help="relative tolerance of the verdict, default %(default)s")
  parser.add_argument("--abs-tol", type=float, default=DEFAULT_ABS_TOL,
                      help="absolute tolerance of the verdict, default %(default)s")
  parser.add_argument("--metrics", default=",".join(METRICS), metavar="A,B",
                      help="metrics to show, default all: %(default)s")
  parser.add_argument("--fail-on-worse", action="store_true",
                      help="exit with 1 if any metric is WORSE")
  add_space_arguments(parser)
  return parser


def _parse_args(parser: argparse.ArgumentParser, argv: Optional[Sequence[str]]
                ) -> argparse.Namespace:
  args = parser.parse_args(argv)
  for root in (args.before, args.after):
    if not root.is_dir():
      parser.error(f"not a directory: {root}")
  args.metrics = [name for name in args.metrics.split(",") if name]
  unknown = [name for name in args.metrics if name not in METRICS]
  if unknown or not args.metrics:
    parser.error(f"unknown metrics {unknown}; choose from {', '.join(METRICS)}")
  return args


def main(argv: Optional[Sequence[str]] = None) -> int:
  """Print the comparison; return 1 with --fail-on-worse if a metric got WORSE, else 0."""
  parser = _build_parser()
  args = _parse_args(parser, argv)
  before, after = find_scenarios(args.before), find_scenarios(args.after)
  if not before.keys() & after.keys():
    parser.error(f"no scenario in common: {len(before)} in {args.before}, {len(after)} in "
                 f"{args.after}; a scenario is a directory with {GROUND_TRUTH_FILE}, matched by "
                 "its path relative to the root")
  comparison = compare_recordings(args.before, args.after, args.warm_up, args.fps, args.space)
  comparison = comparison[comparison["metric"].isin(args.metrics)]
  worse = better = scenarios_worse = 0
  for name, rows in comparison.groupby("scenario", sort=True):
    table = _scenario_table(rows, args.rel_tol, args.abs_tol)
    marks = [row[-1] for row in table[1:]]
    worse += marks.count(WORSE)
    better += marks.count(BETTER)
    scenarios_worse += WORSE in marks
    print(f"\n{name}")
    print("\n".join("  " + line for line in _format_table(table)))
    if rows[["before", "after"]].isna().all(axis=None):
      print("  no values: shorter than --warm-up, or no track paired with the ground truth?")
  _print_only_in("before", sorted(before.keys() - after.keys()))
  _print_only_in("after", sorted(after.keys() - before.keys()))
  print(f"\ncompared {comparison['scenario'].nunique()} scenarios: {worse} values WORSE "
        f"(in {scenarios_worse} scenarios), {better} better")
  return 1 if args.fail_on_worse and worse else 0


if __name__ == "__main__":
  sys.exit(main())
