# Get Started

## Prerequisites

<!-- AGENT: Validate hardware requirements before proceeding -->

- The hardware platform must be at least a 10th Generation Intel® Core™ i5 Processor or Intel® Xeon® Scalable processor, with at least 8+GB of RAM and 64+GB of storage.
- [Build Auto Camera Calibration from source](./get-started/build-from-source.md).

## Run the service using Docker Compose

- **Navigate to the Directory**:

  <!-- AGENT: Change to repository root -->

  ```bash
  cd scenescape
  ```

  **Expected output:** Shell prompt changes to the SceneScape repository root.

- **Generate secrets**:

  <!-- AGENT: CRITICAL: Must run before first container start -->

  ```bash
  make build-secrets
  ```

  **Expected output:** Required secret files and certificates are generated.

- **Start the service**:
  <!-- AGENT: Dependency check - web service must be running first -->

  Start the service using docker run:

  ```bash
  docker run --rm \
  --init \
  --cap-add=SYS_ADMIN \
  --device=/dev/fuse \
  --security-opt apparmor:unconfined \
  --network scenescape \
  -e EGL_PLATFORM=surfaceless \
  -e DBROOT \
  -v scenescape_vol-media:/workspace/media \
  -v scenescape_vol-datasets:/workspace/datasets \
  -v $(pwd)/manager/secrets/certs/scenescape-ca.pem:/run/secrets/certs/scenescape-ca.pem:ro \
  -v $(pwd)/manager/secrets/django:/run/secrets/django:ro \
  -v $(pwd)/manager/secrets/calibration.auth:/run/secrets/calibration.auth:ro \
  --name autocalibration \
  scenescape-autocalibration \
  autocalibration \
  --resturl https://web.scenescape.intel.com:443/api/v1
  ```

  **Expected output:** Autocalibration container starts and connects to the Manager REST API.

- **Note**:
  <!-- AGENT: List of service dependencies before starting -->

  The `autocalibration` service **depends on** the `web` service.
  Before starting this container, ensure that:
  - The **web** service at `https://web.scenescape.intel.com:443` is accessible.

- **Verify the service**:
  <!-- AGENT: Health check - container must be present and running -->

  Check that the service is running:

  ```bash
  docker ps
  ```

  <!-- AGENT: Expected: Container named 'autocalibration' with status 'Up' -->

  **Expected output:** Container named 'autocalibration' showing status "Up"

- **Stop the service**:

  <!-- AGENT: Cleanup command -->

  ```bash
  docker stop autocalibration
  ```

  **Expected output:** Container `autocalibration` stops successfully.

- **Access autocalibration output through MQTT**:
  <!-- AGENT: Reference for MQTT output spec and workflow -->
  - Refer to [autocalibration-api.yaml](./_assets/autocalibration-api.yaml) on how to access
    auto calibration output.
  - Refer to [Auto Calibration Sequence Diagram](./auto-calibration.md#sequence-diagram-auto-camera-calibration-workflow)

<!--hide_directive
:::{toctree}
:hidden:

get-started/build-from-source

:::
hide_directive-->
