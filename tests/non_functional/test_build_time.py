# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import os
import shlex
import subprocess
import time

logger = logging.getLogger(__name__)

TEST_NAME= "NEX-T12520"

def run_command(command, description, timed=False):
  logger.info(f"Running {description} command: {command}")
  start_time = time.time() if timed else None

  cmd = command if isinstance(command, (list, tuple)) else shlex.split(command)
  process = subprocess.Popen(
    cmd,
    cwd=os.getcwd(),
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
  )

  for line in process.stdout:
    logger.debug(line.rstrip())

  process.wait()

  duration = time.time() - start_time if timed else 0.0
  return process.returncode, duration



def test_build_time(record_xml_attribute):

  time_limit = int(os.getenv("BUILD_TIME_LIMIT", "600"))
  build_cmd = os.getenv("BUILD_CMD", "make build-core")
  record_xml_attribute("name", TEST_NAME)

  returncode, duration = run_command(build_cmd, "build", timed=True)
  assert returncode == 0, f"{TEST_NAME}: build command failed with exit code {returncode}"

  logger.info(f"Build completed in {duration:.2f}s")
  assert duration < time_limit, (
    f"{TEST_NAME}: Build took {duration:.2f}s (limit is {time_limit}s)"
  )
