# Get Started with Cluster Analytics

## Prerequisites

- The hardware platform must be at least a 10th Generation Intel® Core™ i5 Processor or Intel® Xeon® Scalable processor, with at least 8+GB of RAM and 64+GB of storage.
- [How to build Cluster Analytics from source](How-to-build-source.md)

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

- **Note**:
  The `cluster-analytics` service **depends on** the `broker` service.
  Before starting this container, ensure that:
  - The **broker** service at `broker.scenescape.intel.com` is up and reachable.

- **Verify the service**:
  Check that the service is running:

  ```bash
  docker ps
  ```

- **Stop the service**:

  ```bash
  docker stop cluster_analytics_manual
  ```

- **Access autocalibration output through MQTT**:
  - Refer to [Cluster Analytics Sequence Diagram](overview.md#data-flow-diagram)
