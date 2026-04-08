# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import base64
import logging
import pytest
from pytest_kubernetes.providers.base import AClusterManager
from pathlib import Path
from pytest_kubernetes.options import ClusterOptions
import subprocess
import os
from python_on_whales import docker
import json
from pytest_kubernetes.portforwarding import PortForwarding
import base64

kind_config_path = Path(__file__).parent / Path("config/kind_config.yaml")
ingress = Path(__file__).parent / Path("config/ingress.yaml")
ingress_controller = "https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml"
certmanager_path = "https://github.com/cert-manager/cert-manager/releases/download/v1.18.2/cert-manager.yaml"
chart_path = str(Path(__file__).parent.parent.parent / Path("kubernetes/scenescape-chart"))

class DeploymentInfo:
  def __init__(self, release_name: str, namespace: str, chart_path: str):
    self.release_name = release_name
    self.namespace = namespace
    self.chart_path = chart_path

@pytest.fixture(scope='session')
def kind_cluster(k8s_manager) -> AClusterManager:
  k8s: AClusterManager = k8s_manager("kind")("pytest-test-cluster")
  k8s.create(cluster_options=ClusterOptions(
    cluster_name="pytest-test-cluster",
    provider_config=kind_config_path)
  )

  # Apply ingress resources
  k8s.apply(ingress)

  # Patch kubernetes api service for kubeclient
  patch = json.dumps({"spec": {"ports": [{"name": "https", "port": 6443, "targetPort": 6443}]}})
  k8s.kubectl(["patch", "svc", "kubernetes", "--type=merge", f"-p='{patch}'"])

  # Install Nginx Ingress Controller
  k8s.apply(ingress_controller)

  k8s.apply(certmanager_path)
  yield k8s

  logging.info("Deleting kind cluster...")
  k8s.delete()

@pytest.fixture(scope='session')
def scenescape_deployment(kind_cluster : AClusterManager, values_file : str) -> DeploymentInfo:
  kubeconfig = str(kind_cluster.kubeconfig)
  chart_location = chart_path
  namespace = "scenescape"
  release_name = "scenescape"

  load_scenescape_images(kind_cluster)

  # Create namespace if it doesn't exist
  subprocess.run([
      "kubectl", "create", "namespace", namespace, "--kubeconfig", kubeconfig], check=False)

  try:
      # Deploy the Helm chart
      cmd = [
          "helm", "install", release_name, chart_location,
          "--namespace", namespace,
          "--kubeconfig", kubeconfig,
          "--wait",
          "--timeout", "1500s",
          "-f", values_file
      ]

      result = subprocess.run(cmd, capture_output=True, text=True, check=True)
      logging.debug(f"Helm chart deployed: {result.stdout}")

      yield DeploymentInfo(release_name, namespace, chart_path)

  finally:
    logging.info("Cleaning up Helm release and namespace...")
    # subprocess.run([
    #     "kubectl", "get", "pod", "-A", "--kubeconfig", kubeconfig
    # ], check=False)
    # # Cleanup: Uninstall the Helm chart
    # subprocess.run([
    #     "helm", "uninstall", release_name, "--namespace", namespace, "--kubeconfig", kubeconfig
    # ], check=False)

    # # Optionally delete the namespace
    # subprocess.run([
    #     "kubectl", "delete", "namespace", namespace, "--ignore-not-found=true", "--kubeconfig", kubeconfig
    # ], check=False)

def load_scenescape_images(kind_cluster : AClusterManager) -> None:
    # Load the Docker images into the kind cluster
    images = [
        "scenescape-manager",
        "scenescape-autocalibration",
        "scenescape-controller",
        "scenescape-cluster-analytics",
        "scenescape-mapping"
    ]

    version_file = Path(__file__).parent.parent.parent / Path("version.txt")
    with open(version_file, "r") as f:
        version = f.read().strip()

    for image in images:
        old_tag = f"{image}:latest"
        new_tag = f"intel/{image}:{version}"
        docker.image.tag(old_tag, new_tag)
        kind_cluster.load_image(new_tag)

@pytest.fixture(scope='session')
def values_file(tmp_path_factory) -> str:
  values_file = tmp_path_factory.mktemp("scenescape") / "values.yaml"
  values_file.write_text(f"""
    supass: "demo"
    pgserver:
      password: demo
    httpProxy: \"{os.getenv("HTTP_PROXY")}\"
    httpsProxy: \"{os.getenv("HTTPS_PROXY")}\"
    noProxy: \"{os.getenv("NO_PROXY")}\"
    """)
  yield str(values_file)

@pytest.fixture(scope='session')
def controller_auth(scenescape_deployment : DeploymentInfo, kind_cluster : AClusterManager, tmp_path_factory) -> str:
  kubeconfig = str(kind_cluster.kubeconfig)
  namespace = scenescape_deployment.namespace

  auth_secret = kind_cluster.kubectl(["get", "secret", f"{scenescape_deployment.release_name}-controller.auth", "-n", namespace], as_dict = True)
  auth_encoded = auth_secret["data"]["controller.auth"]

  auth = base64.b64decode(auth_encoded).decode("utf-8")

  auth_file = tmp_path_factory.mktemp("scenescape") / "controller.auth"
  auth_file.write_text(auth)
  return str(auth_file)

@pytest.fixture(scope='session')
def root_cert(scenescape_deployment : DeploymentInfo, kind_cluster : AClusterManager, tmp_path_factory ) -> str:
  kubeconfig = str(kind_cluster.kubeconfig)
  namespace = scenescape_deployment.namespace

  cert_secret = kind_cluster.kubectl(["get", "secret", f"{scenescape_deployment.release_name}-scenescape-ca.pem", "-n", namespace], as_dict = True)
  cert_encoded = cert_secret["data"]["ca.crt"]

  cert = base64.b64decode(cert_encoded).decode("utf-8")

  cert_file = tmp_path_factory.mktemp("scenescape") / "ca.pem"
  cert_file.write_text(cert)
  return str(cert_file)

@pytest.fixture(scope='session')
def web_app_port(scenescape_deployment : DeploymentInfo, kind_cluster : AClusterManager) -> int:
  namespace = scenescape_deployment.namespace
  port_forwarding : PortForwarding = kind_cluster.port_forwarding(target="svc/web", namespace=namespace, source_port=9443, target_port=443)
  try:
    port_forwarding.start()
    started = True
    yield port_forwarding._ports[0]
  finally:
    if started:
      # port_forwarding.stop()
      logging.debug("Stopping port forwarding for web app")

@pytest.fixture(scope='session')
def autocalibration_port(scenescape_deployment : DeploymentInfo, kind_cluster : AClusterManager) -> int:
  namespace = scenescape_deployment.namespace
  port_forwarding : PortForwarding = kind_cluster.port_forwarding(target="svc/autocalibration", namespace=namespace, source_port=8443, target_port=8443)
  try:
    port_forwarding.start()
    started = True
    yield port_forwarding._ports[0]
  finally:
    if started:
      # port_forwarding.stop()
      logging.debug("Stopping port forwarding for autocalibration")

@pytest.fixture(scope='session')
def mqtt_port(scenescape_deployment : DeploymentInfo, kind_cluster : AClusterManager) -> int:
  namespace = scenescape_deployment.namespace
  port_forwarding : PortForwarding = kind_cluster.port_forwarding(target="svc/broker", namespace=namespace, source_port=1883, target_port=1883)
  try:
    port_forwarding.start()
    started = True
    yield port_forwarding._ports[0]
  finally:
    if started:
      port_forwarding.stop()

@pytest.fixture(scope='session')
def mqtt_insecure_port(scenescape_deployment : DeploymentInfo, kind_cluster : AClusterManager) -> int:
  namespace = scenescape_deployment.namespace
  port_forwarding : PortForwarding = kind_cluster.port_forwarding(target="svc/broker", namespace=namespace, source_port=1884, target_port=1884)
  try:
    port_forwarding.start()
    started = True
    yield port_forwarding._ports[0]
  finally:
    if started:
      port_forwarding.stop()

