#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Kubernetes backend for end-to-end tests.

Provides K8sManager (parallel to _ComposeManager) that creates a KinD cluster,
deploys SceneScape via Helm, sets up port-forwarding, and extracts secrets so
tests can connect to the cluster using the same params dict as Docker tests.
"""

import base64
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("test.k8s")

_TESTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _TESTS_DIR.parent
_CHART_PATH = str(_REPO_ROOT / "kubernetes" / "scenescape-chart")
_KIND_CONFIG = _TESTS_DIR / "kubernetes" / "config" / "kind_config.yaml"
_INGRESS_YAML = _TESTS_DIR / "kubernetes" / "config" / "ingress.yaml"
_INGRESS_CONTROLLER_URL = (
  "https://raw.githubusercontent.com/kubernetes/ingress-nginx"
  "/main/deploy/static/provider/kind/deploy.yaml"
)
_CERTMANAGER_URL = (
  "https://github.com/cert-manager/cert-manager"
  "/releases/download/v1.18.2/cert-manager.yaml"
)

_RELEASE_NAME = "scenescape"
_NAMESPACE = "scenescape"

_SCENESCAPE_IMAGES = [
  "scenescape-manager",
  "scenescape-autocalibration",
  "scenescape-controller",
  "scenescape-cluster-analytics",
  "scenescape-mapping",
]

# External images needed by helm chart hooks and deployments.
# These must be pre-pulled on the host and loaded into KinD.
_EXTERNAL_IMAGES = [
  "docker.io/busybox:1.37.0",
  "docker.io/python:3.13-slim",
  "docker.io/ubuntu:22.04",
  "docker.io/linuxserver/ffmpeg:version-8.0-cli",
  "docker.io/postgres:17.6",
  "docker.io/eclipse-mosquitto:2.0.22",
  "docker.io/dockurr/chrony:4.8",
  "docker.io/curlimages/curl:8.17.0",
  "docker.io/bluenviron/mediamtx:1.14.0",
  "docker.io/intellabs/vdms:v2.12.0",
  "docker.io/intel/dlstreamer-pipeline-server:2026.1.0-20260414-weekly-ubuntu24",
]


def _run(cmd, **kwargs):
  """Run a subprocess command, raising on failure with stderr included."""
  kwargs.setdefault("check", False)
  kwargs.setdefault("capture_output", True)
  kwargs.setdefault("text", True)
  result = subprocess.run(cmd, **kwargs)
  if result.returncode != 0 and kwargs.get("check") is not False:
    raise subprocess.CalledProcessError(
      result.returncode, cmd,
      output=result.stdout, stderr=result.stderr,
    )
  if result.returncode != 0:
    cmd_str = " ".join(str(c) for c in cmd)
    stderr = result.stderr.strip() if result.stderr else ""
    stdout = result.stdout.strip() if result.stdout else ""
    msg = f"Command failed (exit {result.returncode}): {cmd_str}"
    if stderr:
      msg += f"\nSTDERR: {stderr}"
    if stdout:
      msg += f"\nSTDOUT: {stdout}"
    raise RuntimeError(msg)
  return result


@dataclass
class K8sScenescapeEnv:
  """Environment info for a Kubernetes-backed test session."""
  kubeconfig: str
  namespace: str
  release_name: str
  repo_root: str
  secrets_dir: str
  supass: str

  def restore_db(self):
    """Restore the database to baseline state via kubectl exec."""
    web_pod = self._get_pod_name("web")
    manage = "$SCENESCAPE_HOME/manage.py"

    self._kubectl_exec(web_pod, f"python {manage} flush --no-input")
    self._kubectl_exec(
      web_pod,
      f"tar xjf $EXAMPLEDB -C /tmp"
      f" && python {manage} loaddata /tmp/data.json"
      f" && rm -f /tmp/data.json /tmp/meta.json",
    )
    self._kubectl_exec(
      web_pod,
      f"find -L /run/secrets -name '*.auth'"
      f"  -exec python {manage} createuser --skip-existing {{}} \\;"
      f" && DJANGO_SUPERUSER_PASSWORD=$SUPASS"
      f"    python {manage} createsuperuser"
      f"    --no-input --username=admin"
      f"    --email=admin@domain.com 2>/dev/null || true",
    )
    self._kubectl_exec(web_pod, f"python {manage} updatedbstatus --ready")
    logger.info("Database restored.")

    # Restart scene controller to refresh cache.
    logger.info("Restarting scene controller...")
    _run([
      "kubectl", "rollout", "restart", "deployment/scene",
      "-n", self.namespace, "--kubeconfig", self.kubeconfig,
    ])
    _run([
      "kubectl", "rollout", "status", "deployment/scene",
      "-n", self.namespace, "--kubeconfig", self.kubeconfig,
      "--timeout=120s",
    ])
    logger.info("Scene controller restarted and ready.")

  def _get_pod_name(self, app_label):
    """Get the first running pod name for a given app label."""
    result = _run([
      "kubectl", "get", "pods",
      "-l", f"app={app_label}",
      "-n", self.namespace,
      "--kubeconfig", self.kubeconfig,
      "--field-selector=status.phase=Running",
      "-o", "jsonpath={.items[0].metadata.name}",
    ])
    pod_name = result.stdout.strip()
    if not pod_name:
      raise RuntimeError(f"No running pod found with app={app_label}")
    return pod_name

  def _kubectl_exec(self, pod, command):
    """Execute a shell command inside a pod."""
    _run([
      "kubectl", "exec", pod,
      "-n", self.namespace,
      "--kubeconfig", self.kubeconfig,
      "--", "sh", "-c", command,
    ])


class K8sManager:
  """Manages a KinD Kubernetes cluster lifecycle for test sessions.

  Parallel to _ComposeManager: creates a KinD cluster, deploys SceneScape
  via Helm, sets up port-forwarding, and extracts secrets. Session-scoped:
  the cluster is created once and reused for all tests.
  """

  def __init__(self, repo_root, supass, tmp_path_factory):
    self._repo_root = repo_root
    self._supass = supass
    self._tmp_path_factory = tmp_path_factory
    self._cluster = None
    self._port_forwards = []  # PortForwarding objects
    self._env = None
    self._models_preloaded = False

    # Populated during setup
    self.auth_file = None
    self.cert_file = None
    self.mqtt_port = None
    self.web_port = None
    self.kubeconfig = None

  def setup(self):
    """Create KinD cluster, deploy Helm chart, set up port-forwarding."""
    try:
      from pytest_kubernetes.providers.kind import KindManagerBase
      from pytest_kubernetes.options import ClusterOptions
    except ImportError:
      raise RuntimeError(
        "pytest-kubernetes is required for --backend=kubernetes. "
        "Install it: pip install pytest-kubernetes"
      )

    logger.info("=" * 60)
    logger.info("Setting up Kubernetes test environment")
    logger.info("=" * 60)

    # Create KinD cluster
    logger.info("Creating KinD cluster...")
    # Delete any leftover cluster from a previous failed run.
    subprocess.run(
      ["kind", "delete", "cluster", "--name", "pytest-test-cluster"],
      capture_output=True, check=False,
    )
    self._cluster = KindManagerBase("pytest-test-cluster")
    self._cluster.create(
      cluster_options=ClusterOptions(
        cluster_name="pytest-test-cluster",
        provider_config=_KIND_CONFIG,
      ),
    )
    self.kubeconfig = str(self._cluster.kubeconfig)
    logger.info("KinD cluster created. Kubeconfig: %s", self.kubeconfig)

    # Apply ingress resources
    logger.info("Applying ingress resources...")
    self._cluster.apply(str(_INGRESS_YAML))

    # Patch kubernetes API service for kubeclient
    patch = json.dumps({
      "spec": {"ports": [{"name": "https", "port": 6443, "targetPort": 6443}]}
    })
    self._cluster.kubectl(["patch", "svc", "kubernetes", "--type=merge", f"-p='{patch}'"], as_dict=False)

    # Install Nginx Ingress Controller
    logger.info("Installing Nginx Ingress Controller...")
    self._cluster.apply(_INGRESS_CONTROLLER_URL)

    # Install cert-manager
    logger.info("Installing cert-manager...")
    self._cluster.apply(_CERTMANAGER_URL)
    self._wait_for_cert_manager()

    # Load SceneScape images into KinD
    logger.info("Loading SceneScape images into KinD...")
    self._load_images()

    # Populate kubernetes/scenescape-chart/files/ from source tree.
    # This directory is gitignored and must be built before helm install.
    logger.info("Populating Helm chart files (make copy-files)...")
    subprocess.run(
      ["make", "copy-files"],
      cwd=str(_REPO_ROOT / "kubernetes"),
      check=True,
    )

    # Pre-populate models PVC from the host Docker volume so that
    # DL Streamer pipeline pods can start without downloading models.
    self._preload_models_pvc()

    # Generate values file and deploy Helm chart
    logger.info("Deploying Helm chart...")
    values_file = self._generate_values_file()
    self._helm_install(values_file)

    # Extract secrets
    logger.info("Extracting secrets from cluster...")
    tmp_dir = self._tmp_path_factory.mktemp("k8s_secrets")
    self.auth_file = str(self._extract_secret(
      f"{_RELEASE_NAME}-controller.auth", "controller.auth", tmp_dir / "controller.auth",
    ))
    self.cert_file = str(self._extract_secret(
      f"{_RELEASE_NAME}-scenescape-ca.pem", "ca.crt", tmp_dir / "scenescape-ca.pem",
    ))

    # Set up port-forwarding
    logger.info("Setting up port-forwarding...")
    self.mqtt_port = self._port_forward("svc/broker", 1883, 1883)
    self.web_port = self._port_forward("svc/web", 9443, 443)
    logger.info("MQTT port: %d, Web port: %d", self.mqtt_port, self.web_port)

    # Build the environment object
    self._env = K8sScenescapeEnv(
      kubeconfig=self.kubeconfig,
      namespace=_NAMESPACE,
      release_name=_RELEASE_NAME,
      repo_root=self._repo_root,
      secrets_dir=str(tmp_dir),
      supass=self._supass,
    )

    logger.info("=" * 60)
    logger.info("Kubernetes test environment ready")
    logger.info("=" * 60)

  def get_env(self, spec):
    """Return the K8sScenescapeEnv. The Helm chart deploys everything,
    so the ServiceProfile is used only for informational purposes."""
    if self._env is None:
      raise RuntimeError("K8sManager.setup() has not been called")
    return self._env

  def teardown(self):
    """Tear down port-forwarding and delete the KinD cluster."""
    logger.info("Tearing down Kubernetes test environment...")

    for pf in self._port_forwards:
      try:
        pf.stop()
      except Exception:
        pass

    if self._cluster is not None:
      try:
        logger.info("Deleting KinD cluster...")
        self._cluster.delete()
      except Exception as exc:
        logger.warning("Failed to delete KinD cluster: %s", exc)

    logger.info("Kubernetes teardown complete.")

  def _wait_for_cert_manager(self):
    """Wait for cert-manager pods to be ready."""
    logger.info("Waiting for cert-manager to be ready...")
    self._cluster.kubectl([
      "wait", "--for=condition=Available",
      "deployment/cert-manager",
      "deployment/cert-manager-webhook",
      "deployment/cert-manager-cainjector",
      "-n", "cert-manager",
      "--timeout=120s",
    ], as_dict=False, timeout=180)
    # Give cert-manager webhook a moment to become fully operational.
    time.sleep(5)

  def _load_images(self):
    """Tag and load SceneScape + external images into the KinD cluster."""
    from python_on_whales import docker

    version_file = Path(self._repo_root) / "version.txt"
    version = version_file.read_text().strip()

    # Load SceneScape images (already built locally)
    for image_name in _SCENESCAPE_IMAGES:
      old_tag = f"{image_name}:latest"
      new_tag = f"intel/{image_name}:{version}"
      try:
        docker.image.tag(old_tag, new_tag)
      except Exception:
        logger.warning("Could not tag %s → %s (may already exist)", old_tag, new_tag)
      self._cluster.load_image(new_tag)

    # Pull and load external images needed by helm chart hooks/deployments
    for image in _EXTERNAL_IMAGES:
      logger.info("Pulling external image %s ...", image)
      try:
        docker.image.pull(image)
      except Exception:
        logger.warning("Could not pull %s (may already exist locally)", image)
      self._cluster.load_image(image)

  def _generate_values_file(self):
    """Generate a Helm values.yaml for the test deployment.

    When models have been pre-loaded from the host Docker volume, hooks
    are disabled so that the model-installer job is skipped (saving
    significant download time).  When models are not pre-loaded, hooks
    are enabled so that model-installer downloads them and sample-data
    is fetched as a pre-install hook.
    """
    tmp_dir = self._tmp_path_factory.mktemp("k8s_helm")
    values_file = tmp_dir / "values.yaml"
    hooks_enabled = "false" if self._models_preloaded else "true"
    values_content = (
      f'supass: "{self._supass}"\n'
      f'pgserver:\n'
      f'  password: "{self._supass}"\n'
      f'hooks:\n'
      f'  enabled: {hooks_enabled}\n'
      f'httpProxy: "{os.getenv("HTTP_PROXY", "")}"\n'
      f'httpsProxy: "{os.getenv("HTTPS_PROXY", "")}"\n'
      f'noProxy: "{os.getenv("NO_PROXY", "")}"\n'
    )
    values_file.write_text(values_content)
    return str(values_file)

  def _helm_install(self, values_file):
    """Deploy the Helm chart to the KinD cluster."""
    # Create namespace (ignore if it already exists)
    subprocess.run([
      "kubectl", "create", "namespace", _NAMESPACE,
      "--kubeconfig", self.kubeconfig,
    ], check=False, capture_output=True)

    # Install without --wait: some services (NTP, dlstreamer) crash in KinD
    # due to missing capabilities (SYS_TIME) or hardware (GPU). We wait
    # selectively for only the services our tests actually require.
    _run([
      "helm", "install", _RELEASE_NAME, _CHART_PATH,
      "--namespace", _NAMESPACE,
      "--kubeconfig", self.kubeconfig,
      "--timeout", "300s",
      "-f", values_file,
    ])
    logger.info("Helm chart installed. Waiting for core services...")
    self._wait_for_core_services()
    logger.info("Helm chart deployed successfully.")

  def _wait_for_core_services(self):
    """Wait for core SceneScape services to be ready.

    NTP (chrony) is excluded because it needs the SYS_TIME capability
    which is not available in KinD. All other services including
    kubeclient and the camera pipeline pods are waited for here.
    """
    _CORE_RESOURCES = [
      f"deployment/{_RELEASE_NAME}-web-dep",
      f"deployment/{_RELEASE_NAME}-scene-dep",
      f"deployment/{_RELEASE_NAME}-autocalibration-dep",
      f"deployment/{_RELEASE_NAME}-vdms-dep",
      f"deployment/{_RELEASE_NAME}-mediaserver-dep",
      f"deployment/{_RELEASE_NAME}-broker",
      f"statefulset/{_RELEASE_NAME}-pgserver",
    ]

    logger.info("Waiting for core services...")
    for resource in _CORE_RESOURCES:
      logger.info("  Waiting: %s ...", resource)
      self._cluster.kubectl([
        "rollout", "status", resource,
        "-n", _NAMESPACE,
        "--timeout=600s",
      ], as_dict=False, timeout=660)
    logger.info("All core services are ready.")

    # Wait for kubeclient so it can create camera pipeline pods.
    logger.info("Waiting for kubeclient to be ready...")
    self._cluster.kubectl([
      "rollout", "status", f"deployment/{_RELEASE_NAME}-kubeclient-dep",
      "-n", _NAMESPACE,
      "--timeout=300s",
    ], as_dict=False, timeout=360)
    logger.info("kubeclient is ready.")

    # Wait for camera pipeline pods (created dynamically by kubeclient).
    self._wait_for_camera_pods()

  def _preload_models_pvc(self):
    """Copy OpenVINO models from the host Docker volume into the KinD models PVC.

    When Docker-based tests have already downloaded models into the
    ``scenescape_vol-models`` volume, we reuse them so that the KinD
    cluster does not need internet access and model-installer can be
    skipped, saving significant setup time.
    """
    # Locate the host Docker volume.
    result = subprocess.run(
      ["docker", "volume", "inspect", "scenescape_vol-models"],
      capture_output=True, text=True,
    )
    if result.returncode != 0:
      logger.warning(
        "Host Docker volume 'scenescape_vol-models' not found; "
        "model-installer will run during helm install."
      )
      return

    # Check volume is non-empty without requiring root access to the mountpoint.
    check = subprocess.run(
      ["docker", "run", "--rm",
       "-v", "scenescape_vol-models:/check",
       "busybox", "sh", "-c", "ls /check | head -1"],
      capture_output=True, text=True,
    )
    if check.returncode != 0 or not check.stdout.strip():
      logger.warning(
        "Host models volume is empty; "
        "model-installer will run during helm install."
      )
      return

    logger.info("Pre-loading models from host Docker volume into KinD...")

    # Create namespace early so we can create the PVC.
    subprocess.run([
      "kubectl", "create", "namespace", _NAMESPACE,
      "--kubeconfig", self.kubeconfig,
    ], check=False, capture_output=True)

    # Create the models PVC if it doesn't exist yet.
    pvc_manifest = (
      f"apiVersion: v1\nkind: PersistentVolumeClaim\n"
      f"metadata:\n  name: {_RELEASE_NAME}-models-pvc\n  namespace: {_NAMESPACE}\n"
      f"spec:\n  accessModes: [ReadWriteOnce]\n"
      f"  resources:\n    requests:\n      storage: 10Gi\n"
    )
    subprocess.run(
      ["kubectl", "apply", "-f", "-", "--kubeconfig", self.kubeconfig],
      input=pvc_manifest, text=True, capture_output=True,
    )

    # Spin up a transient pod that mounts the PVC, copy models into it.
    loader_pod = f"{_RELEASE_NAME}-model-loader"
    pod_manifest = (
      f"apiVersion: v1\nkind: Pod\n"
      f"metadata:\n  name: {loader_pod}\n  namespace: {_NAMESPACE}\n"
      f"spec:\n  restartPolicy: Never\n"
      f"  containers:\n  - name: loader\n    image: docker.io/busybox:1.37.0\n"
      f"    command: [\"sh\", \"-c\", \"sleep 3600\"]\n"
      f"    volumeMounts:\n    - name: models\n      mountPath: /models\n"
      f"  volumes:\n  - name: models\n    persistentVolumeClaim:\n"
      f"      claimName: {_RELEASE_NAME}-models-pvc\n"
    )
    subprocess.run(
      ["kubectl", "apply", "-f", "-", "--kubeconfig", self.kubeconfig],
      input=pod_manifest, text=True, check=False, capture_output=True,
    )

    # Wait for the loader pod to be running.
    try:
      _run([
        "kubectl", "wait", "--for=condition=Ready", f"pod/{loader_pod}",
        "-n", _NAMESPACE, "--kubeconfig", self.kubeconfig, "--timeout=120s",
      ])
    except Exception as exc:
      logger.warning("Loader pod did not become ready: %s; skipping model preload", exc)
      subprocess.run(
        ["kubectl", "delete", "pod", loader_pod, "-n", _NAMESPACE,
         "--kubeconfig", self.kubeconfig, "--ignore-not-found"],
        capture_output=True,
      )
      return

    # Use docker run to stream volume contents via tar (avoids root access
    # to /var/lib/docker/volumes), then pipe into the loader pod.
    try:
      tar_proc = subprocess.Popen(
        ["docker", "run", "--rm", "-v", "scenescape_vol-models:/models",
         "busybox", "tar", "-C", "/models", "-cf", "-", "."],
        stdout=subprocess.PIPE,
      )
      subprocess.run(
        ["kubectl", "exec", loader_pod, "-n", _NAMESPACE,
         "--kubeconfig", self.kubeconfig,
         "--", "tar", "-C", "/models", "-xf", "-"],
        stdin=tar_proc.stdout, check=True, capture_output=True,
      )
      tar_proc.wait()
      logger.info("Models copied into KinD models PVC successfully.")
      self._models_preloaded = True
    except Exception as exc:
      logger.warning("Failed to copy models into KinD: %s", exc)
    finally:
      subprocess.run(
        ["kubectl", "delete", "pod", loader_pod, "-n", _NAMESPACE,
         "--kubeconfig", self.kubeconfig, "--ignore-not-found"],
        capture_output=True,
      )

  def _wait_for_camera_pods(self, timeout: int = 300):
    """Wait for at least one camera pipeline pod to be running.

    kubeclient reads camera configs from the REST API and creates DL Streamer
    pods dynamically.  We poll until at least one ``*-video-dep`` deployment
    exists and is available, or until *timeout* seconds elapse.
    """
    logger.info("Waiting for kubeclient to create camera pipeline pods...")
    deadline = time.time() + timeout
    while time.time() < deadline:
      result = subprocess.run(
        ["kubectl", "get", "deployments",
         "-n", _NAMESPACE,
         "--kubeconfig", self.kubeconfig,
         "--no-headers"],
        capture_output=True, text=True,
      )
      video_deps = [
        line.split()[0]
        for line in result.stdout.splitlines()
        if "-video-dep" in line
      ]
      if video_deps:
        logger.info("Camera pods found: %s", video_deps)
        # Wait for each video deployment to be available.
        for dep in video_deps:
          try:
            self._cluster.kubectl([
              "rollout", "status", f"deployment/{dep}",
              "-n", _NAMESPACE, "--timeout=120s",
            ], as_dict=False, timeout=130)
            logger.info("Camera deployment %s is ready.", dep)
          except Exception as exc:
            logger.warning("Camera deployment %s not ready: %s", dep, exc)
        return
      logger.debug("No camera pipeline pods yet, waiting...")
      time.sleep(10)
    logger.warning(
      "Timed out waiting for camera pipeline pods after %ds. "
      "Tests requiring live camera images may fail.", timeout,
    )

  def _extract_secret(self, secret_name, key, output_path):
    """Extract a value from a Kubernetes secret and write to a file."""
    secret_data = self._cluster.kubectl(
      ["get", "secret", secret_name, "-n", _NAMESPACE],
      as_dict=True,
    )
    encoded = secret_data["data"][key]
    decoded = base64.b64decode(encoded).decode("utf-8")
    output_path.write_text(decoded)
    logger.info("Extracted secret %s/%s → %s", secret_name, key, output_path)
    return output_path

  def _port_forward(self, target, local_port, remote_port):
    """Start port-forwarding using pytest-kubernetes's PortForwarding. Returns local port."""
    pf = self._cluster.port_forwarding(
      target=target,
      namespace=_NAMESPACE,
      source_port=local_port,
      target_port=remote_port,
    )
    pf.start()
    self._port_forwards.append(pf)
    logger.info("Port-forward: localhost:%d → %s:%d", local_port, target, remote_port)
    return local_port
