<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Deploy Scenescape on Kubernetes

This guide deploys a clean Scenescape instance to an existing Kubernetes cluster with Helm: an empty scene database, without the bundled demo video sources or preloaded demo scenes. It assumes a cluster already exists and `kubectl` is configured with access to it. To run the demo instead, see [Deploy the Demo](./deploy-demo.md). For a self-contained local cluster managed by this repository's tooling (Kind), see [Scenescape on Kubernetes](/kubernetes/README.md) instead.

- **Time to Complete:** 15-30 minutes

## Prerequisites

- A Kubernetes cluster reachable through `kubectl`.
- [Helm](https://helm.sh/) 3.
- [Cert Manager](https://cert-manager.io/) installed in the cluster; the chart's certificate resources depend on it.
- A default StorageClass with dynamic volume provisioning, or a values file that sets storage classes for the chart's persistent volume claims.
- Container images available to the cluster: see [Preparation](./preparation.md).
- A checkout of the Scenescape repository (see [Get Scenescape](../../get-started/installation.md#step-1-get-scenescape)); the chart lives at `kubernetes/scenescape-chart/`.

Check the selected cluster context and available storage classes:

```bash
kubectl config current-context
kubectl get nodes
kubectl get storageclass
```

## Deploy

From the repository root, prepare the chart files:

```bash
make -C kubernetes copy-files chart.yaml
```

Set the namespace and passwords, then install the chart. Use unique, strong passwords for both values:

```bash
export NAMESPACE=scenescape
export SUPASS='<choose-a-strong-admin-password>'
export PGPASS='<choose-a-strong-database-password>'

(
  VALUES_FILE=$(mktemp)
  trap 'rm -f "$VALUES_FILE"' EXIT

  printf "supass: '%s'\npgserver:\n  password: '%s'\n" \
    "$(printf '%s' "$SUPASS" | sed "s/'/''/g")" \
    "$(printf '%s' "$PGPASS" | sed "s/'/''/g")" > "$VALUES_FILE"

  helm upgrade --install scenescape kubernetes/scenescape-chart/ \
    --namespace "$NAMESPACE" --create-namespace \
    --values "$VALUES_FILE" \
    --set reid.enabled=false \
    --wait --timeout 30m
)
```

Passwords are written to a temporary values file rather than passed with `--set`/`--set-string`, because Helm splits those flags on commas: a password containing one would otherwise be parsed as two separate values. The subshell's `EXIT` trap removes the file whether the install succeeds, fails, or is interrupted.

This installs the web application, database, broker, NTP server, Scene Controller, Analytics, Auto Camera Calibration, and supporting resources, including persistent volume claims and certificates. ReID is disabled explicitly, because it is enabled by the chart's defaults. No demo scenes or video sources are installed.

If the cluster has no default StorageClass, provide a Helm values file that sets the applicable storage-class values before running the install command.

## Optional Services

Enable additional chart features by setting these values on `helm upgrade`/`helm install`:

| Value                      | Default | Effect                                                                                                                                                   |
| -------------------------- | ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `reid.enabled`             | `true`  | Deploys the ReID vector database (`reid.backend`: `vdms` or `qdrant`); requires `tracker.enabled=false` so the Scene Controller is deployed to use ReID. |
| `tracker.enabled`          | `false` | Deploys Tracker + Analytics instead of the Scene Controller.                                                                                             |
| `mapping.enabled`          | `false` | Deploys the mapping service.                                                                                                                             |
| `clusterAnalytics.enabled` | `false` | Deploys the cluster-analytics service.                                                                                                                   |

ReID is consumed by the Scene Controller. Tracker mode replaces the Scene Controller, so do not enable ReID together with `tracker.enabled=true`.

See [How to Enable Re-identification](../../other-topics/how-to-enable-reidentification.md) for ReID backend details, and [Scenescape on Kubernetes](/kubernetes/README.md) for the full chart reference.

### Select the Mapping Model

Each Mapping image contains exactly one 3D reconstruction model, fixed at build time. The chart selects the image tag with `mapping.model`:

| `mapping.model` | Image used                                         |
| --------------- | -------------------------------------------------- |
| empty (default) | `intel/scenescape-mapping:<version>` (MapAnything) |
| `mapanything`   | `intel/scenescape-mapping:<version>-mapanything`   |
| `vggt`          | `intel/scenescape-mapping:<version>-vggt`          |

The matching variant must be available to the cluster: either pulled from Docker Hub, or built with `make -C mapping build-all` (see [Build Mapping Service from Source](../../microservices/mapping-service/build-from-source.md)) and pushed to the registry set in `repository`. The root `make build-all` builds only the default MapAnything image.

## Verify

Confirm that workloads and claims become ready:

```bash
kubectl get pods,services,pvc --namespace "$NAMESPACE"
```

For local access, forward the web service port in a terminal and leave the command running:

```bash
kubectl port-forward --namespace "$NAMESPACE" service/web 8443:443
```

Open `https://localhost:8443`. The certificate is self-signed, so the browser displays a warning. Sign in as `admin` with the password assigned to `SUPASS`.

The scene list is empty. Import or create your own scene and configure its cameras and analytics inputs before expecting detections or tracks; see [Build a Scene](../build-a-scene/index.md).

## Stopping

To remove the Helm release while leaving the namespace and any retained storage in place:

```bash
helm uninstall scenescape --namespace "$NAMESPACE"
```

For a local Kind deployment created by the repository's Kubernetes Makefile, use `make -C kubernetes uninstall` to uninstall its Helm release while leaving the Kind cluster running. To delete that local Kind cluster and all resources/data in it, use:

```bash
make -C kubernetes clean-all
```

> **Warning:** This command deletes the default local Kind cluster, regardless of the active Kubernetes context. Do not run it if that Kind cluster contains workloads or data you need to keep.
