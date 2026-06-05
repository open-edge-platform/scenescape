#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Detect and report flaky tests from pytest-rerunfailures output.

SceneScape runs its service-dependent suites (functional, UI, metric, BAT) with
``pytest --reruns`` so transient infrastructure hiccups (container start-up
races, MQTT/broker timing, Selenium timeouts) do not fail an otherwise healthy
pipeline. A test that *fails first and then passes on a retry* is flaky: it is
silently re-run, which can hide real instability if nobody looks.

This script reads the captured pytest log(s), finds every test that was retried
(``RERUN`` entries), and emits a flaky-test report so those tests are surfaced
and tracked instead of being quietly masked. It is intended to run in CI right
after the test step, writing a human-readable report and, when running in GitHub
Actions, a job-summary section.

Usage:
  report_flaky_tests.py LOG [LOG ...] [--output report.txt] [--strict]

Exit status is 0 by default (reporting is informational). With ``--strict`` it
returns 1 when any flaky test is detected, so a team can choose to gate on it.
"""

import argparse
import os
import re
import sys

# Matches a pytest node id, e.g. tests/functional/test_roi.py::test_create[full_stack].
# Node ids contain no whitespace, so stop at the first space to avoid swallowing
# the trailing "RERUN" token or the " - reason" suffix.
NODE_ID_RE = re.compile(r"[\w./-]+\.py(?:::\S+)?")
# pytest-rerunfailures emits "RERUN" both in live progress and the -r R summary.
RERUN_LINE_RE = re.compile(r"\bRERUN\b")


def extract_flaky_tests(log_paths):
  """Return a sorted set of test node ids that were retried (flaky)."""
  flaky = set()
  for path in log_paths:
    if not os.path.isfile(path):
      continue
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
      for line in handle:
        if not RERUN_LINE_RE.search(line):
          continue
        match = NODE_ID_RE.search(line)
        if match:
          flaky.add(match.group(0).rstrip(".,"))
  return sorted(flaky)


def write_github_summary(flaky):
  """Append a flaky-test section to the GitHub Actions job summary, if present."""
  summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
  if not summary_path:
    return
  with open(summary_path, "a", encoding="utf-8") as handle:
    handle.write("## 🔁 Flaky tests (passed only after retry)\n\n")
    if flaky:
      handle.write(f"{len(flaky)} test(s) were retried this run:\n\n")
      for node in flaky:
        handle.write(f"- `{node}`\n")
      handle.write("\nInvestigate and stabilize these, or mark them "
                   "`@pytest.mark.flaky(reruns=N)` with a tracking issue.\n")
    else:
      handle.write("No flaky tests detected in this run.\n")


def build_argparser():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("logs", nargs="+", help="pytest output log file(s) to scan")
  parser.add_argument("--output", help="write the flaky report to this file")
  parser.add_argument("--strict", action="store_true",
                      help="exit non-zero when flaky tests are detected")
  return parser


def main():
  args = build_argparser().parse_args()
  flaky = extract_flaky_tests(args.logs)

  lines = []
  if flaky:
    lines.append(f"Detected {len(flaky)} flaky test(s) (passed only after retry):")
    lines.extend(f"  - {node}" for node in flaky)
  else:
    lines.append("No flaky tests detected.")
  report = "\n".join(lines) + "\n"

  print(report, end="")
  if args.output:
    with open(args.output, "w", encoding="utf-8") as handle:
      handle.write(report)
  write_github_summary(flaky)

  if args.strict and flaky:
    return 1
  return 0


if __name__ == "__main__":
  sys.exit(main())
