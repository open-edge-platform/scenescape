#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Remind PR authors to review Manager's OpenAPI spec after API code changes."""

import argparse
import os
import subprocess
from pathlib import Path


SPEC_PATH = "docs/user-guide/api-docs/api.yaml"
MANAGER_RUNTIME_FILES = {"manager/Dockerfile", "manager/requirements-runtime.txt"}


def changed_files(base, head):
  result = subprocess.check_output([
    "git", "diff", "--no-renames", "--name-only", "-z", f"{base}...{head}", "--",
  ])
  return {path for path in result.decode("utf-8", "surrogateescape").split("\0") if path}


def reminder(paths):
  api_files = [
    path for path in paths
    if (path.startswith("manager/src/") and path.endswith(".py"))
    or path.startswith("manager/config/") or path in MANAGER_RUNTIME_FILES
  ]
  if not api_files or SPEC_PATH in paths:
    return None
  return (
    f"{len(api_files)} Manager API-affecting file(s) changed but {SPEC_PATH} did not. "
    "Review the API contract and update the spec if behavior changed; "
    "otherwise confirm in the PR description that the spec was reviewed."
  )


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("base", help="PR base commit SHA")
  parser.add_argument("head", help="PR head commit SHA")
  args = parser.parse_args()

  message = reminder(changed_files(args.base, args.head))
  if message:
    print(f"::warning file={SPEC_PATH}::{message}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
      with Path(summary).open("a", encoding="utf-8") as summary_file:
        summary_file.write(f"### Manager API spec review\n\n{message}\n")
  else:
    print("No Manager API spec review reminder needed.")


if __name__ == "__main__":
  main()
