# Get Started with Scene Controller

## Prerequisites

<!-- AGENT: PREREQ - Validate hardware requirements before proceeding. -->

- The hardware platform must be at least a 10th Generation Intel® Core™ i5 Processor or Intel® Xeon® Scalable processor, with at least 8+GB of RAM and 64+GB of storage.
- [How to build Scene Controller from source](./get-started/build-from-source.md)

## Run the service using Docker

- **Navigate to the Directory**:

  <!-- AGENT: PREREQ - Change to repository root. -->

  ```bash
  cd scenescape
  ```

  **Expected output:** Shell prompt changes to the SceneScape repository root.

- **Generate secrets**:

  <!-- AGENT: PREREQ - Run before first container start to create TLS certs and auth tokens. -->

  ```bash
  make init-secrets
  ```

  **Expected output:** Secret files and certificates are generated under `manager/secrets/`.

- **Start the service**:
  <!-- AGENT: PREREQ - Ensure dependencies are running first (broker, web, ntp). -->

  Start the service using docker run:

  ```bash
  docker run --rm \
  --init \
  --network <COMPOSE_PROJECT_NAME>_scenescape \
  -v scenescape_vol-media:/home/scenescape/SceneScape/media \
  -v $(pwd)/controller/config/tracker-config.json:/home/scenescape/SceneScape/tracker-config.json \
  -v $(pwd)/controller/config/reid-config.json:/home/scenescape/SceneScape/reid-config.json \
  -v $(pwd)/manager/secrets/certs/scenescape-ca.pem:/run/secrets/certs/scenescape-ca.pem:ro \
  -v $(pwd)/manager/secrets/django:/run/secrets/django:ro \
  -v $(pwd)/manager/secrets/controller.auth:/run/secrets/controller.auth:ro \
  --name scene \
  scenescape-controller \
  controller \
  --broker broker.scenescape.intel.com \
  --tracker_config_file /home/scenescape/SceneScape/tracker-config.json \
  --reid_config_file /home/scenescape/SceneScape/reid-config.json \
  --ntp ntpserv
  ```

  **Expected output:** Scene Controller container starts and begins processing with no immediate startup errors.

- **Note**:
  <!-- AGENT: VERIFY - Confirm all listed dependencies are running before start. -->

  The `scene` service **depends on** the `broker`,`web` and `ntpserv`services.
  Before starting this container, ensure that:
  - The **broker** service at `broker.scenescape.intel.com` is up and reachable.
  - The **web** service at `https://web.scenescape.intel.com:443` is accessible.
  - The **ntpserv** service at `udp://<host-ip>:123` whihc maps to port `123/udp` inside the container.

- **Verify the service**:
  <!-- AGENT: VERIFY - Container must be present and running. -->

  Check that the service is running:

  ```bash
  docker ps
  ```

  <!-- AGENT: VERIFY - Expect container `scene` with status `Up`. -->

  **Expected output:** Container named 'scene' showing status "Up"

- **Stop the service**:

  <!-- AGENT: RUN - Cleanup command. -->

  ```bash
  docker stop scene
  ```

  **Expected output:** Container `scene` stops successfully.

- **Access scene controller output through MQTT**:
  <!-- AGENT: REF - MQTT API spec and workflow diagram references. -->
  - Refer to [scene-controller-api.yaml](./_assets/scene-controller-api.yaml) on how to access scene controller output
  - Refer to [scene controller sequence diagram](./controller.md#sequence-diagram-scene-controller-workflow)

## Running in Analytics-Only Mode

Analytics-only mode allows the Scene Controller to consume tracked objects from a separate Tracker service via MQTT instead of performing tracking internally. This is useful for distributed deployments where tracking and analytics are handled by separate services.

- **Enable analytics-only mode**:

  Add the `--analytics-only` flag to the docker run command:

  ```bash
  docker run --rm \
  --init \
  --network <COMPOSE_PROJECT_NAME>_scenescape \
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

  **Expected output:** Scene Controller starts in analytics-only mode and does not initialize internal tracking.

  Alternatively, use the environment variable:

  ```bash
  docker run --rm \
  --init \
  --network <COMPOSE_PROJECT_NAME>_scenescape \
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

  **Expected output:** Scene Controller starts with analytics-only behavior enabled from environment configuration.

- **Note**: In analytics-only mode (experimental feature):
  - The tracker is not initialized
  - Camera and scene detection data processing is skipped
  - The controller subscribes to tracked object data from MQTT topics published by the Tracker service
  - Analytics processing (regions, tripwires, sensors) continues to function normally
  - Child scenes are not supported in analytics-only mode
  - Sensors in Scene not supported and attribute persistence across moving objects not supported on data/scene MQTT topic (data available on events topic)
  - The following object fields are not available on `event` topic: `visibility`, `similarity`, `confidence`, `entered`, `exited`
  - The following object fields are not available on `data/regulated` topic: `visibility`, `similarity`, `confidence`

<!--hide_directive
:::{toctree}
:hidden:

get-started/build-from-source.md

:::
hide_directive-->
