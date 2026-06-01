# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Black-box evaluation tests.

Runs the full black-box evaluation suite (all three container modes) once per
pytest session and asserts that TrackEval (HOTA, MOTA, IDF1) and JitterEvaluator
(rms_jerk_ratio, acceleration_variance_ratio) metrics meet the defined thresholds.

Runs as part of the standard ``pytest tests/system/metric`` collection (metrics /
BAT groups).  The container image tag is read from ``version.txt`` at the
repository root.

Usage::

  pytest tests/system/metric/test_black_box_evaluation.py
"""

import json
import subprocess
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
# Driver script template — executed inside an isolated virtualenv
# ---------------------------------------------------------------------------
_DRIVER_TEMPLATE = """\
import json, sys
from pathlib import Path

sys.path.insert(0, {eval_dir})
from run_black_box_evaluation import run_all

results = run_all(image_tag={image_tag} or None, output_dir=Path({output_dir}))

serialised = []
for name, v in results:
    if isinstance(v, Exception):
        serialised.append([name, {{"__error__": str(v)}}])
    else:
        serialised.append([name, v])

Path({results_file}).write_text(json.dumps(serialised, default=float))
"""


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def black_box_metrics(tmp_path_factory) -> dict[tuple, float]:
  """Run all black-box evaluation modes once per session.

  The evaluation runs in an isolated virtualenv so its pinned dependencies
  (numpy, pandas, pytest, …) cannot affect the running test process.

  The container image tag is read from ``version.txt`` at the repository root.

  Returns:
    Dict mapping (run_name, evaluator, metric) -> float value.
  """
  import venv as _venv

  work_dir = tmp_path_factory.mktemp("bb_eval")
  venv_dir = work_dir / "venv"
  output_dir = work_dir / "output"
  output_dir.mkdir()
  results_file = work_dir / "results.json"

  # Build an isolated virtualenv so the evaluation's pinned deps do not
  # mutate the active test-process environment.
  _venv.create(str(venv_dir), with_pip=True, clear=True)
  venv_python = venv_dir / "bin" / "python"
  subprocess.run(
    [str(venv_python), "-m", "pip", "install", "-q", "-r", str(_EVAL_REQUIREMENTS)],
    check=True,
  )

  image_tag = _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else ""

  driver = work_dir / "_eval_driver.py"
  driver.write_text(
    _DRIVER_TEMPLATE.format(
      eval_dir=repr(str(_EVAL_SCRIPT.parent)),
      image_tag=repr(image_tag),
      output_dir=repr(str(output_dir)),
      results_file=repr(str(results_file)),
    )
  )

  proc = subprocess.run(
    [str(venv_python), str(driver)],
    capture_output=True,
    text=True,
  )
  if proc.returncode != 0:
    pytest.fail(
      f"Evaluation subprocess failed (exit {proc.returncode}):\n"
      f"{proc.stderr or proc.stdout}"
    )

  raw = json.loads(results_file.read_text())

  errors: list[str] = []
  metrics: dict[tuple, float] = {}
  for run_name, result in raw:
    if "__error__" in result:
      errors.append(f"{run_name}: {result['__error__']}")
      continue
    for evaluator_name, evaluator_metrics in result.items():
      for metric, value in evaluator_metrics.items():
        metrics[(run_name, evaluator_name, metric)] = float(value)

  if not metrics and errors:
    pytest.fail(
      "All evaluation runs failed — check container images and harness setup:\n"
      + "\n".join(errors)
    )

  return metrics

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@pytest.mark.metric
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


@pytest.mark.metric
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
