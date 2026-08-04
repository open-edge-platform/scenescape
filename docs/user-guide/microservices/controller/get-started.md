# Get Started with Scene Controller

## Prerequisites

- The hardware platform must be at least a 10th Generation Intel® Core™ i5 Processor or Intel® Xeon® Scalable processor, with at least 8+GB of RAM and 64+GB of storage.
- [How to build Scene Controller from source](./get-started/build-from-source.md)

## Run the service using Docker

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
  -v scenescape_vol-media:/home/scenescape/Scenescape/media \
  -v $(pwd)/controller/config/tracker-config.json:/home/scenescape/Scenescape/tracker-config.json \
  -v $(pwd)/controller/config/reid-config.json:/home/scenescape/Scenescape/reid-config.json \
  -v $(pwd)/controller/config/pose-adjustment-route.json:/home/scenescape/Scenescape/pose-adjustment-route.json \
  -v $(pwd)/manager/secrets/certs/scenescape-ca.pem:/run/secrets/certs/scenescape-ca.pem:ro \
  -v $(pwd)/manager/secrets/certs/scenescape-reid.crt:/run/secrets/certs/scenescape-reid.crt:ro \
  -v $(pwd)/manager/secrets/certs/scenescape-reid.key:/run/secrets/certs/scenescape-reid.key:ro \
  -v $(pwd)/manager/secrets/django:/run/secrets/django:ro \
  -v $(pwd)/manager/secrets/controller.auth:/run/secrets/controller.auth:ro \
  --name scene \
  intel/scenescape-controller \
  controller \
  --broker broker.scenescape.intel.com \
  --tracker_config_file /home/scenescape/Scenescape/tracker-config.json \
  --reid_config_file /home/scenescape/Scenescape/reid-config.json \
  --ntp ntpserv
  ```

- **Note**:
  The `scene` service **depends on** the `broker`,`web` and `ntpserv`services.
  Before starting this container, ensure that:
  - The **broker** service at `broker.scenescape.intel.com` is up and reachable.
  - The **web** service at `https://web.scenescape.intel.com:443` is accessible.
  - The **ntpserv** service at `udp://<host-ip>:123` whihc maps to port `123/udp` inside the container.
  - For Extended ReID, a vector database is reachable at the shared defaults (`reid.scenescape.intel.com:55555`, TLS). Mount the shared `scenescape-reid` client certs as shown above. Select the backend with `REID_DATABASE` (`VDMS` or `QDRANT`). See [How to enable re-identification](../../other-topics/how-to-enable-reidentification.md).

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
  - Refer to [scene-controller-api.yaml](./_assets/scene-controller-api.yaml) on how to access scene controller output
  - Refer to [scene controller sequence diagram](./controller.md#sequence-diagram-scene-controller-workflow)

## Tracker + Analytics (no local Controller tracker)

For deployments where a separate Tracker publishes tracks on MQTT, run the
[Analytics microservice](../analytics/analytics.md) with the Tracker (for example
`make demo-tracker` / `--profile tracker`). Do not use the former Controller
`--analytics-only` flag — it has been removed. Controller-proper stacks use
`--profile controller` (Scene Controller + Analytics).

## Enabling Pose Adjustment

When using a pose estimation model (e.g. `yolo11n-pose`) in the DL Streamer video pipeline, the Scene Controller can use pose keypoints to refine bounding boxes for supported detection types before projecting them into world coordinates. This improves localization accuracy. The feature is disabled by default.

- **Enable pose adjustment via CLI flag**:

  Add the `--pose-adjustment` flag to the docker run command:

  ```bash
  docker run --rm \
  --init \
  --network scenescape \
  -v scenescape_vol-media:/home/scenescape/Scenescape/media \
  -v $(pwd)/controller/config/tracker-config.json:/home/scenescape/Scenescape/tracker-config.json \
  -v $(pwd)/controller/config/reid-config.json:/home/scenescape/Scenescape/reid-config.json \
  -v $(pwd)/manager/secrets/certs/scenescape-ca.pem:/run/secrets/certs/scenescape-ca.pem:ro \
  -v $(pwd)/manager/secrets/certs/scenescape-reid.crt:/run/secrets/certs/scenescape-reid.crt:ro \
  -v $(pwd)/manager/secrets/certs/scenescape-reid.key:/run/secrets/certs/scenescape-reid.key:ro \
  -v $(pwd)/manager/secrets/django:/run/secrets/django:ro \
  -v $(pwd)/manager/secrets/controller.auth:/run/secrets/controller.auth:ro \
  --name scene \
  intel/scenescape-controller \
  controller \
  --broker broker.scenescape.intel.com \
  --tracker_config_file /home/scenescape/Scenescape/tracker-config.json \
  --reid_config_file /home/scenescape/Scenescape/reid-config.json \
  --pose_adjustment_config_file /home/scenescape/Scenescape/pose-adjustment-route.json \
  --ntp ntpserv \
  --pose-adjustment
  ```

  Alternatively, use the environment variable:

  ```bash
  docker run --rm \
  --init \
  --network scenescape \
  -e CONTROLLER_ENABLE_POSE_ADJUSTMENT=true \
  -v scenescape_vol-media:/home/scenescape/Scenescape/media \
  -v $(pwd)/controller/config/tracker-config.json:/home/scenescape/Scenescape/tracker-config.json \
  -v $(pwd)/controller/config/reid-config.json:/home/scenescape/Scenescape/reid-config.json \
  -v $(pwd)/controller/config/pose-adjustment-route.json:/home/scenescape/Scenescape/pose-adjustment-route.json \
  -v $(pwd)/manager/secrets/certs/scenescape-ca.pem:/run/secrets/certs/scenescape-ca.pem:ro \
  -v $(pwd)/manager/secrets/certs/scenescape-reid.crt:/run/secrets/certs/scenescape-reid.crt:ro \
  -v $(pwd)/manager/secrets/certs/scenescape-reid.key:/run/secrets/certs/scenescape-reid.key:ro \
  -v $(pwd)/manager/secrets/django:/run/secrets/django:ro \
  -v $(pwd)/manager/secrets/controller.auth:/run/secrets/controller.auth:ro \
  --name scene \
  intel/scenescape-controller \
  controller \
  --broker broker.scenescape.intel.com \
  --tracker_config_file /home/scenescape/Scenescape/tracker-config.json \
  --reid_config_file /home/scenescape/Scenescape/reid-config.json \
  --pose_adjustment_config_file /home/scenescape/Scenescape/pose-adjustment-route.json \
  --ntp ntpserv
  ```

- **Configure label routing via `pose-adjustment-route.json`**:

  ```json
  {
    "person": ["human", "pedestrian"]
  }
  ```

- **Note**: This feature requires the DL Streamer video pipeline to use a pose estimation model (e.g. `yolo11n-pose`) that provides keypoint data. See the [DL Streamer Pipeline Server documentation](/dlstreamer-pipeline-server/README.md#enable-pose-estimation) for pipeline setup instructions.

<!--hide_directive
:::{toctree}
:hidden:

get-started/build-from-source.md

:::
hide_directive-->
