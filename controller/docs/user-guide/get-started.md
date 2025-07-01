# Get Started with Scene Controller

## Prerequisites

- The hardware platform must be at least a 10th Generation Intel® Core™ i5 Processor or Intel® Xeon® Scalable processor, with at least 8+GB of RAM and 64+GB of storage.
- [How to build Scene Controller from source](How-to-build-source.md)

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
