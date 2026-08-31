#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Smoke checks for Ubuntu 26.04 / Python 3.14 container base assumptions.

These run on the host against built images (no pytest container fixtures).
They catch regressions in base OS, interpreter version, and apt Open3D packaging.
"""

import json
import shutil
import subprocess
import sys

import pytest

TEST_NAME = "NEX-T28253"

IMAGES = [
  "intel/scenescape-controller:latest",
  "intel/scenescape-manager:latest",
  "intel/scenescape-autocalibration:latest",
  "intel/scenescape-analytics:latest",
  "intel/scenescape-cluster-analytics:latest",
  "intel/scenescape-mapping:latest",
]

OPEN3D_IMAGES = [
  "intel/scenescape-controller:latest",
  "intel/scenescape-manager:latest",
  "intel/scenescape-autocalibration:latest",
  "intel/scenescape-analytics:latest",
  "intel/scenescape-mapping:latest",
]


def _docker_available():
  return shutil.which("docker") is not None


def _image_exists(image):
  result = subprocess.run(
    ["docker", "image", "inspect", image],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    check=False,
  )
  return result.returncode == 0


def _run_in_image(image, python_code):
  cmd = [
    "docker", "run", "--rm", "--entrypoint", "python3", image,
    "-c", python_code,
  ]
  return subprocess.run(cmd, capture_output=True, text=True, check=False)


@pytest.mark.skipif(not _docker_available(), reason="docker not available")
@pytest.mark.parametrize("image", IMAGES)
def test_image_reports_python_314(image):
  """Positive: runtime images ship Python 3.14 from Ubuntu 26.04."""
  if not _image_exists(image):
    pytest.skip(f"image not built: {image}")
  result = _run_in_image(
    image,
    "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
  )
  assert result.returncode == 0, result.stderr
  assert result.stdout.strip() == "3.14"


@pytest.mark.skipif(not _docker_available(), reason="docker not available")
@pytest.mark.parametrize("image", IMAGES)
def test_image_os_release_is_ubuntu_2604(image):
  """Positive: base OS is Ubuntu 26.04 (Resolute)."""
  if not _image_exists(image):
    pytest.skip(f"image not built: {image}")
  result = subprocess.run(
    ["docker", "run", "--rm", "--entrypoint", "bash", image, "-lc",
     "grep -E '^(ID|VERSION_ID)=' /etc/os-release"],
    capture_output=True, text=True, check=False,
  )
  assert result.returncode == 0, result.stderr
  assert "ID=ubuntu" in result.stdout
  assert 'VERSION_ID="26.04"' in result.stdout


@pytest.mark.skipif(not _docker_available(), reason="docker not available")
@pytest.mark.parametrize("image", OPEN3D_IMAGES)
def test_open3d_importable_from_apt_package(image):
  """Positive: Open3D comes from apt python3-open3d and imports cleanly."""
  if not _image_exists(image):
    pytest.skip(f"image not built: {image}")
  result = _run_in_image(
    image,
    "import open3d as o3d; "
    "assert hasattr(o3d.geometry, 'get_rotation_matrix_from_xyz'); "
    "print(o3d.__version__)",
  )
  assert result.returncode == 0, result.stderr
  assert result.stdout.strip().startswith("0.19")


@pytest.mark.skipif(not _docker_available(), reason="docker not available")
def test_controller_core_imports():
  """Positive: controller image can import scene_common + robot_vision + requests."""
  image = "intel/scenescape-controller:latest"
  if not _image_exists(image):
    pytest.skip(f"image not built: {image}")
  result = _run_in_image(
    image,
    "import scene_common, controller, robot_vision, numpy, requests; "
    "from scene_common.rest_client import RESTClient; "
    "print(numpy.__version__, requests.__version__)",
  )
  assert result.returncode == 0, result.stderr


@pytest.mark.skipif(not _docker_available(), reason="docker not available")
@pytest.mark.parametrize("image", [
  "intel/scenescape-controller:latest",
  "intel/scenescape-analytics:latest",
  "intel/scenescape-cluster-analytics:latest",
  "intel/scenescape-autocalibration:latest",
])
def test_scene_common_rest_client_importable(image):
  """Positive: services that ship scene_common can import RESTClient (needs requests)."""
  if not _image_exists(image):
    pytest.skip(f"image not built: {image}")
  result = _run_in_image(
    image,
    "from scene_common.rest_client import RESTClient; import requests; print('ok')",
  )
  assert result.returncode == 0, result.stderr
  assert result.stdout.strip() == "ok"


@pytest.mark.skipif(not _docker_available(), reason="docker not available")
def test_negative_python311_site_packages_path_absent_in_controller():
  """Negative: legacy python3.11 site-packages path must not be the install root."""
  image = "intel/scenescape-controller:latest"
  if not _image_exists(image):
    pytest.skip(f"image not built: {image}")
  result = subprocess.run(
    ["docker", "run", "--rm", "--entrypoint", "bash", image, "-lc",
     "test ! -d /usr/local/lib/python3.11/site-packages/scene_common; "
     "test -d /usr/local/lib/python3.14/dist-packages/scene_common; "
     "echo ok"],
    capture_output=True, text=True, check=False,
  )
  assert result.returncode == 0, result.stderr
  assert result.stdout.strip() == "ok"
