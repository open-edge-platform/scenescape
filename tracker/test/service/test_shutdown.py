#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Graceful shutdown test for tracker service.

Validates that the tracker service handles SIGTERM correctly.
"""

from python_on_whales import DockerClient


def test_graceful_shutdown(tracker_service):
  """
  Test that tracker service shuts down gracefully on SIGTERM.

  Verification:
  - Container exits with code 0 (not 137/killed)
  - Shutdown completes within timeout
  - Logs contain graceful shutdown message
  """
  docker = DockerClient()
  context = tracker_service

  # Get tracker container
  tracker_container = None
  for container in context["containers"]:
    if "-tracker-" in container.name:
      tracker_container = container
      break

  assert tracker_container is not None, "Tracker container not found"

  # Verify service is running before shutdown
  container_info = docker.container.inspect(tracker_container.id)
  assert container_info.state.running, "Tracker should be running before shutdown test"

  print(f"\nSending SIGTERM to tracker (docker stop)...")

  # Send SIGTERM via docker stop (5s timeout matches stop_grace_period)
  docker.container.stop(tracker_container.id, time=5)

  # Inspect container after stop
  container_info = docker.container.inspect(tracker_container.id)

  # Verify exit code is 0 (graceful), not 137 (killed by SIGKILL)
  exit_code = container_info.state.exit_code
  assert exit_code == 0, \
      f"Expected exit code 0 (graceful shutdown), got {exit_code}. " \
      f"Exit code 137 means SIGKILL (timeout exceeded)."

  # Check logs for graceful shutdown message
  logs = docker.container.logs(tracker_container.id)
  assert "shutting down gracefully" in logs.lower(), \
      f"Expected 'shutting down gracefully' in logs. Got:\n{logs[-500:]}"

  print(f"Tracker shut down gracefully (exit code: {exit_code})")
