# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for plotting robot-vision scenario recordings."""

import json
import math
import shutil
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# pylint: disable=wrong-import-position
from visualization.plot_scenario import (  # noqa: E402
  PLOTS,
  TRACKEVAL_ALPHAS,
  TrackEvalEvaluator,
  ground_truth_fps,
  main,
  pair_tracks,
  plot_altitude,
  plot_comparison,
  plot_scenario,
  plot_size,
  plot_speed_yaw,
  plot_std_dev,
  plot_position_error,
  plot_trajectory,
  position_errors,
  trackeval_distances,
)
from visualization.plot_scenario import _position_sigma  # noqa: E402 pylint: disable=protected-access
from visualization.scenario_data import (  # noqa: E402
  PIPELINE_RUN_FILES,
  SCENARIO_FILES,
  load_scenario,
)
# pylint: enable=wrong-import-position
import matplotlib.pyplot as plt  # noqa: E402 (after plot_scenario, which selects the Agg backend)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
FIXTURE = Path(__file__).parent / "fixtures" / "target_born_moving"


def assert_png(path):
  """The file exists and is a PNG image."""
  assert path.read_bytes()[:8] == PNG_SIGNATURE


def test_writes_all_plots(recording):
  """A recording with all four files produces every plot in PLOTS; altitude is skipped for planar."""
  written = plot_scenario(recording)

  assert list(written) == list(PLOTS)
  # For the planar recording, altitude should be None (no vertical motion)
  assert written["altitude"] is None
  # All other plots should be PNG files
  for name, path in written.items():
    if name == "altitude":
      continue  # Already checked as None
    assert path == recording / "plots" / f"{name}.png"
    assert_png(path)
  assert (recording / "metrics" / "tracker_eval" / "pedestrian_detailed.csv").is_file()


def test_writes_selected_plots_to_output(recording, tmp_path):
  """--plots selects a subset and --output redirects the files."""
  output = tmp_path / "out"

  written = plot_scenario(recording, output, ["trajectory", "std_dev"])

  assert sorted(written) == ["std_dev", "trajectory"]
  assert sorted(path.name for path in output.iterdir()) == ["std_dev.png", "trajectory.png"]
  assert not (recording / "plots").exists()
  assert not (recording / "metrics").exists()


def test_tracker_output_skips_estimator_plots(tracker_output):
  """Without estimator.jsonl the estimator plots are skipped; tracks pair with truth by position."""
  written = plot_scenario(tracker_output)

  assert written["model_probability"] is None
  assert written["std_dev"] is None
  assert written["altitude"] is None  # No vertical motion in planar tracker output
  for name in ("trajectory", "position_error", "speed_yaw", "size", "trackeval"):
    assert_png(written[name])


def test_trackeval_failure_is_a_warning(recording, monkeypatch, capsys):
  """A TrackEval error skips only the trackeval plot, with a warning on stderr."""
  def fail(self):
    raise RuntimeError("boom")
  monkeypatch.setattr(TrackEvalEvaluator, "evaluate_metrics", fail)

  written = plot_scenario(recording)

  assert written["trackeval"] is None
  assert_png(written["trajectory"])
  assert "warning: TrackEval failed" in capsys.readouterr().err


def test_trackeval_frame_rate_matches_command_line(tmp_path, monkeypatch):
  """Without --fps, TrackEval gets the frame rate of the TrackEval command line."""
  directory = tmp_path / "uneven"
  directory.mkdir()
  frames = []
  for seconds in (0.0, 0.1, 0.2, 0.4, 0.6):  # intervals 0.1, 0.1, 0.2, 0.2
    frames.append({"timestamp": f"2026-01-01T00:00:00.{int(seconds * 10)}00Z", "objects": [
      {"id": 1, "category": "person", "translation": [seconds, 0.0, 0.0]}]})
  for name in ("groundtruth.jsonl", "tracks.jsonl"):
    (directory / name).write_text("".join(json.dumps(f) + "\n" for f in frames), encoding="utf-8")
  used = []
  original = TrackEvalEvaluator.set_base_fps
  monkeypatch.setattr(TrackEvalEvaluator, "set_base_fps",
                      lambda self, fps=None: used.append(fps) or original(self, fps))

  plot_scenario(directory, plots=["trackeval"])

  np.testing.assert_allclose(used, [ground_truth_fps(directory / "groundtruth.jsonl")])
  np.testing.assert_allclose([ground_truth_fps(directory / "groundtruth.jsonl")], [10/1.5])


def test_trackeval_needs_ground_truth(recording, capsys):
  """Without ground truth the trackeval plot is skipped without a warning."""
  (recording / "groundtruth.jsonl").unlink()

  assert plot_scenario(recording, plots=["trackeval"])["trackeval"] is None
  assert not capsys.readouterr().err


def test_compares_directories(recording, tracker_output, tmp_path, capsys):
  """Several directories also give a comparison in their common parent; others are skipped."""
  arguments = [str(recording), str(tracker_output), "--plots", "trackeval"]
  assert main(arguments) == 0
  assert_png(tmp_path / "plots" / "trackeval_comparison.png")
  assert capsys.readouterr().out.splitlines()[-1] == (
    f"trackeval_comparison: {tmp_path / 'plots' / 'trackeval_comparison.png'}")

  # A glob over the parent now also matches the comparison's plots directory.
  assert main([*arguments, str(tmp_path / "plots")]) == 0
  assert f"{tmp_path / 'plots'}: skipped (no scenario files)" in capsys.readouterr().out
  with pytest.raises(SystemExit):
    main([*arguments, "--output", str(tmp_path / "out")])


def test_trackeval_distances():
  """TrackEval similarity thresholds 5..95 % accept position errors of 1.9..0.1 m."""
  np.testing.assert_allclose(trackeval_distances()[[0, 9, 18]], [1.9, 1.0, 0.1])


def test_rejects_unknown_plot(recording):
  """Unknown plot names are an error."""
  with pytest.raises(ValueError):
    plot_scenario(recording, plots=["nope"])
  with pytest.raises(SystemExit):
    main([str(recording), "--plots", "trajectory,nope"])


def test_command_line(recording, capsys):
  """The CLI writes the plots and lists them."""
  assert main([str(recording), "--plots", "trajectory,size"]) == 0

  assert capsys.readouterr().out.splitlines() == [
    f"trajectory: {recording / 'plots' / 'trajectory.png'}",
    f"size: {recording / 'plots' / 'size.png'}",
  ]


def test_position_errors_in_truth_frame():
  """Errors split into along-track and cross-track (positive to the left of the motion)."""
  aligned = pd.DataFrame({
    "t": [0.0, 0.1, 0.2, 0.3],
    "x": [0.3, 0.3, 0.3, 0.3], "y": [-0.1, 0.1, 0.3, 0.3],
    "x_gt": [0.0, 0.0, 0.0, 0.0], "y_gt": [0.0, 0.2, 0.4, 0.4],
    "vx_gt": [0.0, math.nan, 0.0, 0.0], "vy_gt": [2.0, math.nan, 2.0, 0.0],
  })

  errors = position_errors(aligned)

  np.testing.assert_allclose(errors["total"], math.hypot(0.3, 0.1))
  # Moving along +y; the second row derives the direction from the truth positions.
  np.testing.assert_allclose(errors["along"][:3], -0.1)
  np.testing.assert_allclose(errors["cross"][:3], -0.3)
  # Standing still: no direction.
  assert math.isnan(errors["along"][3]) and math.isnan(errors["cross"][3])


def test_position_errors_with_repeated_timestamps():
  """Rows sharing a time (Immediate-mode output) get the truth direction from its positions."""
  t = [0.0, 0.1, 0.1, 0.2, 0.2, 0.3, 0.3, 0.4]
  aligned = pd.DataFrame({
    "t": t,
    "x": [time - 0.05 for time in t], "y": [0.2] * len(t),
    "x_gt": t, "y_gt": [0.0] * len(t),
    "vx_gt": [math.nan] * len(t), "vy_gt": [math.nan] * len(t),
  })

  with warnings.catch_warnings():
    warnings.simplefilter("error")
    errors = position_errors(aligned)

  # Moving along +x at 1 m/s, the estimate 0.05 m behind and 0.2 m to the left.
  np.testing.assert_allclose(errors["along"], -0.05)
  np.testing.assert_allclose(errors["cross"], 0.2)


def test_position_errors_with_one_distinct_timestamp():
  """Rows at a single time give no direction, without numerical warnings."""
  aligned = pd.DataFrame({
    "t": [0.5, 0.5], "x": [0.1, 0.2], "y": [0.0, 0.0], "x_gt": [0.0, 0.0], "y_gt": [0.0, 0.0],
    "vx_gt": [math.nan, math.nan], "vy_gt": [math.nan, math.nan],
  })

  with warnings.catch_warnings():
    warnings.simplefilter("error")
    errors = position_errors(aligned)

  assert errors["along"].isna().all() and errors["cross"].isna().all()
  np.testing.assert_allclose(errors["total"], [0.1, 0.2])


def scenario_with_yawed_detections(tmp_path, pipeline):
  """The recorded scenario with detections yawed by 1 rad, as a recorder or pipeline run directory.

  The pipeline's detections are in a sensor frame 100 m off the scene and carry the same ids as
  the ground truth, which only a recorder guarantees.
  """
  directory = tmp_path / ("pipeline" if pipeline else "recorder")
  layout = PIPELINE_RUN_FILES if pipeline else {name: name for name in SCENARIO_FILES}
  for name, relative in layout.items():
    (directory / relative).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE / name, directory / relative)
  detections = directory / layout["detections.jsonl"]
  frames = [json.loads(line) for line in detections.read_text(encoding="utf-8").splitlines()]
  for frame in frames:
    for objects in frame["objects"].values():
      for detection in objects:
        detection["rotation"] = [0.0, 0.0, math.sin(0.5), math.cos(0.5)]
        if pipeline:
          detection["translation"][0] += 100.0
  detections.write_text("".join(json.dumps(frame) + "\n" for frame in frames), encoding="utf-8")
  return load_scenario(directory)


@pytest.mark.parametrize("pipeline, drawn", [(False, True), (True, False)])
def test_overlays_detections_only_where_they_are_in_the_scene(tmp_path, pipeline, drawn):
  """Recorder detections carry ground-truth ids in scene coordinates; a pipeline run's do not."""
  scenario = scenario_with_yawed_detections(tmp_path, pipeline)
  pairs = pair_tracks(scenario)

  assert not scenario.detections.empty
  for plot in (plot_trajectory, plot_size, plot_speed_yaw):
    figure = plot(scenario, pairs)
    labels = [line.get_label() for axis in figure.axes for line in axis.lines]
    assert any(label.startswith("detections") for label in labels) is drawn, (plot.__name__, labels)


def quaternion(yaw):
  """Rotation about z as a quaternion [x, y, z, w]."""
  return [0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0)]


def yaw_curves(directory, start, step, error):
  """Truth and track yaw as drawn by plot_speed_yaw, for a truth heading start + step * frame.

  The track follows the same positions with its heading `error` rad off.
  """
  truth, tracks = [], []
  for frame in range(8):
    timestamp = f"2014-09-08T04:00:00.{frame}00Z"
    heading = start + step * frame
    position = [0.1 * frame, 0.0, 0.0]
    truth.append({"timestamp": timestamp, "objects": [
      {"id": 0, "category": "person", "translation": position, "rotation": quaternion(heading)}]})
    tracks.append({"timestamp": timestamp, "objects": [
      {"id": "1", "category": "person", "translation": position,
       "rotation": quaternion(heading + error)}]})
  for name, records in (("groundtruth.jsonl", truth), ("tracks.jsonl", tracks)):
    (directory / name).write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")

  figure = plot_speed_yaw(load_scenario(directory), {"1": "0"})
  lines = {line.get_label(): np.asarray(line.get_ydata(), dtype=float)
           for line in figure.axes[1].lines}
  plt.close(figure)
  return lines["truth 1"], lines["track 1"]  # both labelled with the track id


@pytest.mark.parametrize("start, step", [
  (math.pi - 0.01, 0.0),    # truth just below +pi, the estimate wraps to -pi
  (-math.pi + 0.01, 0.0),
  (math.pi - 0.01, 0.05),   # turning through +-pi with the first samples on opposite sides
  (math.pi - 0.2, 0.05),    # turning through +-pi with the first samples on the same side
])
def test_speed_yaw_draws_truth_on_the_track_branch(tmp_path, start, step):
  """Equivalent headings on opposite sides of +-pi are drawn together, not 2 pi apart."""
  error = 0.02 if start > 0 else -0.02

  truth, track = yaw_curves(tmp_path, start, step, error)

  np.testing.assert_allclose(track - truth, error, atol=1e-9)


def trackeval_result(**scores):
  """A TrackEval COMBINED row with the columns the comparison plot reads."""
  row = {f"{name}___{alpha}": 0.5 for name in ("HOTA", "LocA") for alpha in TRACKEVAL_ALPHAS}
  row.update({"HOTA___AUC": 0.5, "MOTA": 0.5, "IDF1": 0.5, "LocA___AUC": 0.5})
  row.update(scores)
  return pd.Series(row)


def comparison_limits(results, directory, monkeypatch):
  """y-limits of the three axes of the comparison plot."""
  figures = []
  with monkeypatch.context() as patch:
    patch.setattr(plt, "close", figures.append)  # keeps the figure to read its axes
    plot_comparison(results, directory)
  (figure,) = figures
  limits = [axis.get_ylim() for axis in figure.axes]
  plt.close(figure)
  return limits


def test_comparison_score_axis_includes_negative_mota(tmp_path, monkeypatch):
  """MOTA is negative when false positives and ID switches exceed the true positives."""
  results = {"poor": trackeval_result(MOTA=-0.5), "good": trackeval_result()}

  curves_hota, curves_loca, scores = comparison_limits(results, tmp_path, monkeypatch)

  assert scores[0] < -0.5
  assert scores[1] == pytest.approx(1.02)
  assert curves_hota == pytest.approx((0.0, 1.02))
  assert curves_loca == pytest.approx((0.0, 1.02))


@pytest.mark.parametrize("mota", [0.3, math.nan])
def test_comparison_score_axis_starts_at_zero_without_negative_scores(tmp_path, monkeypatch, mota):
  """Non-negative and missing scores keep the 0..1 axis."""
  limits = comparison_limits({"run": trackeval_result(MOTA=mota)}, tmp_path, monkeypatch)

  assert limits[2] == pytest.approx((0.0, 1.02))


def test_position_error_plot_with_an_earlier_detection(early_detection):
  """With --fps 10, a track pairs with its truth when a detection precedes both by 0.05 s."""
  written = plot_scenario(early_detection, plots=["position_error"], fps=10.0)

  assert written["position_error"] is not None
  assert_png(written["position_error"])


def test_climbing_recording_writes_altitude(climbing_recording):
  """A recording with vertical motion writes altitude.png and all other plots."""
  written = plot_scenario(climbing_recording)

  assert list(written) == list(PLOTS)
  # altitude should exist for climbing recording
  assert written["altitude"] is not None
  assert_png(written["altitude"])
  # All other plots should be PNGs (except those without estimator)
  for name, path in written.items():
    if name in ("altitude", "model_probability", "std_dev", "trackeval"):
      continue  # Already checked or may vary
    if path is not None:
      assert_png(path)


def test_plot_altitude_on_climbing_recording(climbing_recording):
  """plot_altitude returns a figure with z and vz panels containing track, truth, detections."""
  scenario = load_scenario(climbing_recording)
  pairs = pair_tracks(scenario)

  fig = plot_altitude(scenario, pairs)

  assert fig is not None
  axes = fig.get_axes()
  assert len(axes) == 2
  assert axes[0].get_ylabel() == "z [m]"
  assert axes[1].get_ylabel() == "vz [m/s]"

  # Check that z axis has lines for track, truth, and detections
  handles, labels = axes[0].get_legend_handles_labels()
  label_starts = set(label.split()[0] for label in labels)
  assert "track" in label_starts or any("track" in label for label in labels)
  assert "truth" in label_starts or any("truth" in label for label in labels)
  assert "detections" in label_starts or any("detections" in label for label in labels)

  # Check vz axis has track and truth
  handles, labels = axes[1].get_legend_handles_labels()
  label_starts = set(label.split()[0] for label in labels)
  assert "track" in label_starts or any("track" in label for label in labels)
  assert "truth" in label_starts or any("truth" in label for label in labels)

  plt.close(fig)


def test_plot_altitude_on_planar_recording_is_none(recording):
  """plot_altitude returns None for planar (no vertical motion) recordings."""
  scenario = load_scenario(recording)
  pairs = pair_tracks(scenario)

  fig = plot_altitude(scenario, pairs)

  assert fig is None


def test_plot_std_dev_on_climbing_recording(climbing_recording):
  """plot_std_dev includes z and vz entries for climbing recording with vertical motion."""
  scenario = load_scenario(climbing_recording)
  pairs = pair_tracks(scenario)

  fig = plot_std_dev(scenario, pairs)

  assert fig is not None
  axes = fig.get_axes()
  assert len(axes) == 5  # position, velocity, yaw, yaw_rate, size

  # Position axis (first) should have z entries
  handles, labels = axes[0].get_legend_handles_labels()
  z_labels = [label for label in labels if label.startswith("z ")]
  assert z_labels, "Expected z entries in position panel"

  # Velocity axis (second) should have vz entries
  handles, labels = axes[1].get_legend_handles_labels()
  vz_labels = [label for label in labels if label.startswith("vz ")]
  assert vz_labels, "Expected vz entries in velocity panel"

  plt.close(fig)


def test_plot_std_dev_on_legacy_12_state_recording_skips_vz(legacy_estimator_recording):
  """plot_std_dev on 12-state recording skips vz silently, no crash."""
  scenario = load_scenario(legacy_estimator_recording)
  pairs = pair_tracks(scenario)

  fig = plot_std_dev(scenario, pairs)

  assert fig is not None
  axes = fig.get_axes()

  # Position axis should have z but not vz
  handles, labels = axes[0].get_legend_handles_labels()
  z_labels = [label for label in labels if label.startswith("z ")]
  vz_labels = [label for label in labels if label.startswith("vz ")]
  assert z_labels, "Expected z entries in position panel"
  assert not vz_labels, "Should not have vz entries in 12-state recording"

  # Velocity axis should not have vz
  handles, labels = axes[1].get_legend_handles_labels()
  vz_labels = [label for label in labels if label.startswith("vz ")]
  assert not vz_labels, "Should not have vz entries in velocity panel"

  plt.close(fig)


def test_position_errors_with_height():
  """The total covers x, y and z by default, the plane or the height on request."""
  aligned = pd.DataFrame({
    "t": [0.0, 0.1],
    "x": [0.3, 0.3], "y": [0.4, 0.4], "z": [1.2, -1.2],
    "x_gt": [0.0, 0.0], "y_gt": [0.0, 0.0], "z_gt": [0.0, 0.0],
    "vx_gt": [1.0, 1.0], "vy_gt": [0.0, 0.0],
  })

  np.testing.assert_allclose(position_errors(aligned)["total"], 1.3)
  np.testing.assert_allclose(position_errors(aligned, "xy")["total"], 0.5)
  np.testing.assert_allclose(position_errors(aligned, "z")["total"], 1.2)
  np.testing.assert_allclose(position_errors(aligned)["vertical"], [1.2, -1.2])
  with pytest.raises(ValueError, match="space"):
    position_errors(aligned, "xz")


def test_position_errors_without_height_are_planar():
  """Without z columns or values the total stays the planar error."""
  planar = pd.DataFrame({
    "t": [0.0], "x": [0.3], "y": [0.4], "x_gt": [0.0], "y_gt": [0.0],
    "vx_gt": [1.0], "vy_gt": [0.0],
  })
  nan_z = planar.assign(z=math.nan, z_gt=math.nan)

  np.testing.assert_allclose(position_errors(planar)["total"], 0.5)
  np.testing.assert_allclose(position_errors(nan_z)["total"], 0.5)
  assert math.isnan(position_errors(nan_z)["vertical"][0])


@pytest.mark.parametrize("space, panels", [
  ("xyz", ["total", "along-track", "cross-track", "vertical"]),
  ("xy", ["total", "along-track", "cross-track"]),
  ("z", ["total", "vertical"]),
])
def test_position_error_panels_follow_the_space(climbing_recording, space, panels):
  """With vertical motion: a vertical panel in x, y, z and in z; no plane panels for z."""
  scenario = load_scenario(climbing_recording)

  fig = plot_position_error(scenario, pair_tracks(scenario, space=space), space)

  assert [ax.get_ylabel().split(" [")[0] for ax in fig.get_axes()] == panels
  plt.close(fig)


def test_planar_recording_has_no_vertical_panel(recording):
  """Planar data keeps the three planar panels by default."""
  scenario = load_scenario(recording)

  fig = plot_position_error(scenario, pair_tracks(scenario))

  assert len(fig.get_axes()) == 3
  plt.close(fig)


def test_vertical_error_band_from_the_estimator(recording):
  """The vertical ±2σ comes from the z variance of the estimator state."""
  scenario = load_scenario(recording)
  track_id = next(iter(scenario.estimator))
  errors = pd.DataFrame({"t": scenario.estimator[track_id].t, "ux": 1.0, "uy": 0.0})

  sigma = _position_sigma(scenario, track_id, errors, tolerance=0.05)

  assert sigma["vertical"].notna().all() and (sigma["vertical"] > 0).all()


@pytest.fixture(name="stacked_tracks")
def fixture_stacked_tracks(tmp_path):
  """Tracks a and b above each other's truth: a=(0,0,0), b=(1,0,5); objects 1=(1,0,0), 2=(0,0,5)."""
  directory = tmp_path / "stacked"
  directory.mkdir()
  stamps = [f"2014-09-08T04:00:{frame // 10:02d}.{frame % 10}00Z" for frame in range(12)]
  truth = [{"timestamp": stamp, "objects": [
    {"id": 1, "category": "person", "translation": [1.0, 0.0, 0.0]},
    {"id": 2, "category": "person", "translation": [0.0, 0.0, 5.0]}]} for stamp in stamps]
  tracks = [{"id": "scene", "name": "scene", "timestamp": stamp, "objects": [
    {"id": "a", "category": "person", "translation": [0.0, 0.0, 0.0]},
    {"id": "b", "category": "person", "translation": [1.0, 0.0, 5.0]}]} for stamp in stamps]
  for name, records in (("groundtruth.jsonl", truth), ("tracks.jsonl", tracks)):
    (directory / name).write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
  return directory


@pytest.mark.parametrize("space, pairs", [
  ("xyz", {"a": "1", "b": "2"}),
  ("xy", {"a": "2", "b": "1"}),
  ("z", {"a": "1", "b": "2"}),
])
def test_pairing_follows_the_space(stacked_tracks, space, pairs):
  """Pairs differ when the height or the plane decides."""
  assert pair_tracks(load_scenario(stacked_tracks), space=space) == pairs


def test_command_line_space_flags(climbing_recording, capsys):
  """--xy-only and --z-only restrict the position error and TrackEval; both together are rejected."""
  for flag in ("--xy-only", "--z-only"):
    assert main([str(climbing_recording), "--plots", "position_error,trackeval", flag]) == 0
  assert "position_error" in capsys.readouterr().out
  with pytest.raises(SystemExit):
    main([str(climbing_recording), "--xy-only", "--z-only"])


def test_plot_scenario_rejects_unknown_space(recording):
  """The space is checked before anything is written."""
  with pytest.raises(ValueError, match="space"):
    plot_scenario(recording, space="xz")
