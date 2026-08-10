# Running tests for Scenescape on Kubernetes

All Kubernetes tests are driven by pytest with the `--backend=kubernetes` flag.
This creates a KinD cluster, deploys Scenescape via Helm, runs the tests, and
destroys the cluster automatically at the end of the session. No
separately-running cluster is required.

## Prerequisites

Install the following tools and make them available on `PATH`:

| Tool      | Installation                                                                                                                                                                                                |
| --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `kind`    | >= v0.31 (v0.32.0 recommended); older binaries fail `kind load` against `kindest/node:v1.35.x` with `failed to detect containerd snapshotter`. https://kind.sigs.k8s.io/docs/user/quick-start/#installation |
| `kubectl` | https://kubernetes.io/docs/tasks/tools/ (v1.35.x recommended for the pinned node image)                                                                                                                     |
| `helm`    | https://helm.sh/docs/intro/install/                                                                                                                                                                         |

Python dependencies (`pytest-kubernetes`, `python-on-whales`) are installed
automatically by `make setup-tests`.

## Running tests

```bash
# One-time setup — build core images and create the test virtualenv
SUPASS=change_me make && make setup-tests

# Activate the virtualenv
source tests/.venv/bin/activate

# Run the Kubernetes deployment smoke tests
pytest tests/kubernetes --backend=kubernetes -v

# Run the out-of-box test on Kubernetes
pytest tests/ui/test_out_of_box.py --backend=kubernetes -v

# Run all Kubernetes-capable tests
pytest --backend=kubernetes -v

# Run only tests that are Kubernetes-specific
pytest -m kubernetes_only --backend=kubernetes -v
```

Requires kind >= v0.31 (see Prerequisites). Cluster setup (KinD creation, Helm
deploy, image loading) takes roughly 15–20 minutes on first run. Subsequent
runs reuse the pulled images from the local Docker cache.

## VS Code Test Extension

Add `--backend=kubernetes` to `python.testing.pytestArgs` in
`.vscode/settings.json`:

```json
{
  "python.testing.pytestArgs": ["tests", "--backend=kubernetes"],
  "python.testing.pytestEnabled": true,
  "python.testing.unittestEnabled": false
}
```

Then click **Refresh Tests** and run from the Testing sidebar as normal.

## How it works

When `--backend=kubernetes` is passed to pytest the `K8sManager` in
`tests/utils/k8s.py` performs the following steps:

1. Creates a KinD cluster named `pytest-test-cluster` using the config in
   `tests/kubernetes/config/kind_config.yaml`.
2. Installs the Nginx Ingress Controller and cert-manager.
3. Tags and loads core Scenescape Docker images into the KinD node
   (matches `make build-core`; mapping / cluster-analytics are not required
   unless those chart features are enabled).
4. Runs `make copy-files` in `kubernetes/` to populate the Helm chart files.
5. Installs the Helm chart with generated values (passwords, proxy settings).
6. Waits for all core services to become ready (web, scene controller,
   autocalibration, broker, pgserver, vdms, mediaserver, kubeclient, cameras,
   DL Streamer warmup).
7. Extracts `controller.auth` and `scenescape-ca.pem` from Kubernetes secrets.
8. Sets up `kubectl port-forward` for MQTT (`localhost:1883`) and the web
   service (`localhost:<random-port>`).
9. Injects the port-forwarded URLs, auth file, and root certificate into the
   test fixtures so tests connect transparently.

After all tests finish the cluster is torn down automatically.
