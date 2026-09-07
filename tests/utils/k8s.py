#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Kubernetes backend for end-to-end tests.

Provides K8sManager (parallel to _ComposeManager) that creates a KinD cluster,
deploys Scenescape via Helm, sets up port-forwarding, and extracts secrets so
tests can connect to the cluster using the same params dict as Docker tests.
"""

import base64
import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from python_on_whales import docker
from pytest_kubernetes.providers.kind import KindManagerBase
from pytest_kubernetes.options import ClusterOptions

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

# Core images required by the default k8s test Helm values (reid enabled;
# mapping / clusterAnalytics remain disabled). Matches `make build-core`.
_SCENESCAPE_IMAGES = [
  "intel/scenescape-analytics",
  "intel/scenescape-autocalibration",
  "intel/scenescape-controller",
  "intel/scenescape-manager",
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


def _image_exists(ref: str) -> bool:
  try:
    docker.image.inspect(ref)
    return True
  except Exception:
    return False
class K8sManager:
  """Manages a KinD Kubernetes cluster lifecycle for test sessions.

  Parallel to _ComposeManager: creates a KinD cluster, deploys Scenescape
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

    # Populated during setup
    self.auth_file = None
    self.cert_file = None
    self.mqtt_port = None
    self.web_port = None
    self.kubeconfig = None

  def setup(self):
    """Create KinD cluster, deploy Helm chart, set up port-forwarding."""

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

    # Merge the test cluster context into ~/.kube/config so that
    # 'kubectl' and k9s work without any extra flags or env vars.
    subprocess.run(
      ["kind", "export", "kubeconfig", "--name", "pytest-test-cluster"],
      check=False, capture_output=True,
    )
    logger.info("Test cluster context merged into ~/.kube/config (kind-pytest-test-cluster)")

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

    # Load Scenescape images into KinD
    logger.info("Loading Scenescape images into KinD...")
    self._load_images()

    # Populate kubernetes/scenescape-chart/files/ from source tree.
    # This directory is gitignored and must be built before helm install.
    logger.info("Populating Helm chart files (make copy-files)...")
    subprocess.run(
      ["make", "copy-files"],
      cwd=str(_REPO_ROOT / "kubernetes"),
      check=True,
    )

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

    # Remove the test cluster context from ~/.kube/config.
    for resource, name in [
      ("context", "kind-pytest-test-cluster"),
      ("cluster", "kind-pytest-test-cluster"),
      ("user", "kind-pytest-test-cluster"),
    ]:
      subprocess.run(
        ["kubectl", "config", "delete-" + resource, name],
        capture_output=True, check=False,
      )

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
    """Tag and load Scenescape + external images into the KinD cluster."""
    version_file = Path(self._repo_root) / "version.txt"
    version = version_file.read_text().strip()

    for image_name in _SCENESCAPE_IMAGES:
      old_tag = f"{image_name}:latest"
      new_tag = f"{image_name}:{version}"

      if not _image_exists(old_tag):
        raise RuntimeError(
          f"Required local image missing: {old_tag}. "
          f"Build images before running k8s tests."
        )

      if not _image_exists(new_tag):
        try:
          docker.image.tag(old_tag, new_tag)
          logger.info("Tagged %s -> %s", old_tag, new_tag)
        except Exception as exc:
          raise RuntimeError(f"Failed tagging {old_tag} -> {new_tag}: {exc}") from exc
      else:
        logger.info("Tag already exists: %s", new_tag)

      try:
        self._cluster.load_image(new_tag)
        logger.info("Loaded image into kind: %s", new_tag)
      except subprocess.CalledProcessError as exc:
        logger.error("Failed loading image into kind: %s", new_tag)
        if exc.stdout:
          logger.error("kind load stdout: %s", exc.stdout.strip())
        if exc.stderr:
          logger.error("kind load stderr: %s", exc.stderr.strip())
        raise RuntimeError(
          f"Failed loading image into kind: {new_tag} (exit {exc.returncode})"
        ) from exc
      except Exception as exc:
        raise RuntimeError(f"Failed loading image into kind: {new_tag}: {exc}") from exc

  def _generate_values_file(self):
    """Generate a Helm values.yaml for the test deployment.

    Hooks are always enabled so that sample-data and model-installer
    run as pre-install hooks (before web/kubeclient start).  This
    ensures the example DB is loaded and cameras are available when
    kubeclient calls getCameras().
    When models are pre-loaded on the PVC, model-installer skips
    downloads (checks if dirs already exist) so it completes quickly.
    """
    tmp_dir = self._tmp_path_factory.mktemp("k8s_helm")
    values_file = tmp_dir / "values.yaml"
    values_content = (
      f'supass: "{self._supass}"\n'
      f'pgserver:\n'
      f'  password: "{self._supass}"\n'
      f'hooks:\n'
      f'  enabled: true\n'
      # KinD/CI often cannot finish the ~550MB NetVLAD fetch before the
      # deployment progress deadline; smoke tests do not need markerless.
      f'autocalibration:\n'
      f'  skipModelDownload: true\n'
      f'reid:\n'
      f'  enabled: true\n'
      f'  backend: "{os.getenv("REID_BACKEND", "vdms")}"\n'
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
    # Timeout covers pre-install hooks (model-installer, sample-data).
    _run([
      "helm", "install", _RELEASE_NAME, _CHART_PATH,
      "--namespace", _NAMESPACE,
      "--kubeconfig", self.kubeconfig,
      "--timeout", "1200s",
      "-f", values_file,
    ])
    logger.info("Helm chart installed. Waiting for core services...")
    self._wait_for_core_services()
    logger.info("Helm chart deployed successfully.")

  def _wait_for_core_services(self):
    """Wait for core Scenescape services to be ready.

    NTP (chrony) is excluded because it needs the SYS_TIME capability
    which is not available in KinD. All other services including
    kubeclient and the camera pipeline pods are waited for here.
    """
    _CORE_RESOURCES = [
      f"deployment/{_RELEASE_NAME}-web-dep",
      f"deployment/{_RELEASE_NAME}-scene-dep",
      f"deployment/{_RELEASE_NAME}-autocalibration-dep",
      f"deployment/{_RELEASE_NAME}-reid-dep",
      f"deployment/{_RELEASE_NAME}-mediaserver-dep",
      f"deployment/{_RELEASE_NAME}-broker",
      f"statefulset/{_RELEASE_NAME}-pgserver",
    ]

    logger.info("Waiting for core services...")
    for resource in _CORE_RESOURCES:
      logger.info("  Waiting: %s ...", resource)
      try:
        self._cluster.kubectl([
          "rollout", "status", resource,
          "-n", _NAMESPACE,
          "--timeout=1200s",
        ], as_dict=False, timeout=1260)
      except Exception:
        self._log_resource_failure(resource)
        raise
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

    # Wait for DL Streamer to load models and start producing inference.
    self._wait_for_inference_warmup()

  def _log_resource_failure(self, resource: str):
    """Emit describe/logs for a failed rollout so CI failures are actionable."""
    name = resource.split("/", 1)[-1]
    kind = resource.split("/", 1)[0]
    logger.error("Rollout failed for %s; collecting diagnostics...", resource)
    for cmd, label in (
      (["kubectl", "describe", kind, name,
        "-n", _NAMESPACE, "--kubeconfig", self.kubeconfig], "describe"),
      (["kubectl", "get", "pods",
        "-n", _NAMESPACE, "--kubeconfig", self.kubeconfig,
        "-l", f"app={name.removesuffix('-dep')}",
        "-o", "wide"], "pods"),
      (["kubectl", "get", "events",
        "-n", _NAMESPACE, "--kubeconfig", self.kubeconfig,
        "--field-selector", f"involvedObject.name={name}",
        "--sort-by=.lastTimestamp"], "events"),
    ):
      result = subprocess.run(cmd, capture_output=True, text=True)
      out = (result.stdout or result.stderr or "").strip()
      logger.error("%s %s:\n%s", resource, label, out or "<empty>")

    pods = subprocess.run(
      ["kubectl", "get", "pods",
       "-n", _NAMESPACE, "--kubeconfig", self.kubeconfig,
       "-l", f"app={name.removesuffix('-dep')}",
       "-o", "jsonpath={.items[*].metadata.name}"],
      capture_output=True, text=True,
    )
    for pod in pods.stdout.split():
      logs = subprocess.run(
        ["kubectl", "logs", pod,
         "-n", _NAMESPACE, "--kubeconfig", self.kubeconfig,
         "--all-containers", "--tail=80"],
        capture_output=True, text=True,
      )
      logger.error(
        "logs %s:\n%s", pod, (logs.stdout or logs.stderr or "").strip() or "<empty>")

  def _wait_for_inference_warmup(self, timeout: int = 180):
    """Wait for DL Streamer pipelines to start producing inference results.

    Polls the logs of the first videoppl pod for evidence that the
    GStreamer pipeline is actively processing frames (indicated by
    'Running' pipeline state or published MQTT messages).
    Falls back to a fixed delay if log inspection fails.
    """
    logger.info("Waiting for DL Streamer inference warmup (up to %ds)...", timeout)
    # Find a videoppl pod to monitor.
    result = subprocess.run(
      ["kubectl", "get", "pods",
       "-n", _NAMESPACE,
       "--kubeconfig", self.kubeconfig,
       "--no-headers"],
      capture_output=True, text=True,
    )
    videoppl_pods = [
      line.split()[0]
      for line in result.stdout.splitlines()
      if "videoppl" in line and "Running" in line
    ]
    if not videoppl_pods:
      logger.warning("No running videoppl pods found; using fixed warmup delay.")
      time.sleep(60)
      return

    target_pod = videoppl_pods[0]
    logger.info("Monitoring pod %s for inference activity...", target_pod)

    deadline = time.time() + timeout
    while time.time() < deadline:
      logs = subprocess.run(
        ["kubectl", "logs", target_pod,
         "-n", _NAMESPACE,
         "--kubeconfig", self.kubeconfig,
         "--tail=50"],
        capture_output=True, text=True,
      )
      log_text = logs.stdout
      # DL Streamer logs "Setting pipeline" or "RUNNING" when the
      # GStreamer pipeline transitions to the playing state, and
      # "Objects detected" or publishes to MQTT when inference runs.
      if any(indicator in log_text for indicator in [
        "RUNNING", "Objects detected", "publish", "Setting pipeline",
        "Pipeline running", "pipeline_running",
      ]):
        logger.info("Inference activity detected in %s.", target_pod)
        # Give a small additional buffer for scene controller to receive frames.
        time.sleep(10)
        return
      time.sleep(10)

    logger.warning(
      "No inference activity detected after %ds. "
      "DL Streamer may still be loading models. Test may fail.", timeout,
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
        if "videoppl" in line
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
