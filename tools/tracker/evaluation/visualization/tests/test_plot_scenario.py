# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for plotting robot-vision scenario recordings."""

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# pylint: disable-next=wrong-import-position
from visualization.plot_scenario import PLOTS, main, plot_scenario, position_errors  # noqa: E402

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


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


def test_writes_selected_plots_to_output(recording, tmp_path):
  """--plots selects a subset and --output redirects the files."""
  output = tmp_path / "out"

  written = plot_scenario(recording, output, ["trajectory", "std_dev"])

  assert sorted(written) == ["std_dev", "trajectory"]
  assert sorted(path.name for path in output.iterdir()) == ["std_dev.png", "trajectory.png"]
  assert not (recording / "plots").exists()


def test_tracker_output_skips_estimator_plots(tracker_output):
  """Without estimator.jsonl the estimator plots are skipped; tracks pair with truth by position."""
  written = plot_scenario(tracker_output)

  assert written["model_probability"] is None
  assert written["std_dev"] is None
  for name in ("trajectory", "position_error", "speed_yaw", "size"):
    assert_png(written[name])


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
