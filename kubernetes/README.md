# Scenescape on Kubernetes

## Overview

This folder contains the helm chart to run Scenescape on Kubernetes.

This readme goes through a minimal setup for running this on your local development machine with only 3 extra binaries needed. The default Makefile target starts a Kubernetes cluster in a Docker container using kind, then deploys Scenescape to that cluster using helm.

Advanced users intending to deploy this in production will have to change the default chart values or modify the templates.

There are 2 main ways to install Scenescape on Kubernetes:

1. [All-in-one (Kind + Registry + Scenescape)](#all-in-one) - for development and testing using locally built Scenescape images
2. [Scenescape only](#scenescape-only) - for existing clusters and published Scenescape images

## All-in-one

To build and deploy the standard Scenescape demo on a local [Kind](https://kind.sigs.k8s.io/) cluster, run this from the repository root:

```sh
SUPASS='<admin-password>' PGPASS='<database-password>' \
  make build-core demo-k8s
```

> **Warning:** This Makefile flow deletes and recreates the default Kind cluster. Do not use it if that cluster contains workloads or data you need to keep.

This will:

- Build the core images, generate secrets, and install the default models
- Create a local Kind cluster and install [Cert Manager](https://cert-manager.io/)
- Load the core images into Kind and deploy Scenescape with Helm
- Start the demo video sources and upload the sample scenes

When the web UI is up, log in as `admin` with the password supplied through `SUPASS`.

To enable optional services, pass their names in the shared, space-separated `DEPLOY_PROFILES` variable. Use `make build-all` in place of `make build-core` when selecting Tracker, Mapping, or Cluster Analytics so their images are built and loaded too. For example:

>

```sh
SUPASS='<admin-password>' PGPASS='<database-password>' \
  make build-all demo-k8s DEPLOY_PROFILES='controller mapping cluster-analytics reid'
```

The supported profiles are `controller`, `tracker`, `mapping`, `cluster-analytics`, and `reid`. Tracker replaces the Scene Controller, so do not combine `tracker` and `reid`.

Save this password for future logins. You can change the admin password later via the web UI after logging in.

### Useful targets

- Install Scenescape: `make -C kubernetes install`
- Uninstall (leave kind cluster running): `make -C kubernetes uninstall`
- Build, load and restart a single service (e.g. manager): `make -C kubernetes manager`
- Remove all: `make -C kubernetes clean-all`

The Kind flow loads the default Mapping image (`intel/scenescape-mapping:<version>`, MapAnything). To use VGGT, build it with `make -C mapping build-all`, load it with `make -C kubernetes load-image IMAGE=intel/scenescape-mapping VERSION=<version>-vggt`, and install the chart with `--set mapping.model=vggt`. See [Select the Mapping Model](../docs/user-guide/how-to-guides/deployment/deploy-kubernetes.md#select-the-mapping-model).

### Tracker + Analytics without demo media

From the repository root, build and deploy the Tracker profile to Kind with Helm:

```sh
SUPASS='<admin-password>' PGPASS='<database-password>' \
  make build-all demo-k8s DEPLOY_PROFILES=tracker
```

This builds the images, prepares the local Kind cluster, and installs the chart
with Tracker and Analytics enabled. The Scene Controller is omitted, and demo
video sources and scene imports are skipped. Helm still creates the supporting
Scenescape services, secrets, ConfigMaps, and persistent volume claims. Tracker
itself is stateless and connects to the chart's broker and Manager services, so
it does not need a dedicated Service, ConfigMap, or PVC.

To use a different Kubernetes cluster, install the chart directly and set
`tracker.enabled=true` and `reid.enabled=false` in the Helm values. The chart
automatically omits the Scene Controller when Tracker is enabled.

## Scenescape Only

If you already have a Kubernetes cluster you can use the Helm chart directly.

**Prerequisites:**

1. Install [Cert Manager](https://cert-manager.io/) in your cluster.

2. Copy common scripts to chart folder:

```sh
make copy-files
```

**Install with a custom admin password:**

```sh
helm install scenescape scenescape-chart -n <NAMESPACE> --create-namespace \
   --set supass=<YOUR_ADMIN_PASSWORD> \
   --set pgserver.password=<YOUR_POSTGRES_PASSWORD>
```

Optionally, prepare updated [values file](scenescape-chart/values.yaml) and save it as `values-custom.yaml`.

```sh
helm install scenescape scenescape-chart -n <NAMESPACE> --create-namespace \
   --set supass=<YOUR_ADMIN_PASSWORD> \
   --set pgserver.password=<YOUR_POSTGRES_PASSWORD> \
   --values values-custom.yaml
```

**To uninstall:**

```sh
helm uninstall scenescape -n <NAMESPACE>
```

## Video Source (sample/demo camera feeds)

The chart does not run a media server or sample-video containers itself — DL
Streamer Pipeline Server pipelines expect an RTSP source reachable at
`rtsp://mediaserver:8554/<camera-id>`. Each demo scene owns a self-contained
compose file with its own mediamtx, ffmpeg loopers and DL Streamer config:
[sample_data/demo_scenes/Retail/retail-video-compose.yaml](../sample_data/demo_scenes/Retail/retail-video-compose.yaml)
and
[sample_data/demo_scenes/Queuing/queuing-video-compose.yaml](../sample_data/demo_scenes/Queuing/queuing-video-compose.yaml).
Both declare a same-named `mediaserver` service, so combining them with two
`-f` flags merges them into one shared instance; used alone, a scene gets its
own private mediaserver. Run the standalone stack(s) on a host reachable from
the cluster, then point the cluster's `mediaserver` Service at it:

For a `kind` cluster created by this repo's `make` targets, `make -C
kubernetes video-source-up` does this automatically (joins the `kind` Docker
network so no extra steps are needed). For any other cluster, create the
network the stack expects and start only the media services (not the
video-analytics DLSPS services, which this chart's `kubeclient` creates
in-cluster):

```sh
docker network create scenescape_scenescape
export VIDEOSOURCE_PORT=8554
docker compose --project-directory . -f sample_data/demo_scenes/Retail/retail-video-compose.yaml \
  -f sample_data/demo_scenes/Queuing/queuing-video-compose.yaml \
  up -d mediaserver retail-cams queuing-cams
make -C kubernetes mediaserver-up VIDEOSOURCE_IP=<ip-of-that-host>
```

Remove the Kubernetes endpoint and stop the Docker media services with:

```sh
make -C kubernetes mediaserver-down
docker compose --project-directory . -f sample_data/demo_scenes/Retail/retail-video-compose.yaml \
  -f sample_data/demo_scenes/Queuing/queuing-video-compose.yaml down
```

For a DNS name instead of a bare IP, edit
[template/mediaserver.template](template/mediaserver.template) to use an
`ExternalName` Service instead.

## Environment Variables

### Proxy Configuration

If you're deploying Scenescape in an environment that requires proxy access, set these environment variables before running make commands:

```console
export http_proxy=http://your-proxy-server:port
export https_proxy=https://your-proxy-server:port
export no_proxy=localhost,127.0.0.1,.local,.svc,.svc.cluster.local,10.96.0.0/12,10.244.0.0/16,172.17.0.0/16
make -C kubernetes install
```

**What to put in `no_proxy` and why:**

- `localhost,127.0.0.1`: Ensures local traffic is not sent through the proxy.
- `.local`: Excludes local network hostnames.
- `.svc,.svc.cluster.local`: Excludes all Kubernetes service DNS names, so internal service-to-service traffic stays inside the cluster.
- `10.96.0.0/12`: Default Kubernetes service CIDR (adjust if your cluster uses a different range).
- `10.244.0.0/16`: Default pod CIDR for many CNI plugins (adjust if your cluster uses a different range).
- `172.17.0.0/16`: Typical Docker bridge network used by kind (Kubernetes IN Docker). Adjust if your Docker network uses a different subnet.

These values ensure that all internal cluster communication, including between pods and services, is not routed through the proxy. This is critical for correct operation of Kubernetes workloads, especially in kind clusters or any environment where internal networking must remain direct. Adjust the CIDRs if your cluster uses custom networking.

The proxy settings will be automatically detected and passed to all Scenescape containers as environment variables.

### NodePort Services

By default, Scenescape exposes its services using ClusterIP type services. If you want to expose them using NodePort services instead, set the following chart value:

```yaml
nodePort:
  enabled: true
```

### Chart Debug Mode

To enable Helm chart debugging (useful for troubleshooting deployment issues):

```console
export CHART_DEBUG=1
make -C kubernetes install
```

This enables the `chartdebug=true` setting in the Helm chart, which keeps debugging resources after installation.
