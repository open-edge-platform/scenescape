import logging
import pytest
from pytest_kubernetes.providers.base import AClusterManager
from pathlib import Path
from pytest_kubernetes.options import ClusterOptions
import subprocess
import os
from python_on_whales import docker


kind_config_path = Path(__file__).parent / Path("config/kind_config.yaml")
ingress = Path(__file__).parent / Path("config/ingress.yaml")
ingress_controller = "https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml"
certmanager_path = "https://github.com/cert-manager/cert-manager/releases/download/v1.18.2/cert-manager.yaml"
chart_path = str(Path(__file__).parent.parent.parent / Path("kubernetes/scenescape-chart"))

@pytest.fixture(scope='session')
def kind_cluster(k8s_manager):
  k8s: AClusterManager = k8s_manager("kind")("pytest-test-cluster")
  k8s.create(cluster_options=ClusterOptions(
    cluster_name="pytest-test-cluster",
    provider_config=kind_config_path)
  )

  # Apply ingress resources
  k8s.apply(ingress)

  # Patch kubernetes api service for kubeclient
  k8s.wait("svc/kubernetes", "jsonpath='{.status.phase}'!=<none>", timeout=120)
  k8s.kubectl("patch", "service", "kubernetes", "--type=merge", "-p", '{"spec": {"ports": [{"name": "https", "port": 6443, "targetPort": 6443}]}}')

  # Install Nginx Ingress Controller
  k8s.apply()

  k8s.apply(certmanager_path)
  yield k8s

  logging.info("Deleting kind cluster...")
#   k8s.delete()

@pytest.fixture(scope='session')
def scenescape_deployment(kind_cluster, values_file):
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
          "--timeout", "1200s",
          "-f", values_file
      ]

      result = subprocess.run(cmd, capture_output=True, text=True, check=True)
      logging.debug(f"Helm chart deployed: {result.stdout}")

      # Return deployment info
      deployment_info = {
          "release_name": release_name,
          "namespace": namespace,
          "chart_path": chart_path
      }

      logging.debug(f"Scenescape deployment info: {deployment_info}")

      yield deployment_info

  finally:
     logging.info("Cleaning up Helm release and namespace...")
#       subprocess.run([
#           "kubectl", "get", "pod", "-A", "--kubeconfig", kubeconfig
#       ], check=False)
#       # Cleanup: Uninstall the Helm chart
#       subprocess.run([
#           "helm", "uninstall", release_name, "--namespace", namespace, "--kubeconfig", kubeconfig
#       ], check=False)

#       # Optionally delete the namespace
#       subprocess.run([
#           "kubectl", "delete", "namespace", namespace, "--ignore-not-found=true", "--kubeconfig", kubeconfig
#       ], check=False)

def load_scenescape_images(kind_cluster):
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
def values_file(tmp_path_factory):
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