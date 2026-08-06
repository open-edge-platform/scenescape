#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Container readiness polling, log collection, and traceback scanning.

Replicates the wait_for_container() function from tests/test_utils.sh
and the log/traceback scanning from tests/runtest.
"""

import os
import re
from datetime import datetime, timedelta, timezone

from waiting import wait

from utils.log import get_logger

log = get_logger(__name__)


def _get_log_dir():
  """Return the per-test container-log directory."""
  root_logger = get_logger()
  container_dir = getattr(root_logger, "_container_log_dir", None)
  if container_dir is None:
    return None
  container_dir.mkdir(parents=True, exist_ok=True)
  return container_dir


def container_is_ready(docker, project_name, service, log_pattern, since=None):
  """Check if a container's logs contain the readiness pattern.

  Also checks Docker health status as a fallback, mirroring the bash
  logic in test_utils.sh:38-39.

  Args:
    since: Only check logs produced after this datetime.  Useful after
           a container restart to ignore stale log lines from the
           previous run.
  """
  container_name = f"{project_name}-{service}-1"
  try:
    inspect = docker.container.inspect(container_name)
    state = inspect.state

    # Check if container is running.
    if not state.running:
      log.debug("%s: container not running (state=%s)", service, state.status)
      return False

    # Check Docker health status
    health = getattr(state, "health", None)
    if health:
      if health.status == "healthy":
        log.debug("%s: Docker health check passed", service)
        return True
      elif health.status == "starting":
        log.debug("%s: Docker health check still starting", service)
        return False
      # If health status is "unhealthy", fall through to log check

    # Check container logs for readiness pattern
    logs = docker.container.logs(container_name, since=since)
    if logs and re.search(log_pattern, logs):
      log.debug("%s: readiness pattern found in logs", service)
      return True

    log.debug("%s: no readiness indicator yet", service)
  except Exception as exc:
    log.debug("%s: readiness check exception: %s", service, exc)

  return False


def wait_for_services(docker, project_name, wait_for, since=None):
  """Wait for all specified services to become ready.

  Args:
    docker: python-on-whales DockerClient.
    project_name: Compose project name (used to form container names).
    wait_for: dict of {service_name: WaitConfig} from profiles.py.
    since: Only check logs produced after this datetime (passed through
           to container_is_ready).
  """
  for service, config in wait_for.items():
    log.info(f"  Waiting up to {config.timeout}s for {service}...")
    wait(
      lambda svc=service, pat=config.log_pattern, s=since: container_is_ready(
        docker, project_name, svc, pat, since=s
      ),
      timeout_seconds=config.timeout,
      sleep_seconds=1,
    )
    log.info(f"  {service} is ready.")


def collect_logs(docker, containers=None, scan_for_tracebacks=False):
  """Log container output for selected container name patterns.

  If containers is None, logs are collected for all containers.
  Otherwise each value is treated as a substring filter against the
  full container name (e.g. "web" matches "test-xxxx-web-1").

  When scan_for_tracebacks is True, also checks each container's logs
  for Python tracebacks in a single pass (avoids fetching logs twice).
  """
  tracebacks_found = []
  log_dir = _get_log_dir()
  if log_dir is None:
    log.warning("Test log directory is not configured; skipping container log file export")

  container_filters = None
  if containers is not None:
    if isinstance(containers, str):
      container_filters = {containers}
    else:
      container_filters = set(containers)

  try:
    compose_containers = docker.compose.ps()
    for container in compose_containers:
      if container_filters and not any(f in container.name for f in container_filters):
        continue
      logs = docker.container.logs(container.name)

      if log_dir is not None:
        log_file = os.path.join(log_dir, f"{container.name}.log")
        with open(log_file, "w") as f:
          f.write(logs)
        log.info(f"[DOCKER] Logs saved: {log_file}")
      if scan_for_tracebacks and "Traceback" in logs:
        tracebacks_found.append(container.name)
        log.warning(f"Found Traceback in {container.name}!")
  except Exception as exc:
    log.warning(f"Error collecting logs: {exc}")
  if tracebacks_found:
    log.warning(f"Tracebacks found in: {', '.join(tracebacks_found)}")
  return tracebacks_found

