# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Plot a robot-vision scenario recording, or real tracker output, as PNG files.

Usage (from tools/tracker/evaluation):
  python visualization/plot_scenario.py <dir> [<dir> ...] [--output DIR] [--plots NAME,...]
                                        [--fps FPS]

Writes one PNG per plot to <dir>/plots/ by default, with one colour per track.
Plots whose data is missing are skipped, e.g. the estimator plots for real
tracker output. Tracks are paired with ground-truth objects by
utils.tracks.match_tracks. The trackeval plot runs TrackEval, writing its files
to <dir>/metrics/; with several directories their TrackEval results are also
compared in <common parent>/plots/trackeval_comparison.png; directories without
scenario files are then skipped.
"""

import argparse
import contextlib
import io
import os
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402 pylint: disable=wrong-import-position
import numpy as np  # noqa: E402 pylint: disable=wrong-import-position
import pandas as pd  # noqa: E402 pylint: disable=wrong-import-position

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pylint: disable=wrong-import-position
from evaluators.trackeval_evaluator import (  # noqa: E402
  ZERO_DISTANCE,
  TrackEvalEvaluator,
  ground_truth_fps,
)
from utils.format_converters import stream_jsonl  # noqa: E402
from visualization.scenario_data import (  # noqa: E402
  GROUND_TRUTH_FILE,
  TRACKS_FILE,
  Scenario,
  align_track_to_truth,
  frame_rate,
  load_scenario,
  match_tracks_to_truth,
)
# pylint: enable=wrong-import-position

Pairs = Dict[str, Optional[str]]  # track_id -> matched object_id or None

TRUTH_STYLE = {"linestyle": "--", "linewidth": 1.0}
DETECTION_STYLE = {"marker": ".", "linestyle": "none", "markersize": 3, "alpha": 0.5}
MAX_LEGEND_ENTRIES = 12
SPEED_FOR_DIRECTION = 1e-3  # [m/s] below this the along-track direction is undefined
TRACKEVAL_ALPHAS = np.arange(5, 100, 5)  # TrackEval similarity thresholds [%]
TRACKEVAL_SCORES = {"HOTA": "HOTA___AUC", "MOTA": "MOTA", "IDF1": "IDF1", "LocA": "LocA___AUC"}


def label(item_id: str) -> str:
  """Short display label; UUIDs are cut to 8 characters."""
  return item_id[:8] if len(item_id) > 12 else item_id


def track_color(pairs: Pairs, track_id: str) -> str:
  """Colour of a track by its position in `pairs`, so it is the same in every plot and video."""
  cycle = plt.rcParams["axes.prop_cycle"].by_key()["color"]
  order = list(pairs)
  index = order.index(track_id) if track_id in order else len(order)
  return cycle[index % len(cycle)]


def pair_tracks(scenario: Scenario, fps: Optional[float] = None) -> Pairs:
  """Every track id, in sorted order, with its matched ground-truth object id or None."""
  pairs: Pairs = {track_id: None for track_id in scenario.track_ids}
  pairs.update(dict(match_tracks_to_truth(scenario, fps)))
  return pairs


def position_errors(aligned: pd.DataFrame) -> pd.DataFrame:
  """Position error of a track against the ground truth, total and in the truth's frame.

  Args:
    aligned: Output of align_track_to_truth. The direction of motion comes from
      the truth velocity, or from truth positions when the velocity is missing.

  Returns:
    Columns t, total, along, cross; along and cross are NaN below SPEED_FOR_DIRECTION.
  """
  ex = (aligned["x"] - aligned["x_gt"]).to_numpy()
  ey = (aligned["y"] - aligned["y_gt"]).to_numpy()
  vx = np.array(aligned["vx_gt"], dtype=float)
  vy = np.array(aligned["vy_gt"], dtype=float)
  missing = np.isnan(vx) | np.isnan(vy)
  if missing.any():
    valid = aligned["x_gt"].notna().to_numpy()
    if valid.sum() >= 2:
      t = aligned["t"].to_numpy()[valid]
      vx[missing & valid] = np.gradient(aligned["x_gt"].to_numpy()[valid], t)[missing[valid]]
      vy[missing & valid] = np.gradient(aligned["y_gt"].to_numpy()[valid], t)[missing[valid]]
  speed = np.hypot(vx, vy)
  with np.errstate(invalid="ignore", divide="ignore"):
    ux = np.where(speed > SPEED_FOR_DIRECTION, vx / speed, np.nan)
    uy = np.where(speed > SPEED_FOR_DIRECTION, vy / speed, np.nan)
  return pd.DataFrame({
    "t": aligned["t"].to_numpy(),
    "total": np.hypot(ex, ey),
    "along": ex * ux + ey * uy,
    "cross": -ex * uy + ey * ux,
    "ux": ux,
    "uy": uy,
  })


def plot_trajectory(scenario: Scenario, pairs: Pairs) -> Optional[plt.Figure]:
  """Top-down view: ground truth, detections and estimates."""
  if scenario.ground_truth.empty and scenario.detections.empty and scenario.tracks.empty:
    return None
  fig, ax = plt.subplots(figsize=(9, 8))
  for object_id, truth in scenario.ground_truth.groupby("object_id"):
    ax.plot(truth["x"], truth["y"], color="black", label=f"truth {label(object_id)}", **TRUTH_STYLE)
    ax.plot(truth["x"].iloc[0], truth["y"].iloc[0], "o", color="black", markersize=4)
  for sensor_id, detections in scenario.detections.groupby("sensor_id"):
    ax.plot(detections["x"], detections["y"], color="gray", label=f"detections {sensor_id}",
            **DETECTION_STYLE)
  for track_id, track in _tracks(scenario, pairs):
    color = track_color(pairs, track_id)
    ax.plot(track["x"], track["y"], color=color, linewidth=1.5, label=f"track {label(track_id)}")
    ax.plot(track["x"].iloc[:1], track["y"].iloc[:1], "x", color=color)
  ax.set_aspect("equal", adjustable="datalim")
  _finish(ax, "x [m]", "y [m]")
  ax.set_title(_title(scenario, "Trajectory"))
  return fig


def plot_position_error(scenario: Scenario, pairs: Pairs) -> Optional[plt.Figure]:
  """Position error against the matched truth, with a ±2σ band from the estimator covariance."""
  matched = {track_id: object_id for track_id, object_id in pairs.items() if object_id}
  if not matched:
    return None
  tolerance = 0.5 / (frame_rate(scenario.ground_truth) or 1.0)
  fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
  for track_id, object_id in matched.items():
    color = track_color(pairs, track_id)
    errors = position_errors(align_track_to_truth(scenario, track_id, object_id, tolerance))
    name = f"track {label(track_id)}"
    axes[0].plot(errors["t"], errors["total"], color=color, label=name)
    axes[1].plot(errors["t"], errors["along"], color=color, label=name)
    axes[2].plot(errors["t"], errors["cross"], color=color, label=name)
    sigma = _position_sigma(scenario, track_id, errors, tolerance)
    if sigma is not None:
      for ax, column in ((axes[1], "along"), (axes[2], "cross")):
        ax.fill_between(errors["t"], -2 * sigma[column], 2 * sigma[column], color=color, alpha=0.15,
                        linewidth=0, label=f"±2σ {label(track_id)}")
  for ax, ylabel in zip(axes, ("total [m]", "along-track [m]", "cross-track [m]")):
    _finish(ax, None, ylabel)
  axes[1].axhline(0.0, color="black", linewidth=0.5)
  axes[2].axhline(0.0, color="black", linewidth=0.5)
  axes[-1].set_xlabel("t [s]")
  axes[0].set_title(_title(scenario, "Position error (estimate - truth)"))
  return fig


def plot_speed_yaw(scenario: Scenario, pairs: Pairs) -> Optional[plt.Figure]:
  """Speed, yaw and yaw rate: estimate vs truth."""
  if scenario.tracks.empty:
    return None
  has_yaw_rate = bool(scenario.estimator) or scenario.ground_truth["yaw_rate"].notna().any()
  rows = 3 if has_yaw_rate else 2
  fig, axes = plt.subplots(rows, 1, figsize=(10, 3 * rows + 1), sharex=True)
  for track_id, track in _tracks(scenario, pairs):
    color = track_color(pairs, track_id)
    truth = _truth(scenario, pairs.get(track_id))
    name = label(track_id)
    axes[0].plot(track["t"], np.hypot(track["vx"], track["vy"]), color=color, label=f"track {name}")
    axes[1].plot(track["t"], np.unwrap(track["yaw"].fillna(0.0)), color=color,
                 label=f"track {name}")
    if truth is not None:
      axes[0].plot(truth["t"], truth["speed"], color=color, label=f"truth {name}", **TRUTH_STYLE)
      if truth["yaw"].notna().any():
        axes[1].plot(truth["t"], np.unwrap(truth["yaw"].fillna(0.0)), color=color,
                     label=f"truth {name}", **TRUTH_STYLE)
      detections = _detections(scenario, pairs.get(track_id))
      if detections["yaw"].notna().any():
        axes[1].plot(detections["t"], _near(detections["t"], detections["yaw"], track), color=color,
                     label=f"detections {name}", **DETECTION_STYLE)
    if has_yaw_rate:
      trace = scenario.estimator.get(track_id)
      if trace is not None:
        axes[2].plot(trace.t, trace.state[:, trace.state_index("yaw_rate")], color=color,
                     label=f"track {name}")
      if truth is not None and truth["yaw_rate"].notna().any():
        axes[2].plot(truth["t"], truth["yaw_rate"], color=color, label=f"truth {name}",
                     **TRUTH_STYLE)
  for ax, ylabel in zip(axes, ("speed [m/s]", "yaw [rad]", "yaw rate [rad/s]")):
    _finish(ax, None, ylabel)
  axes[-1].set_xlabel("t [s]")
  axes[0].set_title(_title(scenario, "Speed and yaw"))
  return fig


def plot_size(scenario: Scenario, pairs: Pairs) -> Optional[plt.Figure]:
  """Length, width and height: estimate vs truth vs detections."""
  if scenario.tracks.empty:
    return None
  fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
  for track_id, track in _tracks(scenario, pairs):
    color = track_color(pairs, track_id)
    truth = _truth(scenario, pairs.get(track_id))
    detections = _detections(scenario, pairs.get(track_id))
    name = label(track_id)
    for ax, column in zip(axes, ("length", "width", "height")):
      ax.plot(track["t"], track[column], color=color, label=f"track {name}")
      if truth is not None and truth[column].notna().any():
        ax.plot(truth["t"], truth[column], color=color, label=f"truth {name}", **TRUTH_STYLE)
      if detections[column].notna().any():
        ax.plot(detections["t"], detections[column], color=color, label=f"detections {name}",
                **DETECTION_STYLE)
  for ax, ylabel in zip(axes, ("length [m]", "width [m]", "height [m]")):
    _finish(ax, None, ylabel)
  axes[-1].set_xlabel("t [s]")
  axes[0].set_title(_title(scenario, "Size"))
  return fig


def plot_model_probability(scenario: Scenario, pairs: Pairs) -> Optional[plt.Figure]:
  """Motion model probabilities, one panel per track."""
  del pairs
  if not scenario.estimator:
    return None
  traces = sorted(scenario.estimator.items())
  fig, axes = plt.subplots(len(traces), 1, figsize=(10, 2.5 * len(traces) + 1), sharex=True,
                           squeeze=False)
  for ax, (track_id, trace) in zip(axes[:, 0], traces):
    models = trace.motion_models or [str(i) for i in range(trace.model_probability.shape[1])]
    for column, model in enumerate(models):
      ax.plot(trace.t, trace.model_probability[:, column], label=model)
    ax.set_ylim(0.0, 1.0)
    _finish(ax, None, f"track {label(track_id)}")
  axes[-1, 0].set_xlabel("t [s]")
  axes[0, 0].set_title(_title(scenario, "Model probability"))
  return fig


STD_DEV_GROUPS = (
  ("position [m]", ("x", "y")),
  ("velocity [m/s]", ("vx", "vy")),
  ("yaw [rad]", ("yaw",)),
  ("yaw rate [rad/s]", ("yaw_rate",)),
  ("size [m]", ("length", "width", "height")),
)


def plot_std_dev(scenario: Scenario, pairs: Pairs) -> Optional[plt.Figure]:
  """Standard deviations sqrt(diag P) of the combined estimate, log scale."""
  if not scenario.estimator:
    return None
  fig, axes = plt.subplots(len(STD_DEV_GROUPS), 1, figsize=(10, 13), sharex=True)
  styles = ("-", "--", ":")
  for track_id, trace in sorted(scenario.estimator.items()):
    color = track_color(pairs, track_id)
    for ax, (_, states) in zip(axes, STD_DEV_GROUPS):
      for style, state in zip(styles, states):
        index = trace.state_index(state)
        ax.plot(trace.t, np.sqrt(np.clip(trace.covariance[:, index, index], 0.0, None)), style,
                color=color, label=f"{state} {label(track_id)}")
  for ax, (ylabel, _) in zip(axes, STD_DEV_GROUPS):
    ax.set_yscale("log")
    _finish(ax, None, ylabel)
  axes[-1].set_xlabel("t [s]")
  axes[0].set_title(_title(scenario, "Standard deviation sqrt(diag P)"))
  return fig


def run_trackeval(scenario: Scenario, fps: Optional[float] = None) -> Optional[pd.Series]:
  """TrackEval results of a scenario: the COMBINED row of TrackEval's detailed CSV.

  TrackEval's files are written to <directory>/metrics. The frame rate defaults to the
  one of the TrackEval command line. Returns None without tracks or ground truth;
  raises when TrackEval fails.
  """
  tracks, truth = scenario.files.get(TRACKS_FILE), scenario.files.get(GROUND_TRUTH_FILE)
  if tracks is None or truth is None or scenario.tracks.empty:
    return None
  fps = fps or ground_truth_fps(truth)
  evaluator = TrackEvalEvaluator().configure_metrics(list(TRACKEVAL_SCORES)[:3]).set_base_fps(fps)
  evaluator.set_output_folder(scenario.directory / "metrics")
  try:
    # TrackEval prints its configuration and progress.
    with contextlib.redirect_stdout(io.StringIO()):
      evaluator.process_tracker_outputs(list(stream_jsonl(str(tracks))), str(truth))
      evaluator.evaluate_metrics()
    detailed = evaluator.detailed_results_path()
  finally:
    evaluator.reset()
  return pd.read_csv(detailed).set_index("seq").loc["COMBINED"]


def trackeval_distances() -> np.ndarray:
  """Position error [m] accepted at each TrackEval similarity threshold."""
  return ZERO_DISTANCE * (1.0 - TRACKEVAL_ALPHAS / 100.0)


def trackeval_curve(results: pd.Series, name: str) -> np.ndarray:
  """A TrackEval metric, e.g. HOTA or HOTA_TP, at each similarity threshold."""
  return np.array([results[f"{name}___{alpha}"] for alpha in TRACKEVAL_ALPHAS], dtype=float)


def plot_trackeval(scenario: Scenario, results: Optional[pd.Series]) -> Optional[plt.Figure]:
  """TrackEval HOTA, DetA, AssA, LocA and TP/FN/FP counts against the accepted position error."""
  if results is None:
    return None
  distance = trackeval_distances()
  fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
  for name in ("HOTA", "DetA", "AssA", "LocA"):
    axes[0].plot(distance, trackeval_curve(results, name), marker=".", label=name)
  for name in ("TP", "FN", "FP"):
    axes[1].plot(distance, trackeval_curve(results, f"HOTA_{name}"), marker=".", label=name)
  axes[0].set_ylim(0.0, 1.02)
  _finish(axes[0], None, "score")
  _finish(axes[1], "accepted position error d [m]", "detections")
  scores = ", ".join(f"{name} {results[column]:.3f}" for name, column in TRACKEVAL_SCORES.items())
  axes[0].set_title(f"{_title(scenario, 'TrackEval')}\n{scores}")
  return fig


def plot_comparison(results: Dict[str, pd.Series], output, title: str = "") -> Optional[Path]:
  """Write trackeval_comparison.png: HOTA and LocA curves and score bars per labelled result.

  Returns the written file, or None without results.
  """
  if not results:
    return None
  distance = trackeval_distances()
  fig, axes = plt.subplots(3, 1, figsize=(10, 12))
  width = 0.8 / len(results)
  positions = np.arange(len(TRACKEVAL_SCORES))
  for index, (name, result) in enumerate(results.items()):
    axes[0].plot(distance, trackeval_curve(result, "HOTA"), marker=".")
    axes[1].plot(distance, trackeval_curve(result, "LocA"), marker=".")
    axes[2].bar(positions - 0.4 + (index + 0.5) * width,
                [result[column] for column in TRACKEVAL_SCORES.values()], width, label=name)
  for ax, ylabel in zip(axes, ("HOTA", "LocA", "score")):
    ax.set_ylabel(ylabel)
    ax.set_ylim(0.0, 1.02)
    ax.grid(True, alpha=0.3)
  for ax in axes[:2]:
    ax.set_xlabel("accepted position error d [m]")
  axes[2].set_xticks(positions, list(TRACKEVAL_SCORES))
  axes[2].legend(fontsize="small", loc="upper center", bbox_to_anchor=(0.5, -0.08),
                 ncol=min(len(results), 4))
  axes[0].set_title(f"TrackEval comparison: {title}" if title else "TrackEval comparison")
  output = Path(output)
  output.mkdir(parents=True, exist_ok=True)
  path = output / "trackeval_comparison.png"
  fig.tight_layout()
  fig.savefig(path, dpi=110)
  plt.close(fig)
  return path


PLOTS: Dict[str, Callable[..., Optional[plt.Figure]]] = {
  "trajectory": plot_trajectory,
  "position_error": plot_position_error,
  "speed_yaw": plot_speed_yaw,
  "size": plot_size,
  "model_probability": plot_model_probability,
  "std_dev": plot_std_dev,
  "trackeval": plot_trackeval,
}


def plot_scenario(directory, output=None, plots: Optional[Sequence[str]] = None,
                  fps: Optional[float] = None) -> Dict[str, Optional[Path]]:
  """Write the selected plots of a scenario directory.

  Args:
    directory: Scenario directory.
    output: Output directory, by default <directory>/plots.
    plots: Plot names from PLOTS, by default all.
    fps: Frame rate for pairing tracks with ground truth, by default the ground-truth rate.

  Returns:
    Plot name -> written file, or None when the plot was skipped for missing data or a
    TrackEval failure, which is reported as a warning on stderr.

  Raises:
    ValueError: for an unknown plot name.
  """
  return _plot_scenario(directory, output, plots, fps)[0]


def _plot_scenario(directory, output, plots: Optional[Sequence[str]],
                   fps: Optional[float]) -> Tuple[Dict[str, Optional[Path]], Optional[pd.Series]]:
  """plot_scenario(), also returning the TrackEval results."""
  names = list(plots) if plots else list(PLOTS)
  unknown = sorted(set(names) - set(PLOTS))
  if unknown:
    raise ValueError(f"Unknown plots {unknown}; available: {list(PLOTS)}")
  scenario = load_scenario(directory)
  output = Path(output) if output else scenario.directory / "plots"
  output.mkdir(parents=True, exist_ok=True)
  pairs = pair_tracks(scenario, fps)
  results = None
  if "trackeval" in names:
    try:
      results = run_trackeval(scenario, fps)
    except Exception as error:  # pylint: disable=broad-exception-caught
      # TrackEval must not stop the other plots.
      print(f"warning: TrackEval failed for {scenario.directory}: {error}", file=sys.stderr)

  written: Dict[str, Optional[Path]] = {}
  for name in names:
    if name == "trackeval":
      figure = plot_trackeval(scenario, results)
    else:
      figure = PLOTS[name](scenario, pairs)
    if figure is None:
      written[name] = None
      continue
    path = output / f"{name}.png"
    figure.tight_layout()
    figure.savefig(path, dpi=110)
    plt.close(figure)
    written[name] = path
  return written, results


def main(argv: Optional[List[str]] = None) -> int:
  """Command-line entry point."""
  parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
  parser.add_argument("directories", type=Path, nargs="+", metavar="directory",
                      help="scenario or evaluation pipeline run directory")
  parser.add_argument("--output", type=Path,
                      help="output directory (default: <directory>/plots); single directory only")
  parser.add_argument("--plots", type=lambda text: [name for name in text.split(",") if name],
                      help=f"comma-separated subset of: {','.join(PLOTS)}")
  parser.add_argument("--fps", type=float,
                      help="frame rate for pairing tracks with ground truth "
                      "(default: from ground truth)")
  args = parser.parse_intermixed_args(argv)
  unknown = sorted(set(args.plots or []) - set(PLOTS))
  if unknown:
    parser.error(f"unknown plots {unknown}; available: {','.join(PLOTS)}")
  several = len(args.directories) > 1
  if args.output and several:
    parser.error("--output works with a single directory only")
  parent = Path(os.path.commonpath([directory.resolve() for directory in args.directories]))
  results: Dict[str, pd.Series] = {}
  for directory in args.directories:
    try:
      written, result = _plot_scenario(directory, args.output, args.plots, args.fps)
    except FileNotFoundError as error:
      if not several:
        parser.error(str(error))
      # A glob over scenario directories also matches e.g. the comparison's plots directory.
      print(f"{directory}: skipped (no scenario files)")
      continue
    if several:
      print(f"{directory}:")
    for name, path in written.items():
      print(f"{name}: {path}" if path else f"{name}: skipped (no data)")
    if result is not None:
      results[str(directory.resolve().relative_to(parent))] = result
  if several and (not args.plots or "trackeval" in args.plots):
    path = plot_comparison(results, parent / "plots", parent.name)
    print(f"trackeval_comparison: {path}" if path else "trackeval_comparison: skipped (no data)")
  return 0


def _title(scenario: Scenario, text: str) -> str:
  return f"{text}: {scenario.directory.parent.name}/{scenario.directory.name}"


def _finish(ax, xlabel: Optional[str], ylabel: str) -> None:
  if xlabel:
    ax.set_xlabel(xlabel)
  ax.set_ylabel(ylabel)
  ax.grid(True, alpha=0.3)
  handles, _ = ax.get_legend_handles_labels()
  if 0 < len(handles) <= MAX_LEGEND_ENTRIES:
    ax.legend(fontsize="small", loc="best")


def _tracks(scenario: Scenario, pairs: Pairs) -> List[Tuple[str, pd.DataFrame]]:
  """Tracks in the order of `pairs`, so colours match across plots."""
  tracks = scenario.tracks
  return [(track_id, tracks[tracks["track_id"] == track_id]) for track_id in pairs]


def _truth(scenario: Scenario, object_id: Optional[str]) -> Optional[pd.DataFrame]:
  if object_id is None:
    return None
  return scenario.ground_truth[scenario.ground_truth["object_id"] == object_id]


def _detections(scenario: Scenario, object_id: Optional[str]) -> pd.DataFrame:
  if object_id is None:
    return scenario.detections.iloc[0:0]
  return scenario.detections[scenario.detections["object_id"] == object_id]


def _near(t: pd.Series, angles: pd.Series, track: pd.DataFrame) -> np.ndarray:
  """Angles shifted by multiples of 2π to lie nearest the unwrapped track yaw."""
  reference = np.interp(t, track["t"], np.unwrap(track["yaw"].fillna(0.0)))
  return angles + 2 * np.pi * np.round((reference - angles) / (2 * np.pi))


def _position_sigma(scenario: Scenario, track_id: str, errors: pd.DataFrame,
                    tolerance: float) -> Optional[pd.DataFrame]:
  """Along- and cross-track standard deviation from the estimator covariance at each error time."""
  trace = scenario.estimator.get(track_id)
  if trace is None:
    return None
  ix, iy = trace.state_index("x"), trace.state_index("y")
  covariance = pd.DataFrame({
    "t": trace.t,
    "pxx": trace.covariance[:, ix, ix],
    "pxy": trace.covariance[:, ix, iy],
    "pyy": trace.covariance[:, iy, iy],
  }).sort_values("t")
  joined = pd.merge_asof(errors.sort_values("t"), covariance, on="t", direction="nearest",
                         tolerance=tolerance)
  ux, uy = joined["ux"], joined["uy"]
  along = ux * ux * joined["pxx"] + 2 * ux * uy * joined["pxy"] + uy * uy * joined["pyy"]
  cross = uy * uy * joined["pxx"] - 2 * ux * uy * joined["pxy"] + ux * ux * joined["pyy"]
  return pd.DataFrame({"along": np.sqrt(along.clip(lower=0.0)),
                       "cross": np.sqrt(cross.clip(lower=0.0))})


if __name__ == "__main__":
  sys.exit(main())
