# Get Started

## Prerequisites

<!-- AGENT: Validate hardware requirements before proceeding -->

- The hardware platform must be at least a 10th Generation Intel® Core™ i5 Processor or Intel® Xeon® Scalable processor, with at least 8+GB of RAM and 64+GB of storage.
- [How to build Cluster Analytics from source](./get-started/build-from-source.md)

## Run the service using Docker Compose

- **Navigate to the Directory**:

  <!-- AGENT: Change to repository root -->

  ```bash
  cd scenescape
  ```

- **Generate secrets**:

  <!-- AGENT: CRITICAL: Must run before first container start -->

  ```bash
  make build-secrets
  ```

- **Start the service**:

<!-- AGENT: Dependency check - broker must be running first -->

> **Note:**
> The `cluster-analytics` service **depends on** the `broker` service.
> Before starting this container, ensure that the **broker** service at
> `broker.scenescape.intel.com` is up and reachable.

<!-- AGENT: Docker run command to start service -->

Start the service using docker run:

```bash
docker run --rm \
  --init \
  --cap-add=SYS_ADMIN \
  --device=/dev/fuse \
  --security-opt apparmor:unconfined \
  --network scenescape_scenescape \
  -e EGL_PLATFORM=surfaceless \
  -e DBROOT \
  -v $(pwd)/manager/secrets/certs/scenescape-ca.pem:/run/secrets/certs/scenescape-ca.pem:ro \
  -v $(pwd)/manager/secrets/django:/run/secrets/django:ro \
  -v $(pwd)/manager/secrets/calibration.auth:/run/secrets/calibration.auth:ro \
  --name cluster_analytics_manual \
  scenescape-cluster-analytics \
  --broker broker.scenescape.intel.com
```

- **Verify the service**:
  <!-- AGENT: Health check - container must be present and running -->

  Check that the service is running:

  ```bash
  docker ps
  ```

  <!-- AGENT: Expected: Container named 'cluster_analytics_manual' with status 'Up' -->

  **Expected output:** Container named 'cluster_analytics_manual' showing status "Up"

- **Stop the service**:

  <!-- AGENT: Cleanup command -->

  ```bash
  docker stop cluster_analytics_manual
  ```

- **Access autocalibration output through MQTT**:
  <!-- AGENT: Reference for MQTT output spec and workflow -->
  - Refer to [Cluster Analytics Sequence Diagram](./cluster-analytics.md#data-flow-diagram)

## Suporting Resources

- Learn how to [Configure Spatial Analytics in Intel® SceneScape](../../building-a-scene/how-to-configure-spatial-analytics.md).
- Learn how to [Work with Spatial Analytics Data](../../using-intel-scenescape/working-with-spatial-analytics-data.md).

<!--hide_directive
:::{toctree}
:hidden:

get-started/build-from-source.md

:::
hide_directive-->
