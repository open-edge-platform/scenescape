<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Deploy the Demo

The demo builds on a clean Scenescape deployment by adding two things: the bundled Retail and Queuing sample video sources, and the corresponding preloaded demo scenes. This lets you explore the UI without connecting your own cameras.

Before you begin, prepare container images: see [Prepare Container Images](./prepare-images.md).

## Docker

### Deploy

```bash
export SUPASS='<choose-a-strong-admin-password>'
make demo
```

`make demo` builds the core images (unless `DEMO_REBUILD_IMAGES=false`), starts the `controller` profile, starts the separate demo video-source stack, and uploads the two demo scenes by running `make demo-scenes`. `make demo-scenes` creates a local Python virtual environment at `tools/upload_scenes/.venv` the first time it runs; no system-wide package installation is required.

To use prebuilt images instead of building locally, after preparing them per [Prepare Container Images](./prepare-images.md):

```bash
SUPASS='<choose-a-strong-admin-password>' DEMO_REBUILD_IMAGES=false make demo
```

### Demo Tiers

The Docker Compose demo targets are tiered, each building on the previous one:

| Target      | Includes                                                |
| ----------- | ------------------------------------------------------- |
| `demo`      | Core services with tracking, without ReID               |
| `demo-reid` | `demo` plus the ReID vector database                    |
| `demo-all`  | `demo-reid` plus cluster analytics and mapping services |

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

Deploy Scenescape as described in [Deploy on Kubernetes](./deploy-kubernetes.md), enabling whichever [optional services](./deploy-kubernetes.md#optional-services) you want, then add the two demo-only pieces below.

### Wire Up the Demo Video Sources

The chart does not run a media server itself. Start the bundled Retail and Queuing sample-video stack and point the cluster's `mediaserver` Service at it: see [Video Source (sample/demo camera feeds)](/kubernetes/README.md#video-source-sampledemo-camera-feeds).

### Upload the Demo Scenes

Install the upload tool's dependencies once, as shown in [Uploading Your Own Scenes](#uploading-your-own-scenes) above. Then, with `kubectl` access to the cluster and the web service reachable (for example, through the port-forward from [Deploy on Kubernetes](./deploy-kubernetes.md#verify)):

```bash
(
  NAMESPACE="${NAMESPACE:-scenescape}"
  AUTH_FILE=$(mktemp)
  trap 'rm -f "$AUTH_FILE"' EXIT

  kubectl get secret scenescape-controller.auth --namespace "$NAMESPACE" \
    -o jsonpath='{.data.controller\.auth}' | base64 -d > "$AUTH_FILE"

  tools/upload_scenes/.venv/bin/python3 tools/upload_scenes/upload-scenes \
    --restauth "$AUTH_FILE" --insecure --wait 300 \
    https://localhost:8443/api/v1 sample_data/demo_scenes
)
```

Running this as a subshell with an `EXIT` trap ensures the temporary credential file is removed even if a command fails or the snippet is interrupted. Adjust the host and port to match however you reach the web service. Scenes that already exist are skipped, so re-running this is safe.
