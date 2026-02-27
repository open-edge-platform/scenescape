#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
OpenTelemetry lifecycle test for tracker service.

Validates that the tracker initializes the OTel SDK, connects to the
OTLP collector, and shuts down cleanly on SIGTERM.
"""

from python_on_whales import DockerClient

from utils.docker import get_container_logs


def test_telemetry_lifecycle(tracker_service_otel):
  """
  Test full OpenTelemetry SDK lifecycle: init → connect → shutdown.

  Phase 1: Verify tracker initialized metrics and tracing providers
           (tracker logs).
  Phase 2: Verify collector is running and accepting connections
           (otel-collector logs).
  Phase 3: Send SIGTERM, verify clean shutdown with telemetry flush
           (tracker logs + exit code 0).
  """
  docker_compose = tracker_service_otel["docker"]

  # Phase 1: Verify OTel initialization in tracker logs
  print("\nPhase 1: Checking OTel initialization...")
  tracker_logs = get_container_logs(docker_compose, "tracker")
  assert "OpenTelemetry metrics initialized" in tracker_logs, \
      f"Expected metrics init log. Tracker logs:\n{tracker_logs[-1000:]}"
  assert "OpenTelemetry tracing initialized" in tracker_logs, \
      f"Expected tracing init log. Tracker logs:\n{tracker_logs[-1000:]}"
  print("  ✓ Metrics and tracing initialized")

  # Phase 2: Verify collector is running and OTLP endpoint is active
  print("\nPhase 2: Checking collector readiness...")
  collector_logs = get_container_logs(docker_compose, "otel-collector")
  assert "Starting GRPC server" in collector_logs, \
      f"Expected GRPC server start log. Collector logs:\n{collector_logs[-1000:]}"
  assert "Everything is ready" in collector_logs, \
      f"Expected ready log. Collector logs:\n{collector_logs[-1000:]}"
  print("  ✓ Collector OTLP endpoint active")

  # Phase 3: Graceful shutdown with telemetry flush
  print("\nPhase 3: Testing graceful shutdown...")
  docker = DockerClient()
  tracker_container = None
  for container in tracker_service_otel["containers"]:
    if "-tracker-" in container.name:
      tracker_container = container
      break

  assert tracker_container is not None, "Tracker container not found"

  docker.container.stop(tracker_container.id, time=5)
  container_info = docker.container.inspect(tracker_container.id)

  exit_code = container_info.state.exit_code
  assert exit_code == 0, \
      f"Expected exit code 0, got {exit_code}"

  logs = docker.container.logs(tracker_container.id)
  assert "OpenTelemetry metrics shut down" in logs, \
      f"Expected metrics shutdown log. Logs:\n{logs[-1000:]}"
  assert "OpenTelemetry tracing shut down" in logs, \
      f"Expected tracing shutdown log. Logs:\n{logs[-1000:]}"
  print(f"  ✓ Telemetry shut down cleanly (exit code: {exit_code})")
