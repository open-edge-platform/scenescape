#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Test helper utilities for tracker service tests.

Provides polling helpers for event-driven testing without fixed sleeps.
"""

from waiting import wait


# Default timeouts for polling
DEFAULT_TIMEOUT = 10
POLL_INTERVAL = 0.1


def is_tracker_ready(docker):
  """Check if tracker /readyz endpoint returns healthy."""
  try:
    result = docker.compose.execute(
        "tracker",
        ["/scenescape/tracker", "healthcheck", "--endpoint", "/readyz"],
        tty=False
    )
    return "OK" in result or result.strip() == ""
  except Exception:
    return False


def wait_for_readiness(docker, timeout=DEFAULT_TIMEOUT):
  """Wait until tracker /readyz returns 200."""
  wait(lambda: is_tracker_ready(docker), timeout_seconds=timeout, sleep_seconds=POLL_INTERVAL)


def get_broker_host(docker, port=1883):
  """Get broker hostname accessible from test host."""
  containers = docker.compose.ps()
  for container in containers:
    if "-broker-" in container.name:
      ports = container.network_settings.ports
      port_key = f"{port}/tcp"
      if port_key in ports and ports[port_key]:
        return "localhost", int(ports[port_key][0]["HostPort"])
  return "localhost", port


def get_container_logs(docker, service):
  """Get container logs for debugging."""
  try:
    return docker.compose.logs(service)
  except Exception as e:
    return f"Failed to get logs: {e}"
