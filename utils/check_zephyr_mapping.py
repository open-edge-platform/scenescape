#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Enforce a one-to-one mapping between pytest tests and Jira Zephyr test cases.

Stage A (offline) collects every non-unit pytest test via ``pytest --collect-only``
and requires each one to declare ``@pytest.mark.test_name("NEX-T#####")``.
Stage B (``--jira``) fetches the Zephyr test cases and reports IDs that exist on
only one side.

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
UTILS_DIR = os.path.join(REPO_ROOT, "utils")

DEFAULT_PYTEST = os.path.join(REPO_ROOT, "tests", ".venv", "bin", "pytest")
DEFAULT_BASELINE = os.path.join(REPO_ROOT, "tests", "zephyr_baseline.json")
DEFAULT_ENV_FILE = os.path.join(UTILS_DIR, ".env")
COLLECT_PLUGIN_DIR = os.path.join(REPO_ROOT, "tests", "scripts")

# Unit tests are out of scope; the remaining satellite suites are already
# excluded by collect_ignore_glob in tests/conftest.py.
TEST_ROOT = os.path.join(REPO_ROOT, "tests")
EXCLUDED_DIRS = [os.path.join(TEST_ROOT, "sscape_tests")]

DEFAULT_FOLDERS = [
  "/Vision_AI/SceneScape/ADMIN",
  "/Vision_AI/SceneScape/Functional Tests",
  "/Vision_AI/SceneScape/Performance Tests",
  "/Vision_AI/SceneScape/UI Tests",
]

ZEPHYR_ID_RE = re.compile(r"^NEX-T\d{5,6}$")

MISSING_ID = "missing_id"
INVALID_ID = "invalid_id"
DUPLICATE_ID = "duplicate_id"
UNKNOWN_ID = "unknown_id"
ORPHAN_ZEPHYR = "orphan_zephyr"

OFFLINE_CATEGORIES = [MISSING_ID, INVALID_ID, DUPLICATE_ID]
JIRA_CATEGORIES = [UNKNOWN_ID, ORPHAN_ZEPHYR]
ALL_CATEGORIES = OFFLINE_CATEGORIES + JIRA_CATEGORIES

CATEGORY_HELP = {
  MISSING_ID: 'test declares no @pytest.mark.test_name("NEX-T#####")',
  INVALID_ID: "test_name marker value is not a valid NEX-T##### key",
  DUPLICATE_ID: "one Zephyr ID is claimed by more than one test",
  UNKNOWN_ID: "test_name marker refers to a Zephyr case that does not exist",
  ORPHAN_ZEPHYR: "automated Zephyr case has no test in the repository",
}

log = logging.getLogger("zephyr")


def load_env_file(path):
  """Populate os.environ from a KEY=VALUE file without overriding the real env."""
  if not path or not os.path.exists(path):
    return
  with open(path, encoding="utf-8") as handle:
    for line in handle:
      line = line.strip()
      if not line or line.startswith("#") or "=" not in line:
        continue
      key, value = line.split("=", 1)
      os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


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


def find_offline_violations(tests):
  """Apply the rules that need no access to Jira."""
  violations = {category: {} for category in OFFLINE_CATEGORIES}
  claims = {}

  for test in tests:
    zephyr_id = test["zephyr_id"]
    if not zephyr_id:
      hint = ""
      if test.get("module_test_name"):
        hint = (f" (module declares TEST_NAME = \"{test['module_test_name']}\"; "
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


def find_jira_violations(claims, token, folders):
  """Compare the IDs claimed by the repo against the Zephyr test cases."""
  sys.path.insert(0, UTILS_DIR)
  import libraries.jira as jira  # noqa: E402  (env must be loaded before import)

  client = jira.Jira(token)
  cases = client.get_tests_in_folder(
    folders, fields="name,key,status,customFields,labels")
  log.info("Retrieved %d Zephyr test cases from %d folder(s)", len(cases), len(folders))

  by_key = {case["key"]: case for case in cases if case.get("key")}
  violations = {category: {} for category in JIRA_CATEGORIES}

  for zephyr_id, keys in claims.items():
    if zephyr_id not in by_key:
      violations[UNKNOWN_ID][zephyr_id] = " claimed by " + ", ".join(sorted(keys))

  for key, case in by_key.items():
    if key not in claims and jira.Jira.is_automated(case):
      name = (case.get("name") or "").strip()
      violations[ORPHAN_ZEPHYR][key] = f" ({name})" if name else ""

  return violations


def load_baseline(path):
  if not os.path.exists(path):
    return {category: set() for category in ALL_CATEGORIES}
  with open(path, encoding="utf-8") as handle:
    data = json.load(handle)
  return {category: set(data.get(category, [])) for category in ALL_CATEGORIES}


def write_baseline(path, violations, categories, previous):
  """Rewrite the baseline, keeping categories this run did not evaluate."""
  data = {category: sorted(violations.get(category, {})) if category in categories
          else sorted(previous.get(category, set()))
          for category in ALL_CATEGORIES}
  with open(path, "w", encoding="utf-8") as handle:
    json.dump(data, handle, indent=2)
    handle.write("\n")


def report(violations, baseline, categories, allow_stale):
  """Print the diff against the baseline and return the number of failures."""
  failures = 0
  for category in categories:
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
    description="Check that every non-unit pytest test maps 1:1 to a Jira Zephyr test case")
  parser.add_argument("--pytest", default=DEFAULT_PYTEST,
                      help="pytest executable used for collection")
  parser.add_argument("--baseline", default=DEFAULT_BASELINE,
                      help="JSON file holding the accepted backlog of violations")
  parser.add_argument("--update-baseline", action="store_true",
                      help="rewrite the baseline from the current violations")
  parser.add_argument("--jira", action="store_true",
                      help="also compare against Jira; needs JIRA_TOKEN in the environment")
  parser.add_argument("--folder", default=os.getenv("ZEPHYR_FOLDERS"),
                      help="comma-separated Zephyr folders to look test cases up in; "
                           "subfolders must be listed explicitly")
  parser.add_argument("--env-file", default=DEFAULT_ENV_FILE,
                      help="file with the JIRA_* settings, ignored when missing")
  parser.add_argument("--debug", action="store_true", help="verbose logging")
  return parser


def main():
  args = build_argparser().parse_args()
  logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                      format="%(levelname)s %(message)s")
  load_env_file(args.env_file)

  print("==> Checking pytest to Jira Zephyr traceability...")
  tests = logical_tests(collect_tests(args.pytest))
  print(f"Collected {len(tests)} tests (unit tests excluded)")

  violations, claims = find_offline_violations(tests)
  baseline = load_baseline(args.baseline)
  evaluated = list(OFFLINE_CATEGORIES)

  failures = report(violations, baseline, OFFLINE_CATEGORIES, args.update_baseline)
  if failures and not args.update_baseline:
    print(f"\nFAIL: {failures} Zephyr ID violation(s). Every test outside "
          f"tests/sscape_tests must declare @pytest.mark.test_name(\"NEX-T#####\").")
    return 1

  if args.jira:
    token = os.getenv("JIRA_TOKEN")
    if not token:
      print("\nJIRA_TOKEN is not set; skipping the Jira comparison")
    else:
      folders = [part.strip() for part in (args.folder or "").split(",") if part.strip()]
      violations.update(find_jira_violations(claims, token, folders or DEFAULT_FOLDERS))
      evaluated.extend(JIRA_CATEGORIES)
      failures += report(violations, baseline, JIRA_CATEGORIES, args.update_baseline)

  if args.update_baseline:
    write_baseline(args.baseline, violations, evaluated, baseline)
    skipped = [category for category in ALL_CATEGORIES if category not in evaluated]
    if skipped:
      print(f"\nKept the existing baseline for {', '.join(skipped)} "
            f"(not evaluated; re-run with --jira to refresh)")
    print(f"\nWrote baseline to {args.baseline}")
    return 0

  if failures:
    print(f"\nFAIL: {failures} Zephyr mapping violation(s)")
    return 1

  print("\nDONE ==> Checking pytest to Jira Zephyr traceability")
  return 0


if __name__ == "__main__":
  try:
    sys.exit(main())
  except KeyboardInterrupt:
    sys.exit(130)
