# Get Started with Auto Camera Calibration

## Prerequisites

- The hardware platform must be at least a 10th Generation Intel® Core™ i5 Processor or Intel® Xeon® Scalable processor, with at least 8+GB of RAM and 64+GB of storage.
- [How to build Auto Camera Calibration from source](How-to-build-source.md)

## Running the service using Docker Compose

- **Navigate to the Directory**:

  ```bash
  cd scenescape
  ```

- **Generate secrets**:

  ```bash
  make build-secrets
  ```

- **Start the service**:
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
  --name camcalibration \
  scenescape-camcalibration \
  camcalibration \
  --broker broker.scenescape.intel.com \
  --resturl https://web.scenescape.intel.com:443/api/v1
  ```

- **Note**:
  The `camcalibration` service **depends on** the `broker` and `web` services.
  Before starting this container, ensure that:
  - The **broker** service at `broker.scenescape.intel.com` is up and reachable.
  - The **web** service at `https://web.scenescape.intel.com:443` is accessible.

- **Verify the service**:
  Check that the service is running:

  ```bash
  docker ps
  ```

- **Stop the service**:

  ```bash
  docker stop camcalibration
  ```

- **Access autocalibration output through MQTT**:
  - Refer to [autocalibration-api.yaml](api-docs/autocalibration-api.yaml) on how to access auto calibration output
  - Refer to [Auto Calibration Sequence Diagram](overview.md#sequence-diagram-auto-camera-calibration-workflow)
