#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
NTP service tests for tracker.

Test tracker's NTP offset calculation (RFC 5905) by:
- Comparing the tracker's computed offset against ntplib (a reference
  Python implementation of the same RFC 5905 formula), both querying the
  same Chrony NTP server container.
"""

import re
import uuid
import ntplib
import pytest
from pathlib import Path
from python_on_whales import DockerClient
from waiting import wait, TimeoutExpired

from utils.docker import (
    wait_for_readiness,
    get_container_logs,
    get_ntp_server_port,
    POLL_INTERVAL,
)

# Tolerance for offset comparison between tracker (C++) and ntplib (Python).
# Both implement RFC 5905; the difference reflects only the time between the
# two independent queries over the Docker-local network.
_OFFSET_TOLERANCE_S = 0.005

# Timeout to wait for the tracker to log its first NTP sync line.
_NTP_SYNC_TIMEOUT_S = 60


@pytest.fixture(scope="function")
def tracker_service_ntp(tls_certs):
  """
  Starts tracker with a Chrony NTP server (dockurr/chrony:4.8, same as production).
  Tracker is configured with TRACKER_NTP_SERVER=ntp-server so it syncs on startup.
  """
  service_dir = Path(__file__).parent
  compose_file = service_dir / "docker-compose.yaml"

  project_name = f"tracker-ntp-{uuid.uuid4().hex[:8]}"

  env_file = tls_certs.temp_dir / ".env"
  env_file.write_text(
      f"TLS_CA_CERT_FILE={tls_certs.ca.cert_path}\n"
      f"TLS_SERVER_CERT_FILE={tls_certs.server.cert_path}\n"
      f"TLS_SERVER_KEY_FILE={tls_certs.server.key_path}\n"
      f"TLS_CLIENT_CERT_FILE={tls_certs.client.cert_path}\n"
      f"TLS_CLIENT_KEY_FILE={tls_certs.client.key_path}\n"
      f"TRACKER_MQTT_INSECURE=true\n"
      f"TRACKER_SCENES_SOURCE=file\n"
      f"TRACKER_NTP_SERVER=ntp-server\n"
      f"TRACKER_NTP_SYNC_INTERVAL_S=60\n"
  )

  docker = DockerClient(
      compose_files=[compose_file],
      compose_project_name=project_name,
      compose_project_directory=str(service_dir),
      compose_env_files=[str(env_file)],
      compose_profiles=["ntp"],
  )

  try:
    print(f"\nStarting NTP test environment: {project_name}")
    # Start ntp-server first so Chrony is ready before the tracker fires its
    # first NTP sync attempt, avoiding a 60-second retry delay.
    docker.compose.up(services=["ntp-server"], detach=True, wait=True)
    docker.compose.up(detach=True, wait=False)

    try:
      wait_for_readiness(docker, timeout=30)
    except TimeoutExpired:
      print("\nTracker failed to become ready. Logs:")
      print("--- Tracker logs ---")
      print(get_container_logs(docker, "tracker"))
      print("--- NTP server logs ---")
      print(get_container_logs(docker, "ntp-server"))
      raise

    yield {"docker": docker}

  finally:
    print(f"\nCleaning up: {project_name}")
    docker.compose.down(remove_orphans=True, volumes=True)


def _wait_for_ntp_log(docker, timeout=_NTP_SYNC_TIMEOUT_S):
  """Poll tracker logs until an NTP sync line appears or timeout expires."""
  logs = None

  def ntp_log_present():
    nonlocal logs
    logs = get_container_logs(docker, "tracker")
    return "NTP sync: offset=" in logs

  wait(ntp_log_present, timeout_seconds=timeout, sleep_seconds=POLL_INTERVAL)
  return logs


def test_ntp_offset_matches_reference_implementation(tracker_service_ntp):
  """
  Positive test: tracker's RFC 5905 offset agrees with ntplib reference.

  Both implement: offset = ((T2 - T1) + (T3 - T4)) / 2
  Queries the same ntp-server container independently and compares results.
  """
  docker = tracker_service_ntp["docker"]

  try:
    logs = _wait_for_ntp_log(docker)
  except TimeoutExpired:
    print("\nNo NTP sync log found. Tracker logs:")
    print(get_container_logs(docker, "tracker"))
    pytest.fail("Tracker did not log an NTP sync within the expected timeout")

  match = re.search(r"NTP sync: offset=([+-]?\d+\.\d+)s", logs)
  assert match, f"Could not parse offset from NTP sync log line.\nLogs:\n{logs}"
  tracker_offset = float(match.group(1))

  host, port = get_ntp_server_port(docker)
  ntp_client = ntplib.NTPClient()
  try:
    response = ntp_client.request(host, port=port, version=4)
  except ntplib.NTPException as exc:
    pytest.fail(f"ntplib failed to query ntp-server at {host}:{port}: {exc}")

  ntplib_offset = response.offset

  diff = abs(tracker_offset - ntplib_offset)
  print(
      f"\nNTP offset comparison:"
      f"\n  tracker : {tracker_offset:+.6f}s"
      f"\n  ntplib  : {ntplib_offset:+.6f}s"
      f"\n  diff    : {diff:.6f}s (tolerance {_OFFSET_TOLERANCE_S}s)"
  )
  assert diff < _OFFSET_TOLERANCE_S, (
      f"Tracker offset ({tracker_offset:.6f}s) and ntplib offset "
      f"({ntplib_offset:.6f}s) differ by {diff:.6f}s, "
      f"which exceeds tolerance of {_OFFSET_TOLERANCE_S}s"
  )
