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
  ImageBuildRequirements(name="autocalibration", make_target="autocalibration", time_limit_seconds=400, size_limit_megabytes=850.0),
  ImageBuildRequirements(name="tracker", make_target="tracker", time_limit_seconds=1500, size_limit_megabytes=40.0),
  ImageBuildRequirements(name="cluster-analytics", make_target="cluster_analytics", time_limit_seconds=600, size_limit_megabytes=330.0),
  ImageBuildRequirements(name="mapping", make_target="mapping", time_limit_seconds=360, size_limit_megabytes=1250.0),
  ImageBuildRequirements(name="analytics", make_target="analytics", time_limit_seconds=240, size_limit_megabytes=550.0),
]

@pytest.fixture(scope="module", params=IMAGES_REQUIREMENTS, ids=lambda img: img.name)
def built_image_result(request):
  image = request.param
  build_cmd = f"make {image.make_target}"

  env_extra = {"EXTRA_BUILD_ARGS": " ".join(EXTRA_BUILD_ARGS)}

  status, duration = run_command(build_cmd, env_extra)

  assert status == 0, f"{TEST_NAME}: Building {image.name} failed with exit code {status}"
  return image, duration

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

<<<<<<< Updated upstream
@pytest.mark.test_name("NEX-T12520")
@pytest.mark.parametrize("image", IMAGES_REQUIREMENTS, ids=lambda img: img.name)
def test_build_time_and_size(record_xml_attribute, image):
  record_xml_attribute("name", f"{TEST_NAME}-{image.name}")
=======
def test_build_time(record_xml_attribute, built_image_result):
  image, duration = built_image_result
  record_xml_attribute("name", f"{TEST_NAME}-{image.name}-time")
>>>>>>> Stashed changes

  assert duration <= image.time_limit_seconds, (
    f"{TEST_NAME}: Building {image.name} took {duration:.2f}s (limit is {image.time_limit_seconds}s)"
  )

def test_image_size(record_xml_attribute, built_image_result):
  image, _ = built_image_result
  record_xml_attribute("name", f"{TEST_NAME}-{image.name}-size")

  built_image = docker.image.inspect(f"intel/scenescape-{image.name}")

  assert (built_image.size / 10**6) <= image.size_limit_megabytes, (
    f"{TEST_NAME}: Built {image.name} image size is {(built_image.size / 10**6):.2f}MB (limit is {image.size_limit_megabytes}MB)"
  )
