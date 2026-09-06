#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Check that every non-unit test declares a unique, well-formed Jira Zephyr test ID.

Collects tests with ``pytest --collect-only`` and requires each one to declare
``@pytest.mark.test_name("NEX-T#####")``. Every violation fails the check.

Fails on:
  - missing_id: test declares no test_name marker
  - invalid_id: marker value doesn't match the pattern ``NEX-T#####``
  - duplicate_id: test declares a Zephyr test ID already used by another test
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_PYTEST = os.path.join(REPO_ROOT, "tests", ".venv", "bin", "pytest")
COLLECT_PLUGIN_DIR = os.path.join(REPO_ROOT, "tests", "scripts")

# Unit tests are out of scope for this check
TEST_ROOT = os.path.join(REPO_ROOT, "tests")
EXCLUDED_DIRS = [os.path.join(TEST_ROOT, "sscape_tests")]

ZEPHYR_ID_RE = re.compile(r"^NEX-T\d{5,6}$")

MISSING_ID = "missing_id"
INVALID_ID = "invalid_id"
DUPLICATE_ID = "duplicate_id"

ALL_CATEGORIES = [MISSING_ID, INVALID_ID, DUPLICATE_ID]

CATEGORY_HELP = {
  MISSING_ID: 'test declares no @pytest.mark.test_name("NEX-T#####")',
  INVALID_ID: "test_name marker value is not a valid NEX-T##### key",
  DUPLICATE_ID: "one Zephyr ID is claimed by more than one test",
}

log = logging.getLogger("zephyr")


def collect_tests(pytest_bin):
  """Return the collected test records produced by the zephyr_collect plugin."""
  if not os.path.exists(pytest_bin):
    raise SystemExit(f"ERROR: pytest not found at {pytest_bin}; run 'make setup-pytest'")

  handle, out_path = tempfile.mkstemp(prefix="zephyr-collect-", suffix=".json")
  os.close(handle)
  cmd = [pytest_bin, TEST_ROOT, "--collect-only", "-q",
         "-p", "no:cacheprovider", "-p", "zephyr_collect",
         f"--zephyr-out={out_path}"]
  for path in EXCLUDED_DIRS:
    cmd.extend(["--ignore", path])

  env = dict(os.environ)
  env["PYTHONPATH"] = os.pathsep.join(
    [COLLECT_PLUGIN_DIR] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))

  log.debug("Running: %s", " ".join(cmd))
  try:
    result = subprocess.run(cmd, cwd=REPO_ROOT, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, check=False)
    if result.returncode != 0:
      sys.stderr.write(result.stdout)
      raise SystemExit(f"ERROR: pytest collection failed (exit {result.returncode})")
    with open(out_path, encoding="utf-8") as collected:
      return json.load(collected)
  finally:
    if os.path.exists(out_path):
      os.remove(out_path)


def logical_tests(records):
  """Collapse parametrized variants into one entry unless they carry distinct IDs."""
  by_function = {}
  for record in records:
    by_function.setdefault(record["function_nodeid"], []).append(record)

  tests = []
  for function_nodeid, variants in by_function.items():
    if len({variant["zephyr_id"] for variant in variants}) == 1:
      tests.append(dict(variants[0], key=function_nodeid))
    else:
      tests.extend(dict(variant, key=variant["nodeid"]) for variant in variants)
  return sorted(tests, key=lambda test: test["key"])


def find_violations(tests):
  """Apply the marker rules and return the violations by category."""
  violations = {category: {} for category in ALL_CATEGORIES}
  claims = {}

  for test in tests:
    zephyr_id = test["zephyr_id"]
    if not zephyr_id:
      violations[MISSING_ID][test["key"]] = ""
      continue
    if not ZEPHYR_ID_RE.match(zephyr_id):
      violations[INVALID_ID][test["key"]] = f" (declares \"{zephyr_id}\")"
      continue
    claims.setdefault(zephyr_id, []).append(test["key"])

  for zephyr_id, keys in claims.items():
    if len(keys) > 1:
      violations[DUPLICATE_ID][zephyr_id] = " claimed by " + ", ".join(sorted(keys))

  return violations


def report(violations):
  """Print all violations and return the total failure count."""
  failures = 0
  for category in ALL_CATEGORIES:
    current = violations.get(category, {})
    print(f"\n{category.upper()}: {len(current)} ({CATEGORY_HELP[category]})")
    for entry in sorted(current):
      print(f"  FAIL  {entry}{current[entry]}")
    failures += len(current)
  return failures


def build_argparser():
  parser = argparse.ArgumentParser(
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    description="Check that every non-unit pytest test declares a unique Zephyr test ID")
  parser.add_argument("--pytest", default=DEFAULT_PYTEST,
                      help="pytest executable used for collection")
  parser.add_argument("--debug", action="store_true", help="verbose logging")
  return parser


def main():
  args = build_argparser().parse_args()
  logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                      format="%(levelname)s %(message)s")

  print("==> Checking Zephyr test IDs...")
  tests = logical_tests(collect_tests(args.pytest))
  print(f"Collected {len(tests)} tests (unit tests excluded)")

  violations = find_violations(tests)
  failures = report(violations)

  if failures:
    print(f"\nFAIL: {failures} Zephyr ID violation(s). Every test outside "
          "tests/sscape_tests must declare a unique "
          "@pytest.mark.test_name(\"NEX-T#####\").")
    return 1

  print("\nDONE ==> Checking Zephyr test IDs")
  return 0


if __name__ == "__main__":
  try:
    sys.exit(main())
  except KeyboardInterrupt:
    sys.exit(130)
