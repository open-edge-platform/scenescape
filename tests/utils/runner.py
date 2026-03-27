#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Local test execution.

Runs test scripts as local subprocesses from the host venv, with the
correct PYTHONPATH and environment variables for reaching services in
the Docker Compose stack.
"""

import os

from utils import stream_subprocess


def run_test_local(command, repo_root, secrets_dir, extra_env=None):
  """Run a test command as a local subprocess.

  Args:
    command: List of strings for the test command
        (e.g. ["pytest", "-s", "tests/functional/test_roi_mqtt.py", ...]).
    repo_root: Absolute path to the repository root.
    secrets_dir: Absolute path to the secrets directory.
    extra_env: Optional dict of additional environment variables.

  Returns:
    Exit code of the subprocess.
  """
  env = {
    **os.environ,
    "PYTHONPATH": repo_root,
    "SECRETSDIR": secrets_dir,
  }
  if extra_env:
    env.update(extra_env)
  return stream_subprocess(command, check=False, cwd=repo_root, env=env)


def run_unit_test(command, repo_root):
  """Run a unit test as a local subprocess.

  Simpler variant for standalone unit tests that only need PYTHONPATH
  pointing at the repository root.

  Args:
    command: List of strings for the test command.
    repo_root: Absolute path to the repository root.

  Returns:
    Exit code.
  """
  env = {**os.environ, "PYTHONPATH": repo_root}
  return stream_subprocess(command, check=False, cwd=repo_root, env=env)
