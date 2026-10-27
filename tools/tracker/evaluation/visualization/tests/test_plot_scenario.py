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
  TrackEvalEvaluator,
  ground_truth_fps,
  main,
  pair_tracks,
  plot_scenario,
  plot_size,
  plot_speed_yaw,
  plot_trajectory,
  position_errors,
  trackeval_distances,
)
from visualization.scenario_data import (  # noqa: E402
  PIPELINE_RUN_FILES,
  SCENARIO_FILES,
  load_scenario,
)
# pylint: enable=wrong-import-position

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
FIXTURE = Path(__file__).parent / "fixtures" / "target_born_moving"


def assert_png(path):
  """The file exists and is a PNG image."""
  assert path.read_bytes()[:8] == PNG_SIGNATURE


def test_writes_all_plots(recording):
  """A recording with all four files produces every plot in <directory>/plots."""
  written = plot_scenario(recording)

  assert list(written) == list(PLOTS)
  for name, path in written.items():
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
