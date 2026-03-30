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

from waiting import wait

logger = logging.getLogger("test.containers")


def container_is_ready(docker, project_name, service, log_pattern):
  """Check if a container's logs contain the readiness pattern.

  Also checks Docker health status as a fallback, mirroring the bash
  logic in test_utils.sh:38-39.
  """
  container_name = f"{project_name}-{service}-1"
  try:
    logs = docker.container.logs(container_name)
    if re.search(log_pattern, logs):
      return True
    inspect = docker.container.inspect(container_name)
    health = getattr(inspect.state, "health", None)
    if health and health.status == "healthy":
      return True
  except Exception:
    pass
  return False


def wait_for_services(docker, project_name, wait_for):
  """Wait for all specified services to become ready.

  Args:
    docker: python-on-whales DockerClient.
    project_name: Compose project name (used to form container names).
    wait_for: dict of {service_name: WaitConfig} from profiles.py.
  """
  for service, config in wait_for.items():
    logger.info("  Waiting up to %ds for %s...", config.timeout, service)
    wait(
      lambda svc=service, pat=config.log_pattern: container_is_ready(
        docker, project_name, svc, pat
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

