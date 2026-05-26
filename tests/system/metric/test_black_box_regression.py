# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Black-box regression evaluation tests.

Runs the full black-box evaluation suite (all three container modes) once per
pytest session and asserts that TrackEval (HOTA, MOTA, IDF1) and JitterEvaluator
(rms_jerk_ratio, acceleration_variance_ratio) metrics meet the defined thresholds.

Runs as part of the standard ``pytest tests/system/metric`` collection (metrics /
BAT groups).  When ``--image-tag`` is not supplied the image tag is read from
``version.txt`` at the repository root.

Usage::

  pytest tests/system/metric/test_black_box_regression.py
  pytest tests/system/metric/test_black_box_regression.py --image-tag 2026.1.0
"""

import csv
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent.parent.parent
_EVAL_SCRIPT = _REPO_ROOT / "tools" / "tracker" / "evaluation" / "run_black_box_evaluation.py"
_EVAL_REQUIREMENTS = _REPO_ROOT / "tools" / "tracker" / "evaluation" / "requirements.txt"
_VERSION_FILE = _REPO_ROOT / "version.txt"

# ---------------------------------------------------------------------------
# Evaluation modes (stem of the pipeline config file name)
# ---------------------------------------------------------------------------
_RUNS = [
  "black_box_controller_no_tc",
  "black_box_controller_tc",
  "black_box_tracker_service",
]

# ---------------------------------------------------------------------------
# Threshold definitions
# ---------------------------------------------------------------------------
# TrackEval: higher is better — value must be >= threshold
_TRACKEVAL_MIN: dict[str, float] = {
  "HOTA": 0.50,
  "MOTA": 0.40,
  "IDF1": 0.50,
}

# JitterEvaluator: lower is better — value must be <= threshold
_JITTER_MAX: dict[str, float] = {
  "rms_jerk_ratio": 2.0,
  "acceleration_variance_ratio": 2.0,
}

# ---------------------------------------------------------------------------
# Parametrize helpers
# ---------------------------------------------------------------------------
_TRACKEVAL_PARAMS = [
  pytest.param(run, metric, threshold, id=f"{run}/{metric}")
  for run in _RUNS
  for metric, threshold in _TRACKEVAL_MIN.items()
]

_JITTER_PARAMS = [
  pytest.param(run, metric, threshold, id=f"{run}/{metric}")
  for run in _RUNS
  for metric, threshold in _JITTER_MAX.items()
]

# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=False)
def _eval_deps_installed():
  """Ensure evaluation pipeline requirements are present in the active venv."""
  subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q", "-r", str(_EVAL_REQUIREMENTS)],
    check=True,
  )


@pytest.fixture(scope="session")
def black_box_metrics(request, tmp_path_factory, _eval_deps_installed) -> dict[tuple, float]:
  """Run all black-box evaluation modes once per session.

  The container image tag is taken from ``--image-tag`` if supplied, otherwise
  read from ``version.txt`` at the repository root.

  Returns:
    Dict mapping (run_name, evaluator, metric) -> float value.
  """
  image_tag = request.config.getoption("--image-tag")
  if not image_tag and _VERSION_FILE.exists():
    image_tag = _VERSION_FILE.read_text().strip()

  output_dir = tmp_path_factory.mktemp("bb_eval")

  cmd = [sys.executable, str(_EVAL_SCRIPT), "--output", str(output_dir)]
  if image_tag:
    cmd += ["--image-tag", image_tag]

  result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(_EVAL_SCRIPT.parent))
  if result.returncode != 0:
    pytest.fail(
      f"run_black_box_evaluation.py failed (exit {result.returncode}):\n"
      f"{result.stdout}\n{result.stderr}"
    )

  csv_files = list(output_dir.rglob("metrics.csv"))
  if not csv_files:
    pytest.fail("metrics.csv not found in evaluation output")

  metrics: dict[tuple, float] = {}
  with open(csv_files[0], newline="") as f:
    for row in csv.DictReader(f):
      key = (row["run_name"], row["evaluator"], row["metric"])
      metrics[key] = float(row["value"])
  return metrics

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("run,metric,min_threshold", _TRACKEVAL_PARAMS)
def test_trackeval_threshold(black_box_metrics, run, metric, min_threshold):
  """TrackEval metric (HOTA/MOTA/IDF1) must meet the minimum threshold."""
  key = (run, "TrackEvalEvaluator", metric)
  value = black_box_metrics.get(key)
  if value is None:
    pytest.skip(f"metric {key!r} not found in results (run may have been skipped)")
  assert value >= min_threshold, (
    f"[{run}] {metric} = {value:.4f} < minimum {min_threshold}"
  )


@pytest.mark.parametrize("run,metric,max_threshold", _JITTER_PARAMS)
def test_jitter_threshold(black_box_metrics, run, metric, max_threshold):
  """JitterEvaluator metric must not exceed the maximum threshold."""
  key = (run, "JitterEvaluator", metric)
  value = black_box_metrics.get(key)
  if value is None:
    pytest.skip(f"metric {key!r} not found in results (run may have been skipped)")
  assert value <= max_threshold, (
    f"[{run}] {metric} = {value:.4f} > maximum {max_threshold}"
  )
