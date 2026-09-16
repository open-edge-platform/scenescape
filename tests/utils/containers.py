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


# Health statuses reported by check_service_health().
HEALTH_OK = "ok"                # running and (healthy | starting | no healthcheck)
HEALTH_UNHEALTHY = "unhealthy"  # Docker healthcheck reports unhealthy
HEALTH_STOPPED = "stopped"      # container exists but is not running
HEALTH_MISSING = "missing"      # container does not exist in the compose project
HEALTH_ERROR = "error"          # inspect raised an exception


def check_service_health(docker, project_name, service):
  """Return a coarse health status for one Compose service.

  Combines Docker container state and healthcheck status so callers get a
  single OK / not-OK signal without needing to interpret Docker internals.

  Returns:
    Tuple of (status, detail) where ``status`` is one of the HEALTH_*
    constants above and ``detail`` is a short human-readable string.
  """
  container_name = f"{project_name}-{service}-1"
  try:
    inspect = docker.container.inspect(container_name)
  except Exception as exc:
    msg = str(exc)
    if "No such container" in msg or "not found" in msg.lower():
      return HEALTH_MISSING, "container not present"
    return HEALTH_ERROR, msg

  state = inspect.state
  if not state.running:
    return HEALTH_STOPPED, f"state={state.status}"

  health = getattr(state, "health", None)
  if health is None:
    return HEALTH_OK, "running (no healthcheck)"
  if health.status == "healthy":
    return HEALTH_OK, "healthy"
  if health.status == "starting":
    return HEALTH_OK, "starting"
  if health.status == "unhealthy":
    return HEALTH_UNHEALTHY, "unhealthy"
  return HEALTH_OK, f"health={health.status}"


def check_services_health(docker, project_name, services):
  """Return a mapping of {service: (status, detail)} for each service."""
  return {
    svc: check_service_health(docker, project_name, svc)
    for svc in services
  }


def get_services_stats(docker, project_name, services):
  """Return a mapping of {service: (cpu_pct, mem_pct)} sampled via docker stats.

  Services whose containers are missing or that fail to sample are returned
  as ``None`` so callers can decide how to handle skipped entries.
  """
  result = {svc: None for svc in services}
  wanted = {f"{project_name}-{svc}-1": svc for svc in services}
  try:
    stats = docker.container.stats(containers=list(wanted.keys()))
  except Exception as exc:  # container missing, docker down, etc.
    log.debug("docker stats sampling failed: %s", exc)
    return result
  for entry in stats:
    svc = wanted.get(getattr(entry, "container_name", None))
    if svc is None:
      continue
    try:
      cpu = float(entry.cpu_percentage)
      mem = float(entry.memory_percentage)
    except (AttributeError, TypeError, ValueError):
      continue
    result[svc] = (cpu, mem)
  return result


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

