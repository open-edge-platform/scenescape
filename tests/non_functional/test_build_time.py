#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import os
import subprocess
import time

logger = logging.getLogger(__name__)


def run_command(command, description, timed=False):
  logger.info(f"Running {description} command: {command}")
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
    logger.debug(line.rstrip())

  process.wait()

  duration = time.time() - start_time if timed else 0.0
  return process.returncode, duration


def test_build_time():
  time_limit = int(os.getenv("BUILD_TIME_LIMIT", "600"))
  build_cmd = os.getenv("BUILD_CMD", "make build-core")
  test_name = os.getenv("TEST_NAME", "NEX-T12520")

  returncode, duration = run_command(build_cmd, "build", timed=True)
  assert returncode == 0, f"{test_name}: build command failed with exit code {returncode}"

  logger.info(f"Build completed in {duration:.2f}s")
  assert duration < time_limit, (
    f"{test_name}: Build took {duration:.2f}s (limit is {time_limit}s)"
  )