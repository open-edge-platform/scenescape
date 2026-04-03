import json
import subprocess
import time
import socket
import requests
from pytest_kubernetes.providers.base import AClusterManager
from conftest import DeploymentInfo

def test_kubernetes_version(kind_cluster : AClusterManager):
    assert kind_cluster.version() == (1, 25)

def test_scenescape_installation(scenescape_deployment : DeploymentInfo, kind_cluster : AClusterManager):
    kubeconfig = str(kind_cluster.kubeconfig)
    result = subprocess.run(
        ["helm", "status", scenescape_deployment.release_name,
         "--namespace", scenescape_deployment.namespace,
         "--kubeconfig", kubeconfig,
         "--output", "json"],
        capture_output=True, text=True, check=True
    )
    status = json.loads(result.stdout)
    assert status["info"]["status"] == "deployed"


def _get_restart_counts(kubeconfig : str, namespace : str):
    result = subprocess.run(
        ["kubectl", "get", "pods",
         "--namespace", namespace,
         "--kubeconfig", kubeconfig,
         "-o", "json"],
        capture_output=True, text=True, check=True
    )
    pods = json.loads(result.stdout)["items"]
    return {
        f"{pod['metadata']['name']}/{c['name']}": c["restartCount"]
        for pod in pods
        for c in pod["status"].get("containerStatuses", [])
    }


def test_scenescape_pods_not_restarting_after_5min(scenescape_deployment : DeploymentInfo, kind_cluster : AClusterManager):
    kubeconfig = str(kind_cluster.kubeconfig)
    namespace = scenescape_deployment.namespace

    before = _get_restart_counts(kubeconfig, namespace)
    assert len(before) > 0, "No containers found in namespace"

    time.sleep(300)

    after = _get_restart_counts(kubeconfig, namespace)

    new_restarts = [
        f"{name}: {before.get(name, 0)} -> {count}"
        for name, count in after.items()
        if count > before.get(name, 0)
    ]
    assert not new_restarts, "Containers restarted during the 5 minute window:\n" + "\n".join(new_restarts)

def test_scenescape_web_app_accessible(web_app_port : int, root_cert : str):
    response = requests.get(f"https://localhost:{web_app_port}", verify=str(root_cert),)
    assert response.status_code == 200

def test_scenescape_autocalibration_accessible(autocalibration_port : int, root_cert : str):
    response = requests.get(f"https://localhost:{autocalibration_port}", verify=str(root_cert),)
    assert response.status_code == 200

def test_scenescape_mqtt_accessible(mqtt_port : int):
    with socket.create_connection(("localhost", mqtt_port), timeout=5) as sock:
        assert sock is not None, "Failed to connect to MQTT broker"

def test_scenescape_mqtt_insecure_accessible(mqtt_insecure_port : int):
    with socket.create_connection(("localhost", mqtt_insecure_port), timeout=5) as sock:
        assert sock is not None, "Failed to connect to MQTT broker on insecure port"