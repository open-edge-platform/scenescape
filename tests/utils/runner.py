#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
In-container test execution.

Runs "docker run" via python-on-whales with the same volume mounts, environment variables,
and user/group handling.
"""

import os
from pathlib import Path

from utils import stream_subprocess


APPDIR = "/workspace"
MODELDIR = "/opt/intel/openvino/deployment_tools/intel_models"
SAMPLE_DATA_DIR = "/home/scenescape/SceneScape/sample_data"


def run_test_in_container(
  image,
  command,
  repo_root,
  project_name,
  network=None,
  extra_env=None,
):
  """Run a test command inside a Docker container.

  Args:
    image: Full Docker image name (e.g. "scenescape-manager-test:2026.0.0").
    command: List of strings for the test command
        (e.g. ["pytest", "-s", "tests/functional/tc_roi_mqtt.py", ...]).
    repo_root: Absolute path to the repository root on the host.
    project_name: Compose project name for volume name resolution.
    network: Docker network to connect to (e.g. "test-abc12345_scenescape-test").
    extra_env: Optional dict of additional environment variables.

  Returns:
    Exit code of the container process.
  """
  repo_root = str(Path(repo_root).resolve())
  secrets_dir = f"{repo_root}/manager/secrets"

  volumes = [
    (repo_root, APPDIR, "rw"),
    (f"{project_name}_vol-models", MODELDIR, "rw"),
    (f"{project_name}_vol-sample-data", SAMPLE_DATA_DIR, "rw"),
    (secrets_dir, "/run/secrets", "ro"),
  ]

  env = {
    "PYTHONPATH": APPDIR,
    "PROJECT": project_name,
    "SECRETSDIR": "/run/secrets",
    "HOSTDIR": repo_root,
  }

  # Proxy vars
  for var in ("http_proxy", "https_proxy", "no_proxy"):
    val = os.environ.get(var)
    if val:
      env[var] = val

  if extra_env:
    env.update(extra_env)

  # Image-specific user/group handling (scenescape-start:128-135)
  uid = os.getuid()
  gid = os.getgid()
  user = None
  extra_run_args = []

  if "controller-test" in image:
    user = f"{uid}:{gid}"
  elif "manager-test" in image:
    user = str(uid)
    extra_run_args.extend(["--userns", "host"])
    volumes.extend([
      (f"{repo_root}/manager/secrets",
       "/home/scenescape/SceneScape/manager/secrets", "ro"),
      (f"{repo_root}/manager/secrets/django/secrets.py",
       "/home/scenescape/SceneScape/manager/secrets.py", "ro"),
    ])

  # Build the raw docker run command to handle flags like --userns
  # that python-on-whales doesn't expose as keyword arguments.
  run_cmd = [
    "docker", "run", "--rm",
    "--privileged",
    "--cap-add=SYS_ADMIN",
    "--cap-add=SYS_PTRACE",
    f"--workdir={APPDIR}",
  ]

  if user:
    run_cmd.extend(["--user", user])

  for flag in extra_run_args:
    run_cmd.append(flag)

  if network:
    run_cmd.extend(["--network", network])

  for src, dst, mode in volumes:
    run_cmd.append(f"--volume={src}:{dst}:{mode}")

  for key, val in env.items():
    run_cmd.extend(["-e", f"{key}={val}"])

  run_cmd.append(image)
  run_cmd.extend(command)

  return stream_subprocess(run_cmd, check=False)


def run_unit_test(image, command, repo_root):
  """Run a unit test in a standalone container (no compose network).

  Simpler variant for tests using the unit-recipe pattern that only need
  the test image with repo + secrets mounts.

  Args:
    image: Full Docker image name.
    command: List of strings for the test command.
    repo_root: Absolute path to the repository root on the host.

  Returns:
    Exit code.
  """
  return run_test_in_container(
    image=image,
    command=command,
    repo_root=repo_root,
    project_name="scenescape",
    network=None,
  )
