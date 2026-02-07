# Get Started with Scene Controller

## Prerequisites

- The hardware platform must be at least a 10th Generation Intel® Core™ i5 Processor or Intel® Xeon® Scalable processor, with at least 8+GB of RAM and 64+GB of storage.
- [How to build Scene Controller from source](How-to-build-source.md)

## Running the service using Docker

- **Navigate to the Directory**:

  ```bash
  cd scenescape
  ```

- **Generate secrets**:

  ```bash
  make init-secrets
  ```

- **Start the service**:
  Start the service using docker run:

  ```bash
  docker run --rm \
  --init \
  --network scenescape \
  -v scenescape_vol-media:/home/scenescape/SceneScape/media \
  -v $(pwd)/controller/config/tracker-config.json:/home/scenescape/SceneScape/tracker-config.json \
  -v $(pwd)/manager/secrets/certs/scenescape-ca.pem:/run/secrets/certs/scenescape-ca.pem:ro \
  -v $(pwd)/manager/secrets/certs/scenescape-vdms-c.key:/run/secrets/certs/scenescape-vdms-c.key:ro \
  -v $(pwd)/manager/secrets/certs/scenescape-vdms-c.crt:/run/secrets/certs/scenescape-vdms-c.crt:ro \
  -v $(pwd)/manager/secrets/django:/run/secrets/django:ro \
  -v $(pwd)/manager/secrets/controller.auth:/run/secrets/controller.auth:ro \
  --name scene \
  scenescape-controller \
  controller \
  --broker broker.scenescape.intel.com \
  --ntp ntpserv
  ```

- **Note**:
  The `scene` service **depends on** the `broker`,`web` and `ntpserv`services.
  Before starting this container, ensure that:
  - The **broker** service at `broker.scenescape.intel.com` is up and reachable.
  - The **web** service at `https://web.scenescape.intel.com:443` is accessible.
  - The **ntpserv** service at `udp://<host-ip>:123` whihc maps to port `123/udp` inside the container.

- **Verify the service**:
  Check that the service is running:

  ```bash
  docker ps
  ```

- **Stop the service**:

  ```bash
  docker stop scene
  ```

- **Access scene controller output through MQTT**:
  - Refer to [scene-controller-api.yaml](api-docs/scene-controller-api.yaml) on how to access scene controller output
  - Refer to [scene controller sequence diagram](overview.md#sequence-diagram-scene-controller-workflow)

## Running in Analytics-Only Mode

Analytics-only mode allows the Scene Controller to consume tracked objects from a separate Tracker service via MQTT instead of performing tracking internally. This is useful for distributed deployments where tracking and analytics are handled by separate services.

- **Enable analytics-only mode**:

  Add the `--analytics-only` flag to the docker run command:

  ```bash
  docker run --rm \
  --init \
  --network scenescape \
  -v scenescape_vol-media:/home/scenescape/SceneScape/media \
  -v $(pwd)/controller/config/tracker-config.json:/home/scenescape/SceneScape/tracker-config.json \
  -v $(pwd)/manager/secrets/certs/scenescape-ca.pem:/run/secrets/certs/scenescape-ca.pem:ro \
  -v $(pwd)/manager/secrets/django:/run/secrets/django:ro \
  -v $(pwd)/manager/secrets/controller.auth:/run/secrets/controller.auth:ro \
  --name scene \
  scenescape-controller \
  controller \
  --broker broker.scenescape.intel.com \
  --ntp ntpserv \
  --analytics-only
  ```

  Alternatively, use the environment variable:

  ```bash
  docker run --rm \
  --init \
  --network scenescape \
  -e CONTROLLER_ENABLE_ANALYTICS_ONLY=true \
  -v scenescape_vol-media:/home/scenescape/SceneScape/media \
  -v $(pwd)/controller/config/tracker-config.json:/home/scenescape/SceneScape/tracker-config.json \
  -v $(pwd)/manager/secrets/certs/scenescape-ca.pem:/run/secrets/certs/scenescape-ca.pem:ro \
  -v $(pwd)/manager/secrets/django:/run/secrets/django:ro \
  -v $(pwd)/manager/secrets/controller.auth:/run/secrets/controller.auth:ro \
  --name scene \
  scenescape-controller \
  controller \
  --broker broker.scenescape.intel.com \
  --ntp ntpserv
  ```

- **Note**: In analytics-only mode (experimental feature):
  - The tracker is not initialized
  - Camera and scene detection data processing is skipped
  - The controller subscribes to tracked object data from MQTT topics published by the Tracker service
  - Analytics processing (regions, tripwires, sensors) continues to function normally
  - Child scenes are not supported in analytics-only mode
  - Sensors in Scene not supported and attribute persistence across moving objects not supported on data/scene MQTT topic (data avaliable on events topic).
