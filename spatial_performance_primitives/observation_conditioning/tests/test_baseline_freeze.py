# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""The frozen baseline of the original MVP and the scenario corpus behind it.

`tests/data/mvp-original.ocb` records what the original MVP (commit 5cc7f08a8) computes on
the scenario corpus. These tests check that the corpus still produces the recorded inputs,
that every decision branch is reached, and that the current Python implementation still
reproduces the recorded outputs. Set OC_BASELINE_STRICT=1 (the container does when
regenerating) to demand bit-identical floats; otherwise a tiny tolerance absorbs BLAS
differences between CPUs.
"""

import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from observation_conditioning import AmodalReasoner  # noqa: E402
from oc_corpus import baseline  # noqa: E402
from oc_corpus.capture import capture_decisions, evaluate_core, reached_flags  # noqa: E402
from oc_corpus.ocb import read_ocb, write_ocb  # noqa: E402
from oc_corpus.scenarios import FLAGS, build_corpus  # noqa: E402

BASELINE = Path(__file__).resolve().parent / "data" / "mvp-original.ocb"
STRICT = os.getenv("OC_BASELINE_STRICT") == "1"

ARRAYS, META = read_ocb(BASELINE)
SCENARIOS = sorted(META["scenarios"])


def assert_same(actual, expected, label):
  actual, expected = np.asarray(actual), np.asarray(expected)
  assert actual.shape == expected.shape, label
  if actual.dtype.kind != "f" or STRICT:
    np.testing.assert_array_equal(actual, expected, err_msg=label)
    return
  rtol = 1e-12 if actual.dtype == np.float64 else 1e-6
  np.testing.assert_array_equal(np.isnan(actual), np.isnan(expected), err_msg=label)
  np.testing.assert_array_equal(np.isinf(actual), np.isinf(expected), err_msg=label)
  np.testing.assert_allclose(actual, expected, rtol=rtol, atol=1e-30, err_msg=label)


def test_ocb_roundtrip_is_exact_and_deterministic(tmp_path):
  arrays = {"a": np.arange(12, dtype=np.float32).reshape(3, 4), "b": np.array([1, 2], np.uint16),
            "c/d": np.zeros((0, 3), dtype=np.float64)}
  first, second = tmp_path / "one.ocb", tmp_path / "two.ocb"
  write_ocb(first, arrays, {"k": [1, 2]})
  write_ocb(second, dict(reversed(list(arrays.items()))), {"k": [1, 2]})
  assert first.read_bytes() == second.read_bytes()
  read, meta = read_ocb(first)
  assert meta == {"k": [1, 2]}
  assert set(read) == set(arrays)
  for key, value in arrays.items():
    np.testing.assert_array_equal(read[key], value)
    assert read[key].dtype == value.dtype


def test_baseline_records_its_provenance():
  assert META["kind"] == "mvp-original"
  assert META["source"]["commit"] == baseline.ORIGINAL_COMMIT
  assert set(META["source"]["files"]) == set(baseline.ORIGINAL_SOURCES)
  for path, digest in META["source"]["files"].items():
    original = baseline.git_show(baseline.ORIGINAL_COMMIT, path)
    if original is None:
      pytest.skip("original commit is not available in this checkout")
    assert baseline.sha256(original) == digest, path


def test_every_decision_branch_is_covered_by_the_corpus():
  reached = {flag for info in META["scenarios"].values() for flag in info["reached"]}
  assert reached == set(FLAGS) - set(META["unreachable_flags"])
  for name, info in META["scenarios"].items():
    assert set(info["expect"]) <= set(info["reached"]), name
    flags = ARRAYS[f"s/{name}/dec/flags"]
    assert reached_flags(flags) == info["reached"], name


def test_corpus_still_produces_the_recorded_inputs():
  for name, scenario in build_corpus(include_terrain=False).items():
    stored = baseline.load_scenario(ARRAYS, META, name)
    np.testing.assert_array_equal(scenario.vertices, stored.vertices, err_msg=name)
    np.testing.assert_array_equal(scenario.indices, stored.indices, err_msg=name)
    np.testing.assert_array_equal(scenario.K, stored.K, err_msg=name)
    np.testing.assert_array_equal(scenario.pose, stored.pose, err_msg=name)
    for key, value in scenario.observations.items():
      assert value.dtype == stored.observations[key].dtype, (name, key)
      np.testing.assert_array_equal(value, stored.observations[key], err_msg=f"{name}/{key}")


@pytest.mark.parametrize("name", SCENARIOS)
def test_current_implementation_reproduces_the_original_outputs(name):
  scenario = baseline.load_scenario(ARRAYS, META, name)
  stored = baseline.stored_results(ARRAYS, name)
  with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    core = evaluate_core(scenario, AmodalReasoner)
    decisions = capture_decisions(scenario, AmodalReasoner)
  for key, value in core.items():
    assert_same(value, stored[key], f"{name}/{key}")
  for key, value in decisions.items():
    if not key.startswith("dec/_"):
      assert_same(value, stored[key], f"{name}/{key}")
