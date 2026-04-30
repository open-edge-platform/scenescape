#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Container readiness polling, log collection, and traceback scanning.

Replicates the wait_for_container() function from tests/test_utils.sh
and the log/traceback scanning from tests/runtest.
"""

import logging
import re
from datetime import datetime, timedelta, timezone

from waiting import wait

logger = logging.getLogger("test.containers")


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
      logger.debug("%s: container not running (state=%s)", service, state.status)
      return False

    # Check Docker health status
    health = getattr(state, "health", None)
    if health:
      if health.status == "healthy":
        logger.debug("%s: Docker health check passed", service)
        return True
      elif health.status == "starting":
        logger.debug("%s: Docker health check still starting", service)
        return False
      # If health status is "unhealthy", fall through to log check

    # Check container logs for readiness pattern
    logs = docker.container.logs(container_name, since=since)
    if logs and re.search(log_pattern, logs):
      logger.debug("%s: readiness pattern found in logs", service)
      return True

    logger.debug("%s: no readiness indicator yet", service)
  except Exception as exc:
    logger.debug("%s: readiness check exception: %s", service, exc)

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
    logger.info("  Waiting up to %ds for %s...", config.timeout, service)
    wait(
      lambda svc=service, pat=config.log_pattern, s=since: container_is_ready(
        docker, project_name, svc, pat, since=s
      ),
      timeout_seconds=config.timeout,
      sleep_seconds=1,
    )
    logger.info("  %s is ready.", service)


def collect_logs(docker, services=None, scan_for_tracebacks=False):
  """Log container output for the given services (or all if None).

  When scan_for_tracebacks is True, also checks each container's logs
  for Python tracebacks in a single pass (avoids fetching logs twice).
  """
  tracebacks_found = []
  try:
    containers = docker.compose.ps()
    for container in containers:
      if services and not any(svc in container.name for svc in services):
        continue
      logger.info("\n--- logs: %s ---", container.name)
      logs = docker.container.logs(container.name)
      for line in logs.splitlines():
        logger.info("%s", line)
      if scan_for_tracebacks and "Traceback" in logs:
        tracebacks_found.append(container.name)
        logger.warning("Found Traceback in %s!", container.name)
  except Exception as exc:
    logger.warning("Error collecting logs: %s", exc)
  if tracebacks_found:
    logger.warning("Tracebacks found in: %s", ", ".join(tracebacks_found))
  return tracebacks_found

