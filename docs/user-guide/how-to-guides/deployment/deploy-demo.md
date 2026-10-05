<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Deploy the Demo

The demo builds on a clean Scenescape deployment by adding two things: the bundled Retail and Queuing sample video sources, and the corresponding preloaded demo scenes. This lets you explore the UI without connecting your own cameras.

Before you begin, complete [Preparation](./preparation.md).

## Docker

### Deploy

```bash
export SUPASS='<choose-a-strong-admin-password>'
make demo
```

`make demo` builds the core images (unless `DEMO_REBUILD_IMAGES=false`), starts the `controller` profile, starts the separate demo video-source stack, and uploads the two demo scenes by running `make demo-scenes`. `make demo-scenes` creates a local Python virtual environment at `tools/upload_scenes/.venv` the first time it runs; no system-wide package installation is required.

To use prebuilt images instead of building locally, after following the prebuilt option in [Preparation](./preparation.md):

```bash
SUPASS='<choose-a-strong-admin-password>' DEMO_REBUILD_IMAGES=false make demo
```

### Docker Demo Targets

The Docker demo targets start the common sample video sources and upload the standard demo scenes, then select these services or overlays:

| Target                   | Services / behavior                                                                                                                                                                                             |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `demo`                   | Controller + Analytics; no ReID.                                                                                                                                                                                |
| `demo-reid`              | `demo` plus the selected ReID backend and ReID pipeline override.                                                                                                                                               |
| `demo-all`               | `demo-reid` plus Mapping and Cluster Analytics.                                                                                                                                                                 |
| `demo-cluster-analytics` | `demo` plus Cluster Analytics; no Mapping or ReID override.                                                                                                                                                     |
| `demo-tracker`           | Tracker + Analytics instead of the Scene Controller.                                                                                                                                                            |
| `demo-lidar`             | `demo` plus the LiDAR/camera intersection fusion overlay. It requires a manually downloaded dataset and first-run model setup; see [Run the LiDAR-Intersection Fusion Demo](../run-lidar-intersection-demo.md). |

The `demo-all`, `demo-cluster-analytics`, and `demo-tracker` targets build all service images by default. `demo-lidar` builds the dedicated LiDAR variant. Set `DEMO_REBUILD_IMAGES=false` to skip building when the required images already exist.

The ReID targets use VDMS by default. Set `REID_BACKEND=qdrant` to use Qdrant:

```bash
make demo-reid
make demo-reid REID_BACKEND=qdrant
```

See [Docker Compose Profiles](./deploy-docker.md#docker-compose-profiles) for the underlying profiles, including `demo-tracker` (Tracker + Analytics, no Scene Controller) and `demo-cluster-analytics`.

### Verify

Connect and sign in as described in [Deploy on Docker](./deploy-docker.md#verify-a-successful-deployment). Scenescape provides two scenes, Retail and Queuing, that you can explore running from stored video data.

### Uploading Your Own Scenes

Scenes that already exist are skipped, so re-running `make demo-scenes` is safe. `make demo`/`make demo-scenes` create and reuse a virtual environment at `tools/upload_scenes/.venv`; create or reuse it directly if you have not run either target yet, since the system Python on the supported Ubuntu setup is externally managed and rejects a bare `pip install`:

```bash
python3 -m venv tools/upload_scenes/.venv
tools/upload_scenes/.venv/bin/pip install -r tools/upload_scenes/requirements.txt
```

To load your own scenes into an already-running deployment, point the tool at a different directory of per-scene subdirectories, each with its own `<scene>.zip` as produced by the "Export Scene" button of the web UI:

```bash
tools/upload_scenes/.venv/bin/python3 tools/upload_scenes/upload-scenes \
  --restauth manager/secrets/controller.auth \
  --rootcert manager/secrets/certs/scenescape-ca.pem \
  https://web.scenescape.intel.com/api/v1 ./my-scenes
```

`--restauth` also accepts a `user:password` string, and `--insecure` skips certificate verification when the deployment is reached under a name the certificate was not issued for, such as `https://localhost`.

Scenes can also be imported through the Web UI: sign in, navigate to **Import Scene**, then select and upload the scene ZIP.

### Stopping the Demo

`make demo-close` remembers the selected override and stops the matching deployment, removing all volumes:

```bash
make demo-close
```

## Kubernetes

For the standard demo on a new local Kind cluster, build the core images and invoke the Kubernetes demo target from the repository root:

```bash
SUPASS='<choose-a-strong-admin-password>' PGPASS='<choose-a-strong-database-password>' \
  make build-core demo-k8s
```

The `build-core` goal prepares secrets, builds the core images, and installs models. `demo-k8s` installs the local Kind prerequisites, creates the cluster, loads the images, deploys the Helm chart, starts the demo video sources, and uploads the demo scenes.

Use `DEPLOY_PROFILES` to select optional services. For profiles that need Tracker, Mapping, or Cluster Analytics images, use `build-all` instead of `build-core`. For example, to run Controller + ReID + Mapping + Cluster Analytics:

```bash
SUPASS='<choose-a-strong-admin-password>' PGPASS='<choose-a-strong-database-password>' \
  make build-all demo-k8s DEPLOY_PROFILES='controller mapping cluster-analytics reid'
```

`DEPLOY_PROFILES` accepts `controller`, `tracker`, `mapping`, `cluster-analytics`, and `reid`; the default is `controller`. Tracker replaces the Scene Controller, so do not select both `tracker` and `reid`.

### Existing Cluster

For an existing Kubernetes cluster, follow [Deploy on Kubernetes](./deploy-kubernetes.md) and then add the two demo-only pieces below.

### Wire Up the Demo Video Sources

The chart does not run a media server itself. Start the bundled Retail and Queuing sample-video stack and point the cluster's `mediaserver` Service at it: see [Video Source (sample/demo camera feeds)](https://github.com/open-edge-platform/scenescape/blob/main/kubernetes/README.md#video-source-sampledemo-camera-feeds).

### Upload the Demo Scenes

Install the upload tool's dependencies once, as shown in [Uploading Your Own Scenes](#uploading-your-own-scenes) above. Then, with `kubectl` access to the cluster and the web service reachable (for example, through the port-forward from [Deploy on Kubernetes](./deploy-kubernetes.md#verify)):

```bash
(
  set -euo pipefail
  NAMESPACE="${NAMESPACE:-scenescape}"
  AUTH_FILE=$(mktemp)
  trap 'rm -f "$AUTH_FILE"' EXIT

  AUTH_SECRET_NAMES=$(kubectl get secrets --namespace "$NAMESPACE" \
    -o custom-columns=:metadata.name --no-headers | grep -E 'controller[.]auth$' || true)
  AUTH_SECRET_COUNT=$(printf '%s\n' "$AUTH_SECRET_NAMES" | sed '/^$/d' | wc -l)
  if [ "$AUTH_SECRET_COUNT" -ne 1 ]; then
    echo "Expected exactly one controller.auth Secret in namespace $NAMESPACE; found $AUTH_SECRET_COUNT." >&2
    exit 1
  fi
  AUTH_SECRET_NAME=$(printf '%s\n' "$AUTH_SECRET_NAMES" | sed -n '1p')

  kubectl get secret "$AUTH_SECRET_NAME" --namespace "$NAMESPACE" \
    -o jsonpath='{.data.controller\.auth}' | base64 -d > "$AUTH_FILE"

  tools/upload_scenes/.venv/bin/python3 tools/upload_scenes/upload-scenes \
    --restauth "$AUTH_FILE" --insecure --wait 300 \
    https://localhost:8443/api/v1 sample_data/demo_scenes
)
```

Running this as a subshell with an `EXIT` trap ensures the temporary credential file is removed even if a command fails or the snippet is interrupted. Adjust the host and port to match however you reach the web service. Scenes that already exist are skipped, so re-running this is safe.
