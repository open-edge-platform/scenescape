<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Run the LiDAR-Intersection Fusion Demo

- **Time to Complete:** 30-45 minutes (plus first-time PointPillars model build)

This guide walks through running the **LiDAR-Intersection fusion demo**, a
separate, opt-in Scenescape demo that fuses a recorded LiDAR point-cloud
stream with a recorded camera image sequence of the same real-world
intersection. It is fully independent from the default apriltag/queuing demo:
all of its data, scene configuration, and pipeline assets live under
[sample_data/lidar_intersection/](../../../sample_data/lidar_intersection)
and it is started with its own `LIDAR_DEMO` environment variable, so it never
affects the standard `make demo` deployment.

> **Note:** No source-code patches are required to the Manager, Scene
> Controller, or any other microservice to run this demo. The "Lidar
> Intersection" scene is seeded using Scenescape's existing
> [scene import](./build-a-scene/create-new-scene.md#importing-the-scene)
> feature, and camera/LiDAR sensor fusion is handled by the Scene
> Controller's existing multi-sensor tracking logic - the same mechanism used
> to fuse any two overlapping camera/sensor feeds.

## What this demo adds

| Asset                                           | Purpose                                                                     |
| ------------------------------------------------ | ---------------------------------------------------------------------------- |
| `sample_data/docker-compose.lidar-override.yml` | Opt-in Compose override adding the `lidar-data-init`, `lidar-model-init`, and `lidar-stream` services |
| `dlstreamer-pipeline-server/user_scripts/lidar_publisher.py` | Runs the LiDAR (PointPillars) and camera (person-vehicle-bike) GStreamer pipelines and publishes detections over MQTT |
| `sample_data/lidar_intersection/`               | Scene config, map image, scene-import ZIP, recorded LiDAR/camera frames, and the PointPillars model installer, all scoped to this demo |

## Prerequisites

- Complete [Installation](../get-started/installation.md) Steps 1-2 (get the
  source and build the container images) at least once.
- A GPU is optional. The demo defaults to CPU inference for both the LiDAR
  and camera branches so it works on any supported target; see
  [Using GPU acceleration](#using-gpu-acceleration) below to switch to GPU.

## Step 1: Enable the demo

Add `LIDAR_DEMO=true` to any of the normal `make demo*` targets. For example,
to start the core demo plus the LiDAR-Intersection fusion demo:

```bash
export SUPASS=<password>
make demo LIDAR_DEMO=true
```

`LIDAR_DEMO=true` can be combined with any other demo target the same way
`REID_BACKEND` can, for example:

```bash
make demo-reid LIDAR_DEMO=true REID_BACKEND=qdrant
make demo-all LIDAR_DEMO=true
```

This starts three extra containers, on top of the normal demo services:

| Service            | Role                                                                                                          |
| ------------------ | -------------------------------------------------------------------------------------------------------------- |
| `lidar-data-init`  | One-shot: extracts the recorded `.bin` LiDAR frames and `.jpg` camera frames into the shared sample-data volume |
| `lidar-model-init` | One-shot: builds and installs the PointPillars OpenVINO model + GStreamer inference extension into the shared models volume (first run only; can take several minutes) |
| `lidar-stream`     | Long-running: runs both GStreamer pipelines and publishes fused-ready detections over MQTT                     |

Check the one-shot containers completed successfully, and that `lidar-stream`
is running:

```bash
docker compose ps lidar-data-init lidar-model-init lidar-stream
docker compose logs -f lidar-stream
```

You should see log lines like:

```text
[lidar-publisher] lidar_sensor=intersection-lidar1 cam_sensor=intersection-cam1 ...
[camera-publisher] Connected to broker.scenescape.intel.com:1883
[lidar-publisher] frames=100 fps=10.0 objects={'vehicle': 2, 'cyclist': 1}
```

## Step 2: Import the "Lidar Intersection" scene

The demo publishes detections for sensors `intersection-lidar1` and
`intersection-cam1`, but the scene itself (map, camera/sensor poses) is not
seeded automatically - import it once per fresh deployment (per `make
demo-close` volume reset).

### Option A: Using the Web UI

1. Open `https://localhost` (or `https://<hostname>`) and log in with
   `admin` / the `SUPASS` password.
2. Click **Scenes**, then **+ Import Scene**.
3. Upload
   [sample_data/lidar_intersection/LidarIntersection-scene-import.zip](../../../sample_data/lidar_intersection/LidarIntersection-scene-import.zip).
4. Click **Import**.

### Option B: Using `curl`

```bash
TOKEN=$(curl --location --insecure -X POST \
  -d "username=admin&password=$SUPASS" \
  https://localhost/api/v1/auth | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

curl -k -X POST \
  -H "Authorization: Token $TOKEN" \
  -F "zipFile=@sample_data/lidar_intersection/LidarIntersection-scene-import.zip" \
  https://localhost/api/v1/import-scene/
```

After the import, a new **Lidar Intersection** scene appears with the
`intersection-cam1` camera and `intersection-lidar1` LiDAR sensor already
positioned and calibrated.

## Step 3: Verify fusion is working

1. Open the **Lidar Intersection** scene in the UI - tracked vehicles and
   cyclists should appear moving through the intersection, sourced from
   either sensor.
2. Or inspect the raw per-sensor detections directly (the broker is not
   published to the host by default, so sniff traffic from inside the
   container):

   ```bash
   docker compose exec broker mosquitto_sub -h localhost -p 1883 \
     --cafile /mosquitto/secrets/certs/scenescape-ca.pem --insecure -v \
     -t 'scenescape/data/camera/intersection-lidar1' \
     -t 'scenescape/data/camera/intersection-cam1'
   ```

   Each message includes a `"source"` sensor id and category-grouped
   `objects`; over time you should see the same real-world vehicle tracked
   by both sensors and fused into a single tracked object in the scene.

## Stopping the demo

```bash
make demo-close
```

This stops and removes all demo services and volumes, including the LiDAR
demo containers - the same command used for any other demo, no separate
teardown step is needed.

## Using GPU acceleration

Both branches default to `LIDAR_DEVICE=CPU` / `CAM_DEVICE=CPU`. To use GPU
inference:

1. In `sample_data/docker-compose.lidar-override.yml`, uncomment the
   `devices`, `group_add`, and `device_cgroup_rules` entries under the
   `lidar-stream` service.
2. Set `LIDAR_DEVICE=GPU` (and optionally `CAM_DEVICE=GPU`) under the same
   service's `environment` section.

## Configuration reference

The `lidar-stream` service reads its configuration from environment
variables (see the commented examples in
`sample_data/docker-compose.lidar-override.yml`):

| Variable                | Default                        | Description                                  |
| ------------------------ | ------------------------------- | ----------------------------------------------- |
| `LIDAR_SENSOR_ID`        | `intersection-lidar1`           | Sensor id used for the MQTT topic and payload |
| `LIDAR_DEVICE`           | `CPU`                           | OpenVINO device for PointPillars inference    |
| `LIDAR_SCORE_THRESHOLD`  | `0.70`                          | Minimum detection confidence to publish       |
| `LIDAR_FRAME_RATE`       | `10`                            | Target playback frame rate                    |
| `LIDAR_LOOP`             | `true`                          | Loop the recorded frame sequence               |
| `CAM_SENSOR_ID`          | `intersection-cam1`             | Sensor id used for the MQTT topic and payload |
| `CAM_DEVICE`             | `CPU`                           | OpenVINO device for the camera detector        |
| `CAM_SCORE_THRESHOLD`    | `0.8`                           | Minimum detection confidence to publish       |
| `CAM_DETECTION_LABELS`   | `vehicle,cyclist`               | Comma-separated category allow-list           |

## Troubleshooting

- **`lidar-model-init` fails or times out:** it compiles a GStreamer
  extension from `openvino_contrib` source on first run and needs outbound
  network access (respects `HTTPS_PROXY`/`https_proxy`); check `docker
  compose logs lidar-model-init`.
- **No detections published:** confirm `lidar-data-init` completed
  successfully (`docker compose logs lidar-data-init`) - the pipelines need
  the extracted `.bin`/`.jpg` frames in the shared sample-data volume.
- **Scene appears empty after `make demo-close` + a fresh `make demo
  LIDAR_DEMO=true`:** the scene import (Step 2) is not automatic and must be
  repeated after every volume reset.
