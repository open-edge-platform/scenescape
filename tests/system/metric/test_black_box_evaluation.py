# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Black-box evaluation tests.

Runs the full black-box evaluation suite (all three container modes) once per
pytest session and asserts that TrackEval (HOTA, MOTA, IDF1) and JitterEvaluator
(rms_jerk_ratio, acceleration_variance_ratio) metrics meet the defined thresholds.

Usage::

  # Run this file directly
  pytest tests/system/metric/test_black_box_evaluation.py
"""

import sys
from pathlib import Path

import pytest

import tests.common_test_utils as common

_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent.parent.parent
_EVAL_SCRIPT = _REPO_ROOT / "tools" / "tracker" / "evaluation" / "run_black_box_evaluation.py"
_VERSION_FILE = _REPO_ROOT / "version.txt"

_TRACKEVAL_MIN: dict[str, dict[str, float]] = {
  "black_box_controller_immediate": {
    "HOTA": 0.75,
    "MOTA": 0.95,
    "IDF1": 0.95,
  },
  "black_box_controller_tc": {
    "HOTA": 0.70,
    "MOTA": 0.60,
    "IDF1": 0.75,
  },
  "black_box_tracker_service": {
    "HOTA": 0.60,
    "MOTA": 0.70,
    "IDF1": 0.75,
  },
}

_JITTER_MAX: dict[str, dict[str, float]] = {
  "black_box_controller_immediate": {
    "rms_jerk_ratio": 20.0,
    "acceleration_variance_ratio": 200.0,
  },
  "black_box_controller_tc": {
    "rms_jerk_ratio": 10.0,
    "acceleration_variance_ratio": 50.0,
  },
  "black_box_tracker_service": {
    "rms_jerk_ratio": 25.0,
    "acceleration_variance_ratio": 350.0,
  },
}

_TRACKEVAL_PARAMS = [
  pytest.param(run, metric, threshold, id=f"{run}/{metric}")
  for run, thresholds in _TRACKEVAL_MIN.items()
  for metric, threshold in thresholds.items()
]

_JITTER_PARAMS = [
  pytest.param(run, metric, threshold, id=f"{run}/{metric}")
  for run, thresholds in _JITTER_MAX.items()
  for metric, threshold in thresholds.items()
]

TEST_NAME = "NEX-T10463"

@pytest.fixture(scope="session")
def black_box_metrics(tmp_path_factory) -> dict[tuple, float]:
  """Run all black-box evaluation modes once per session.

  The container image tag is read from ``version.txt`` at the repository root.

  Returns:
    Dict mapping (run_name, evaluator, metric) -> float value.
  """
  eval_dir = str(_EVAL_SCRIPT.parent)

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

@pytest.mark.parametrize("run,metric,min_threshold", _TRACKEVAL_PARAMS)
def test_trackeval_threshold(black_box_metrics, run, metric, min_threshold, record_xml_attribute):
  """TrackEval metric (HOTA/MOTA/IDF1) must meet the minimum threshold."""
  record_xml_attribute("name", TEST_NAME)
  print("Executing: " + TEST_NAME)
  exit_code = 1
  key = (run, "TrackEvalEvaluator", metric)
  value = black_box_metrics.get(key)
  if value is None:
    common.record_test_result(TEST_NAME, exit_code)
    pytest.fail(f"metric {key!r} not found in results")
  passed = value >= min_threshold
  exit_code = 0 if passed else 1
  status = "PASS" if passed else "FAIL"
  print(f"  [{run}] {metric} = {value:.4f} (min {min_threshold}) -> {status}")
  common.record_test_result(TEST_NAME, exit_code)
  assert passed, (
    f"[{run}] {metric} = {value:.4f} < minimum {min_threshold}"
  )


@pytest.mark.parametrize("run,metric,max_threshold", _JITTER_PARAMS)
def test_jitter_threshold(black_box_metrics, run, metric, max_threshold, record_xml_attribute):
  """JitterEvaluator metric must not exceed the maximum threshold."""
  record_xml_attribute("name", TEST_NAME)
  print("Executing: " + TEST_NAME)
  exit_code = 1
  key = (run, "JitterEvaluator", metric)
  value = black_box_metrics.get(key)
  if value is None:
    common.record_test_result(TEST_NAME, exit_code)
    pytest.fail(f"metric {key!r} not found in results")
  passed = value <= max_threshold
  exit_code = 0 if passed else 1
  status = "PASS" if passed else "FAIL"
  print(f"  [{run}] {metric} = {value:.4f} (max {max_threshold}) -> {status}")
  common.record_test_result(TEST_NAME, exit_code)
  assert passed, (
    f"[{run}] {metric} = {value:.4f} > maximum {max_threshold}"
  )
