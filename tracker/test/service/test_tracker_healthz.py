#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Basic service test for tracker skeleton.

Validates tracker service health.
"""

from python_on_whales import DockerClient


def test_tracker_healthz(tracker_service):
  """
  Test that tracker service is healthy.

  Verification:
  - Service starts successfully and healthcheck passes
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

  # Verify tracker is healthy
  tracker_container = docker.container.inspect(tracker_container.id)
  assert tracker_container.state.running, \
      f"Tracker container not running: {tracker_container.state.status}"

  health = tracker_container.state.health
  assert health and health.status == "healthy", \
      f"Tracker healthcheck failed: {health.status if health else 'no healthcheck'}"

  print(f"\n✅ Tracker service is healthy")
