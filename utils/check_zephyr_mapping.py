#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Check that every non-unit pytest test declares a unique Jira Zephyr test ID.

Collects tests with ``pytest --collect-only`` and requires each one to declare
``@pytest.mark.test_name("NEX-T#####")`` with a well-formed key that no other
test already claims. Jira itself is unreachable from CI, so the keys are only
validated for shape and uniqueness here; existence is checked at upload time by
``utils/upload_to_zephyr.py``.

Known violations are frozen in a baseline file that may only shrink, so new
breakage fails while the existing backlog is burned down over time.
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
DEFAULT_BASELINE = os.path.join(REPO_ROOT, "tests", "zephyr_baseline.json")
COLLECT_PLUGIN_DIR = os.path.join(REPO_ROOT, "tests", "scripts")

# Unit tests are out of scope; the remaining satellite suites are already
# excluded by collect_ignore_glob in tests/conftest.py.
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
  """Apply the marker rules and return the violations plus the claimed IDs."""
  violations = {category: {} for category in ALL_CATEGORIES}
  claims = {}

  for test in tests:
    zephyr_id = test["zephyr_id"]
    if not zephyr_id:
      legacy = test.get("local_test_name") or test.get("module_test_name")
      hint = ""
      if legacy:
        scope = "test body" if test.get("local_test_name") else "module"
        hint = (f" ({scope} declares TEST_NAME = \"{legacy}\"; "
                f"convert it to a marker)")
      violations[MISSING_ID][test["key"]] = hint
      continue
    if not ZEPHYR_ID_RE.match(zephyr_id):
      violations[INVALID_ID][test["key"]] = f" (declares \"{zephyr_id}\")"
      continue
    claims.setdefault(zephyr_id, []).append(test["key"])

  for zephyr_id, keys in claims.items():
    if len(keys) > 1:
      violations[DUPLICATE_ID][zephyr_id] = " claimed by " + ", ".join(sorted(keys))

  return violations, claims


def load_baseline(path):
  if not os.path.exists(path):
    return {category: set() for category in ALL_CATEGORIES}
  with open(path, encoding="utf-8") as handle:
    data = json.load(handle)
  return {category: set(data.get(category, [])) for category in ALL_CATEGORIES}


def write_baseline(path, violations):
  data = {category: sorted(violations.get(category, {}))
          for category in ALL_CATEGORIES}
  with open(path, "w", encoding="utf-8") as handle:
    json.dump(data, handle, indent=2)
    handle.write("\n")


def report(violations, baseline, allow_stale):
  """Print the diff against the baseline and return the number of failures."""
  failures = 0
  for category in ALL_CATEGORIES:
    current = violations.get(category, {})
    known = baseline.get(category, set())
    new = sorted(set(current) - known)
    stale = sorted(known - set(current)) if not allow_stale else []

    print(f"\n{category.upper()}: {len(current)} total, {len(new)} new "
          f"({CATEGORY_HELP[category]})")
    for entry in new:
      print(f"  NEW    {entry}{current[entry]}")
    for entry in stale:
      print(f"  STALE  {entry} — fixed; remove it from the baseline")
    failures += len(new) + len(stale)
  return failures


def build_argparser():
  parser = argparse.ArgumentParser(
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    description="Check that every non-unit pytest test declares a unique Zephyr test ID")
  parser.add_argument("--pytest", default=DEFAULT_PYTEST,
                      help="pytest executable used for collection")
  parser.add_argument("--baseline", default=DEFAULT_BASELINE,
                      help="JSON file holding the accepted backlog of violations")
  parser.add_argument("--update-baseline", action="store_true",
                      help="rewrite the baseline from the current violations")
  parser.add_argument("--debug", action="store_true", help="verbose logging")
  return parser


def main():
  args = build_argparser().parse_args()
  logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                      format="%(levelname)s %(message)s")

  print("==> Checking Zephyr test IDs...")
  tests = logical_tests(collect_tests(args.pytest))
  print(f"Collected {len(tests)} tests (unit tests excluded)")

  violations, _ = find_violations(tests)
  baseline = load_baseline(args.baseline)
  failures = report(violations, baseline, args.update_baseline)

  if args.update_baseline:
    write_baseline(args.baseline, violations)
    print(f"\nWrote baseline to {args.baseline}")
    return 0

  if failures:
    print(f"\nFAIL: {failures} Zephyr ID violation(s). Every test outside "
          f"tests/sscape_tests must declare a unique "
          f"@pytest.mark.test_name(\"NEX-T#####\").")
    return 1

  print("\nDONE ==> Checking Zephyr test IDs")
  return 0


if __name__ == "__main__":
  try:
    sys.exit(main())
  except KeyboardInterrupt:
    sys.exit(130)
