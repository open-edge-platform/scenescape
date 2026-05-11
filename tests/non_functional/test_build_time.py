#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import subprocess
import time


def run_command(command, description, timed=False):
  print(f"Running {description} command: {command}")
  start_time = time.time() if timed else None

  process = subprocess.Popen(
    command,
    cwd=os.getcwd(),
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    shell=True
  )

  for line in process.stdout:
    print(line, end='')

  process.wait()

  duration = time.time() - start_time if timed else 0.0
  return process.returncode, duration


def test_build_time():
  time_limit = int(os.getenv("BUILD_TIME_LIMIT", "600"))
  build_cmd = os.getenv("BUILD_CMD", "make build-core")
  test_name = os.getenv("TEST_NAME", "NEX-T12520")

  success, duration = run_command(build_cmd, "build", timed=True)
  assert success, f"{test_name}: build command failed"

  assert duration < time_limit, (
    f"{test_name}: Build took {duration:.2f}s (limit is {time_limit}s)"
  )
