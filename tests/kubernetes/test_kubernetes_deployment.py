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
import secrets
import socket
import subprocess
import time
from pathlib import Path

import pytest
import requests

try:
  from utils.log import get_logger
  logger = get_logger(__name__)
except ImportError:
  logger = logging.getLogger(__name__)


@pytest.mark.kubernetes_only
@pytest.mark.test_name("NEX-T29214")
def test_scenescape_installation(_k8s_manager, result_recorder):
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

  hooks = subprocess.run(
    ["helm", "get", "hooks", "scenescape",
     "--namespace", "scenescape",
     "--kubeconfig", _k8s_manager.kubeconfig],
    capture_output=True, text=True, check=True,
  )
  assert not hooks.stdout.strip(), "Hook resources remain in the release"

  pvcs = subprocess.run(
    ["kubectl", "get", "pvc",
     "--namespace", "scenescape",
     "--kubeconfig", _k8s_manager.kubeconfig,
     "--output", "json"],
    capture_output=True, text=True, check=True,
  )
  pvc_names = {claim["metadata"]["name"] for claim in json.loads(pvcs.stdout)["items"]}
  expected_pvcs = {
    "scenescape-datasets-pvc",
    "scenescape-media-pvc",
    "scenescape-migrations-pvc",
    "scenescape-models-pvc",
  }
  assert expected_pvcs <= pvc_names, f"Missing PVCs: {expected_pvcs - pvc_names}"
  unbound_pvcs = {
    claim["metadata"]["name"] for claim in json.loads(pvcs.stdout)["items"]
    if claim["metadata"]["name"] in expected_pvcs
    and claim.get("status", {}).get("phase") != "Bound"
  }
  assert not unbound_pvcs, f"PVCs are not bound: {unbound_pvcs}"

  jobs = subprocess.run(
    ["kubectl", "get", "jobs",
     "--namespace", "scenescape",
     "--kubeconfig", _k8s_manager.kubeconfig,
     "--selector", "app=scenescape-model-download",
     "--output", "json"],
    capture_output=True, text=True, check=True,
  )
  model_jobs = json.loads(jobs.stdout)["items"]
  assert model_jobs, "Model download Job was not installed"
  assert any(job.get("status", {}).get("succeeded", 0) == 1 for job in model_jobs), (
    "Model download Job has not completed successfully"
  )

  web = subprocess.run(
    ["kubectl", "get", "deployment", "scenescape-web-dep",
     "--namespace", "scenescape",
     "--kubeconfig", _k8s_manager.kubeconfig,
     "--output", "json"],
    capture_output=True, text=True, check=True,
  )
  init_containers = json.loads(web.stdout)["spec"]["template"]["spec"]["initContainers"]
  init_names = {container["name"] for container in init_containers}
  assert "wait-for-model-download" in init_names
  assert "model-download" not in init_names
  result_recorder.success()


@pytest.mark.kubernetes_only
@pytest.mark.test_name("NEX-T29218")
def test_scenescape_helm_uninstall_cleans_resources(_k8s_manager, result_recorder):
  """Verify Helm uninstall removes release-managed claims and model resources."""
  token = secrets.token_hex(4)
  release = f"cleanup-{token}"
  namespace = release
  kubeconfig = _k8s_manager.kubeconfig
  chart_path = str(Path(_k8s_manager._repo_root) / "kubernetes" / "scenescape-chart")
  test_password = secrets.token_hex(24)
  release_may_exist = True

  try:
    subprocess.run(
      ["helm", "install", release, chart_path,
       "--namespace", namespace,
       "--create-namespace",
       "--kubeconfig", kubeconfig,
       "--timeout", "120s",
       "--set-string", f"supass={test_password}",
       "--set-string", f"pgserver.password={test_password}"],
      capture_output=True, text=True, check=True,
    )

    expected_pvcs = {
      f"{release}-datasets-pvc",
      f"{release}-media-pvc",
      f"{release}-migrations-pvc",
      f"{release}-models-pvc",
      f"{release}-netvlad-pvc",
      f"pgserver-storage-{release}-pgserver-0",
    }
    deadline = time.monotonic() + 120
    pvc_names = set()
    while time.monotonic() < deadline:
      pvc_result = subprocess.run(
        ["kubectl", "get", "pvc",
         "--namespace", namespace,
         "--kubeconfig", kubeconfig,
         "--output", "json"],
        capture_output=True, text=True, check=True,
      )
      pvc_names = {
        claim["metadata"]["name"]
        for claim in json.loads(pvc_result.stdout)["items"]
      }
      if expected_pvcs <= pvc_names:
        break
      time.sleep(2)
    assert expected_pvcs <= pvc_names, f"Temporary release is missing PVCs: {expected_pvcs - pvc_names}"

    jobs_result = subprocess.run(
      ["kubectl", "get", "jobs",
       "--namespace", namespace,
       "--kubeconfig", kubeconfig,
       "--selector", f"app={release}-model-download",
       "--output", "json"],
      capture_output=True, text=True, check=True,
    )
    job_names = {
      job["metadata"]["name"]
      for job in json.loads(jobs_result.stdout)["items"]
    }
    assert job_names, "Temporary release did not create a model download Job"

    configmap_name = f"{release}-model-download"
    subprocess.run(
      ["kubectl", "get", "configmap", configmap_name,
       "--namespace", namespace,
       "--kubeconfig", kubeconfig],
      capture_output=True, text=True, check=True,
    )
    expected_resources = expected_pvcs | job_names | {configmap_name}

    subprocess.run(
      ["helm", "uninstall", release,
       "--namespace", namespace,
       "--kubeconfig", kubeconfig],
      capture_output=True, text=True, check=True,
    )
    release_may_exist = False

    deadline = time.monotonic() + 120
    remaining = set()
    while time.monotonic() < deadline:
      resources_result = subprocess.run(
        ["kubectl", "get", "pvc,jobs,configmaps",
         "--namespace", namespace,
         "--kubeconfig", kubeconfig,
         "--output", "json"],
        capture_output=True, text=True, check=True,
      )
      resource_names = {
        item["metadata"]["name"]
        for item in json.loads(resources_result.stdout)["items"]
      }
      remaining = expected_resources & resource_names
      if not remaining:
        break
      time.sleep(2)
    assert not remaining, f"Release resources remain after uninstall: {remaining}"
    result_recorder.success()
  finally:
    if release_may_exist:
      subprocess.run(
        ["helm", "uninstall", release,
         "--namespace", namespace,
         "--kubeconfig", kubeconfig],
        capture_output=True, text=True, check=False,
      )
    subprocess.run(
      ["kubectl", "delete", "namespace", namespace,
       "--kubeconfig", kubeconfig,
       "--wait=true", "--timeout=180s"],
      capture_output=True, text=True, check=False,
    )


@pytest.mark.kubernetes_only
@pytest.mark.test_name("NEX-T29366")
def test_kubeclient_spawns_dlstreamer_pipelines(_k8s_manager, result_recorder):
  """Verify kubeclient creates available DL Streamer deployments for demo cameras."""
  result = subprocess.run(
    ["kubectl", "get", "deployments",
     "--namespace", "scenescape",
     "--kubeconfig", _k8s_manager.kubeconfig,
     "--selector", "release=scenescape",
     "--output", "json"],
    capture_output=True, text=True, check=True,
  )
  deployments = json.loads(result.stdout)["items"]
  pipelines = [
    deployment for deployment in deployments
    if "videoppl" in deployment["metadata"]["name"]
  ]
  assert pipelines, "kubeclient did not create any DL Streamer pipeline deployments"

  unavailable = [
    deployment["metadata"]["name"] for deployment in pipelines
    if deployment["status"].get("availableReplicas", 0) < 1
  ]
  logger.info(
    "Found %d kubeclient-created DL Streamer pipeline deployment(s): %s",
    len(pipelines), ", ".join(deployment["metadata"]["name"] for deployment in pipelines),
  )
  assert not unavailable, (
    "kubeclient-created DL Streamer pipeline deployments are not available: "
    + ", ".join(unavailable)
  )
  result_recorder.success()


@pytest.mark.test_name("NEX-T29215")
def test_scenescape_pods_not_restarting(_k8s_manager, result_recorder):
  """Verify core Scenescape pods don't restart within a 2-minute window.

  NTP (chrony) is excluded because it crashes in KinD due to missing
  capabilities (SYS_TIME). It is not required for functional test execution.
  """
  kubeconfig = _k8s_manager.kubeconfig

  # Pods whose restarts we ignore (known KinD-incompatible services)
  _EXCLUDED_SUFFIXES = ("-ntpserv", "-kubeclient")

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
  result_recorder.success()


@pytest.mark.kubernetes_only
@pytest.mark.test_name("NEX-T29216")
def test_scenescape_web_app_accessible(_k8s_manager, result_recorder):
  """Verify the web application responds with HTTP 200."""
  url = f"https://localhost:{_k8s_manager.web_port}"
  logger.info("Checking web app accessibility at %s", url)
  response = requests.get(url, verify=False)
  logger.info("Web app response: HTTP %d", response.status_code)
  assert response.status_code == 200
  result_recorder.success()


@pytest.mark.kubernetes_only
@pytest.mark.test_name("NEX-T29217")
def test_scenescape_mqtt_accessible(_k8s_manager, result_recorder):
  """Verify the MQTT broker is reachable on the port-forwarded port."""
  logger.info("Checking MQTT broker accessibility on localhost:%d", _k8s_manager.mqtt_port)
  with socket.create_connection(("localhost", _k8s_manager.mqtt_port), timeout=5) as sock:
    assert sock is not None, "Failed to connect to MQTT broker"
  logger.info("MQTT broker is reachable")
  result_recorder.success()
