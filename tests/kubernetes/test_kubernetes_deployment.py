import json
import subprocess
import time

import pytest


def test_kubernetes_version(kind_cluster):
    assert kind_cluster.version() == (1, 25)

def test_scenescape_installation(scenescape_deployment, kind_cluster):
    kubeconfig = str(kind_cluster.kubeconfig)
    result = subprocess.run(
        ["helm", "status", scenescape_deployment["release_name"],
         "--namespace", scenescape_deployment["namespace"],
         "--kubeconfig", kubeconfig,
         "--output", "json"],
        capture_output=True, text=True, check=True
    )
    status = json.loads(result.stdout)
    assert status["info"]["status"] == "deployed"


def _get_restart_counts(kubeconfig, namespace):
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


def test_scenescape_pods_not_restarting_after_5min(scenescape_deployment, kind_cluster):
    kubeconfig = str(kind_cluster.kubeconfig)
    namespace = scenescape_deployment["namespace"]

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


# def test_dlstreamer_running(scenescape_deployment, kind_cluster):
#     kubeconfig = str(kind_cluster.kubeconfig)
#     result = subprocess.run(
#         ["kubectl", "get", "pods",
#          "--namespace", scenescape_deployment["namespace"],
#          "--kubeconfig", kubeconfig,
#          "-l", "app.kubernetes.io/name=dlstreamer",
#          "-o", "json"],
#         capture_output=True, text=True, check=True
#     )
#     pods = json.loads(result.stdout)
#     assert len(pods["items"]) > 0
#     for pod in pods["items"]:
#         assert pod["status"]["phase"] == "Running"
