# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Kubernetes-specific deployment smoke tests.

These tests verify that the KinD cluster and Helm deployment are healthy.
They use the unified K8sManager via the _k8s_manager fixture from conftest.py
and are marked kubernetes_only so they're skipped when --backend=docker.
"""

import json
import logging
import os
import socket
import subprocess
import time

import pytest
import requests

try:
  from utils.log import get_logger
  logger = get_logger(__name__)
except ImportError:
  logger = logging.getLogger(__name__)


@pytest.mark.kubernetes_only
def test_scenescape_installation(_k8s_manager):
  """Verify Helm release is in 'deployed' status."""
  logger.info("Checking Helm release status for 'scenescape'")
  result = subprocess.run(
    ["helm", "status", "scenescape",
     "--namespace", "scenescape",
     "--kubeconfig", _k8s_manager.kubeconfig,
     "--output", "json"],
    capture_output=True, text=True, check=True,
  )
  status = json.loads(result.stdout)
  release_status = status["info"]["status"]
  logger.info("Helm release status: %s", release_status)
  assert release_status == "deployed"


@pytest.mark.kubernetes_only
def test_scenescape_pods_not_restarting(_k8s_manager):
  """Verify core Scenescape pods don't restart within a 2-minute window.

  NTP (chrony) and dlstreamer (retail/queuing cams) are excluded because
  they crash in KinD due to missing capabilities (SYS_TIME) and GPU hardware.
  These services are not required for functional test execution.
  """
  kubeconfig = _k8s_manager.kubeconfig

  # Pods whose restarts we ignore (known KinD-incompatible services)
  _EXCLUDED_SUFFIXES = ("-ntpserv", "-retail-cams", "-queuing-cams", "-kubeclient")

  def _get_restart_counts():
    result = subprocess.run(
      ["kubectl", "get", "pods",
       "--namespace", "scenescape",
       "--kubeconfig", kubeconfig,
       "-o", "json"],
      capture_output=True, text=True, check=True,
    )
    pods = json.loads(result.stdout)["items"]
    return {
      f"{pod['metadata']['name']}/{c['name']}": c["restartCount"]
      for pod in pods
      if not any(pod["metadata"]["name"].endswith(s) for s in _EXCLUDED_SUFFIXES)
      for c in pod["status"].get("containerStatuses", [])
    }

  before = _get_restart_counts()
  assert len(before) > 0, "No core containers found in scenescape namespace"
  logger.info("Monitoring %d core containers for restarts over 2 minutes", len(before))
  for name, count in sorted(before.items()):
    logger.debug("  %s restart count: %d", name, count)

  time.sleep(120)

  after = _get_restart_counts()
  new_restarts = [
    f"{name}: {before.get(name, 0)} -> {count}"
    for name, count in after.items()
    if count > before.get(name, 0)
  ]
  if new_restarts:
    logger.error("Core containers restarted during observation:\n%s", "\n".join(new_restarts))
  else:
    logger.info("No unexpected restarts detected in %d containers", len(after))
  assert not new_restarts, (
    "Core containers restarted during 2-minute observation:\n" + "\n".join(new_restarts)
  )


@pytest.mark.kubernetes_only
def test_scenescape_web_app_accessible(_k8s_manager):
  """Verify the web application responds with HTTP 200."""
  url = f"https://localhost:{_k8s_manager.web_port}"
  logger.info("Checking web app accessibility at %s", url)
  # Verify TLS against the deployment's CA bundle when available; otherwise
  # fall back to the system trust store so the request always performs
  # certificate validation.
  cert = os.environ.get("ROOT_CERT", "/run/secrets/certs/scenescape-ca.pem")
  verify = cert if isinstance(cert, str) and cert and os.path.exists(cert) else True
  response = requests.get(url, verify=verify, timeout=30)
  logger.info("Web app response: HTTP %d", response.status_code)
  assert response.status_code == 200


@pytest.mark.kubernetes_only
def test_scenescape_mqtt_accessible(_k8s_manager):
  """Verify the MQTT broker is reachable on the port-forwarded port."""
  logger.info("Checking MQTT broker accessibility on localhost:%d", _k8s_manager.mqtt_port)
  with socket.create_connection(("localhost", _k8s_manager.mqtt_port), timeout=5) as sock:
    assert sock is not None, "Failed to connect to MQTT broker"
  logger.info("MQTT broker is reachable")
