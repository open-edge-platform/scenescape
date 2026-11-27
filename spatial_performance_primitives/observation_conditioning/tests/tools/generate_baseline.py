#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Freeze the original MVP's behavior on the scenario corpus into an OCB1 baseline.

Run it in the test container (`make baseline-original`). It runs the original MVP from the
`*.py.backup` copies and refuses to run when they differ from the recorded original commit.
"""

import argparse
import sys
import warnings
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE / "tests"))
sys.path.insert(0, str(PACKAGE.parent / "frustum_gaussian" / "python"))
warnings.simplefilter("ignore")

import numpy as np  # noqa: E402

from oc_corpus import baseline  # noqa: E402
from oc_corpus.capture import capture_decisions, evaluate_core, reached_flags  # noqa: E402
from oc_corpus.legacy import BACKUPS, load_legacy  # noqa: E402
from oc_corpus.ocb import write_ocb  # noqa: E402
from oc_corpus.scenarios import build_corpus  # noqa: E402


def require_original_sources():
  """The legacy backups must be byte-identical to the original commit's files."""
  for backup in BACKUPS:
    path = f"spatial_performance_primitives/observation_conditioning/{backup.name[:-len('.backup')]}"
    original = baseline.git_show(baseline.ORIGINAL_COMMIT, path)
    if original is None or original != backup.read_bytes():
      raise SystemExit(f"{backup.name} differs from {path} at {baseline.ORIGINAL_COMMIT}")


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--out", required=True, type=Path)
  args = parser.parse_args()
  require_original_sources()
  AmodalReasoner = load_legacy().AmodalReasoner

  arrays, scenarios_meta = {}, {}
  for name, scenario in build_corpus().items():
    core = evaluate_core(scenario, AmodalReasoner)
    decisions = capture_decisions(scenario, AmodalReasoner)
    # Instrumentation must not change a single bit of the result.
    np.testing.assert_array_equal(decisions["dec/_depth"], core["out/depth"])
    np.testing.assert_array_equal(decisions["dec/_var"], core["out/var"])
    reached = reached_flags(decisions["dec/flags"])
    missing = [flag for flag in scenario.expect if flag not in reached]
    if missing:
      raise SystemExit(f"scenario {name} does not reach {missing} (reached {reached})")
    arrays.update(baseline.pack_scenario(scenario, core, decisions))
    scenarios_meta[name] = baseline.scenario_meta(scenario, reached)
    print(f"{name:26s} objects={scenarios_meta[name]['objects']:4d} reached={reached}")

  all_reached = {flag for info in scenarios_meta.values() for flag in info["reached"]}
  from oc_corpus.scenarios import FLAGS
  uncovered = set(FLAGS) - all_reached - set(baseline.UNREACHABLE_FLAGS)
  if uncovered:
    raise SystemExit(f"corpus never raises {sorted(uncovered)}")
  write_ocb(args.out, arrays, baseline.baseline_meta(scenarios_meta))
  print(f"wrote {args.out} ({args.out.stat().st_size / 1024:.0f} KiB)")


if __name__ == "__main__":
  main()
