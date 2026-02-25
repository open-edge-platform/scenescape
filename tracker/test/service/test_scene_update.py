#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Database update notification tests for tracker service (dynamic mode).

Tests that in API (dynamic) mode, publishing to scenescape/cmd/database
triggers a graceful shutdown and Docker restart, per the design doc:
  "On notification: logs change, exits gracefully (Docker restarts the service
   which loads new config at startup)"
"""

import uuid

import paho.mqtt.client as mqtt
from waiting import wait, TimeoutExpired

from utils.docker import (
    get_broker_host,
    get_container_logs,
    is_tracker_ready,
    wait_for_readiness,
    DEFAULT_TIMEOUT,
    POLL_INTERVAL,
)

# Topic for database update notifications (matches Manager's sendUpdateCommand)
TOPIC_DATABASE_UPDATE = "scenescape/cmd/database"


def _count_startups(docker):
  """Count how many times 'Tracker service starting' appears in logs."""
  logs = get_container_logs(docker, "tracker")
  return logs.count("Tracker service starting")


def test_database_update_triggers_restart(tracker_service_api):
  """
  Test that publishing a database update notification causes graceful shutdown
  and automatic restart in API (dynamic) mode.

  Phases:
  1. Verify tracker is ready (API scenes loaded)
  2. Publish database update notification
  3. Wait for restart via log-based detection (startup count increases)
  4. Verify logs contain expected database update messages
  """
  docker = tracker_service_api["docker"]

  # Phase 1: Tracker should be ready (fixture ensures this)
  assert is_tracker_ready(docker), "Tracker should be ready in API mode"
  initial_startups = _count_startups(docker)
  assert initial_startups >= 1, "Tracker should have started at least once"
  print("\nPhase 1: Tracker ready with API-loaded scenes")

  # Phase 2: Connect to broker and publish database update notification
  host, port = get_broker_host(docker)

  client = mqtt.Client(
      callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
      client_id=f"test-update-{uuid.uuid4().hex[:8]}"
  )
  client.connect(host, port, keepalive=60)
  client.loop_start()

  try:
    result = client.publish(TOPIC_DATABASE_UPDATE, "update", qos=1)
    result.wait_for_publish()
    print("Phase 2: Published database update notification")
  finally:
    client.loop_stop()
    client.disconnect()

  # Phase 3: Wait for the tracker to restart by observing an additional
  # "Tracker service starting" entry in the logs. Docker restart: on-failure
  # restarts the container quickly (~300ms), which is too fast for health-check
  # polling to catch the brief "not ready" window. Log-based detection is
  # deterministic and avoids that race condition.
  try:
    wait(
        lambda: _count_startups(docker) > initial_startups,
        timeout_seconds=DEFAULT_TIMEOUT,
        sleep_seconds=POLL_INTERVAL
    )
    print("Phase 3: Tracker restarted after database update")
  except TimeoutExpired:
    logs = get_container_logs(docker, "tracker")
    raise AssertionError(
        f"Tracker did not restart after database update. Logs:\n{logs[-500:]}"
    )

  # Phase 4: Wait for the restarted tracker to become ready
  try:
    wait_for_readiness(docker, timeout=30)
    print("Phase 4: Restarted tracker became ready again")
  except TimeoutExpired:
    logs = get_container_logs(docker, "tracker")
    raise AssertionError(
        f"Tracker did not become ready after restart. Logs:\n{logs[-500:]}"
    )

  # Phase 5: Verify logs contain database update message
  logs = get_container_logs(docker, "tracker")
  assert "Database update received" in logs, \
      f"Expected 'Database update received' in logs. Got:\n{logs[-500:]}"
  assert "triggering restart" in logs, \
      f"Expected 'triggering restart' in logs. Got:\n{logs[-500:]}"
  assert "database update restart" in logs.lower(), \
      f"Expected 'database update restart' in logs. Got:\n{logs[-500:]}"

  print("\nAll database update restart phases passed")
