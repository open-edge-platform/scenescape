# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import os
from pathlib import Path
import shlex
import subprocess
import time
from python_on_whales import docker
import pytest

logger = logging.getLogger(__name__)

TEST_NAME= "NEX-T12520"

BUILD_WORKING_DIR = Path(__file__).resolve().parents[2]

EXTRA_BUILD_ARGS = [
  "--no-cache"
]

class ImageBuildRequirements:
  def __init__(self, name : str, make_target : str, time_limit_seconds : int, size_limit_megabytes: float):
    self.name = name
    self.make_target = make_target
    self.time_limit_seconds = time_limit_seconds
    self.size_limit_megabytes = size_limit_megabytes

IMAGES_REQUIREMENTS = [
  ImageBuildRequirements(name="common-base", make_target="build-common", time_limit_seconds=120, size_limit_megabytes=400.0),
  ImageBuildRequirements(name="manager", make_target="manager", time_limit_seconds=360, size_limit_megabytes=600.0),
  ImageBuildRequirements(name="controller", make_target="controller", time_limit_seconds=400, size_limit_megabytes=660.0),
  ImageBuildRequirements(name="autocalibration", make_target="autocalibration", time_limit_seconds=400, size_limit_megabytes=825.0),
  ImageBuildRequirements(name="tracker", make_target="tracker", time_limit_seconds=1500, size_limit_megabytes=40.0),
]

def build_image_check(image : ImageBuildRequirements) -> None:
  build_cmd = f"make {image.make_target}"

  env_extra = {"EXTRA_BUILD_ARGS": " ".join(EXTRA_BUILD_ARGS)}

  status, duration = run_command(build_cmd, env_extra)

  assert status == 0, f"{TEST_NAME}: Building {image.name} failed with exit code {status}"
  assert duration <= image.time_limit_seconds, (
    f"{TEST_NAME}: Building {image.name} took {duration:.2f}s (limit is {image.time_limit_seconds}s)"
  )

  built_image = docker.image.inspect(f"intel/scenescape-{image.name}")

  assert (built_image.size / 10**6) <= image.size_limit_megabytes, (
    f"{TEST_NAME}: Built {image.name} image size is {(built_image.size / 10**6):.2f}MB (limit is {image.size_limit_megabytes}MB)"
  )

def run_command(command, env_extra=None) -> tuple[int, float]:
  logger.info(f"Running command: {command} inside {BUILD_WORKING_DIR}")
  start_time = time.time()

  cmd = command if isinstance(command, (list, tuple)) else shlex.split(command)
  run_env = {**os.environ, **(env_extra or {})}
  process = subprocess.Popen(
      cmd, cwd=BUILD_WORKING_DIR, env=run_env,
      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
  )

  for line in process.stdout:
    logger.debug(line.rstrip())

  process.wait()

  duration = time.time() - start_time
  return process.returncode, duration

@pytest.mark.parametrize("image", IMAGES_REQUIREMENTS, ids=lambda img: img.name)
def test_build_time_and_size(record_xml_attribute, image):
  record_xml_attribute("name", f"{TEST_NAME}-{image.name}")

  build_image_check(image)
