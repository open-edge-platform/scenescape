# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Black-box evaluation tests.

Runs the full black-box evaluation suite (all three container modes) once per
pytest session and asserts that TrackEval (HOTA, MOTA, IDF1) and JitterEvaluator
(rms_jerk_ratio, acceleration_variance_ratio) metrics meet the defined thresholds.

Runs as part of the standard ``pytest tests/system/metric`` collection.
The container image tag is read from ``version.txt`` at the
repository root.

Usage::

  pytest tests/system/metric/test_black_box_evaluation.py
"""

import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent.parent.parent
_EVAL_SCRIPT = _REPO_ROOT / "tools" / "tracker" / "evaluation" / "run_black_box_evaluation.py"
_VERSION_FILE = _REPO_ROOT / "version.txt"

# ---------------------------------------------------------------------------
# Evaluation modes (stem of the pipeline config file name)
# ---------------------------------------------------------------------------
_RUNS = [
  "black_box_controller_immediate",
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
@pytest.fixture(scope="session")
def black_box_metrics(tmp_path_factory) -> dict[tuple, float]:
  """Run all black-box evaluation modes once per session.

  The container image tag is read from ``version.txt`` at the repository root.

  Returns:
    Dict mapping (run_name, evaluator, metric) -> float value.
  """
  eval_dir = str(_EVAL_SCRIPT.parent)

  # The test suite has its own ``tests/utils`` package already cached in
  # sys.modules under the name ``utils``.  The evaluation package has its own
  # ``utils`` (containing format_converters, etc.) that lives in eval_dir.
  # We must evict the test-suite ``utils`` from the module cache for the
  # duration of the evaluation call, then restore everything afterwards so
  # the rest of the test session is unaffected.
  _evicted = {k: v for k, v in sys.modules.items()
              if k == "utils" or k.startswith("utils.")}
  _eval_modules = [
    "run_black_box_evaluation", "pipeline_engine",
  ]
  _evicted.update({k: v for k, v in sys.modules.items()
                   if k in _eval_modules or k.startswith(tuple(m + "." for m in _eval_modules))})
  for k in _evicted:
    del sys.modules[k]

  sys.path.insert(0, eval_dir)
  try:
    import importlib
    import run_black_box_evaluation as _rbbe  # noqa: PLC0415
    importlib.reload(_rbbe)

    image_tag = _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else None
    output_dir = tmp_path_factory.mktemp("bb_eval")

    results = _rbbe.run_all(image_tag=image_tag, output_dir=output_dir)
  finally:
    sys.path.remove(eval_dir)
    # Remove all modules that were imported from eval_dir.
    for k in list(sys.modules):
      if k == "utils" or k.startswith("utils."):
        del sys.modules[k]
    # Restore the test-suite modules.
    sys.modules.update(_evicted)

  errors: list[str] = []
  metrics: dict[tuple, float] = {}
  for run_name, result in results:
    if isinstance(result, Exception):
      errors.append(f"{run_name}: {result}")
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
@pytest.mark.basic_acceptance
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


@pytest.mark.basic_acceptance
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
