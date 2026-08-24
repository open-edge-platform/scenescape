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

> **Note:** The scene itself is seeded using Scenescape's existing
> [scene import](./build-a-scene/create-new-scene.md#importing-the-scene)
> feature - no Manager DB-fixture changes needed. Camera/LiDAR sensor fusion
> is handled entirely by the Scene Controller's existing multi-sensor
> tracking logic, unmodified. A small set of demo-only Manager source
> changes (default vehicle/cyclist objects, debug source labels in the UI)
> are kept as a single patch under `sample_data/lidar_intersection/patches/`
> and are applied to the source tree automatically by `make build-core`/
> `make build-all` only when `LIDAR_DEMO=true` - a normal build/demo never
> touches these files. See
> [Demo-only Manager patch](#demo-only-manager-patch) below for details.

## What this demo adds

| Asset                                           | Purpose                                                                     |
| ------------------------------------------------ | ---------------------------------------------------------------------------- |
| `sample_data/lidar_intersection/docker-compose.lidar-override.yml` | Opt-in Compose override adding the `lidar-scene-init`, `lidar-data-init`, `lidar-model-init`, and `lidar-stream` services |
| `sample_data/lidar_intersection/lidar_publisher.py` | Runs the LiDAR (PointPillars) and camera (person-vehicle-bike) GStreamer pipelines and publishes detections over MQTT |
| `sample_data/lidar_intersection/patches/0001-lidar-fusion-manager.patch` | Demo-only Manager source changes, applied automatically when building with `LIDAR_DEMO=true` |
| `sample_data/lidar_intersection/`               | Scene config, map image, scene-import ZIP, recorded LiDAR/camera frames, and the PointPillars model installer, all scoped to this demo |

## Prerequisites

- Complete [Installation](../get-started/installation.md) Steps 1-2 (get the
  source and build the container images) at least once.
- An Intel GPU is used **by default** for the LiDAR (PointPillars) inference
  branch, and requires the host to have `/dev/dri` and the Intel GPU driver
  installed. The camera branch defaults to CPU (a lighter model that runs
  fine without a GPU). Install/verify drivers with the
  [DL Streamer prerequisites script](https://github.com/open-edge-platform/dlstreamer/blob/main/scripts/DLS_install_prerequisites.sh)
  (`./DLS_install_prerequisites.sh`) or see the
  [DL Streamer system requirements](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dlstreamer/get_started/system_requirements.html)
  and [install guide](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dlstreamer/get_started/install/install_guide_ubuntu.html)
  for details (NPU is not used by this demo, but the same script covers it).
  > **Performance note:** running the LiDAR branch without a GPU
  > (`LIDAR_DEVICE=CPU`, see [Using GPU acceleration](#using-gpu-acceleration))
  > works on any target, but PointPillars 3-D inference on CPU is
  > significantly slower than on GPU and can noticeably drop below the
  > `LIDAR_FRAME_RATE` target (choppy playback, growing detection latency).
  > Prefer GPU whenever available.

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

This starts four extra containers, on top of the normal demo services:

| Service            | Role                                                                                                          |
| ------------------ | -------------------------------------------------------------------------------------------------------------- |
| `lidar-scene-init` | One-shot: seeds the "Lidar Intersection" scene, camera, and sensor via the Scene Import REST API (idempotent - skips if the scene already exists) |
| `lidar-data-init`  | One-shot: extracts the recorded `.bin` LiDAR frames and `.jpg` camera frames into the shared sample-data volume |
| `lidar-model-init` | One-shot: builds and installs the PointPillars OpenVINO model + GStreamer inference extension into the shared models volume (first run only; can take several minutes) |
| `lidar-stream`     | Long-running: runs both GStreamer pipelines and publishes fused-ready detections over MQTT                     |

Check the one-shot containers completed successfully, and that `lidar-stream`
is running:

```bash
docker compose ps lidar-scene-init lidar-data-init lidar-model-init lidar-stream
docker compose logs -f lidar-stream
```

You should see log lines like:

```text
[lidar-publisher] lidar_sensor=intersection-lidar1 cam_sensor=intersection-cam1 ...
[camera-publisher] Connected to broker.scenescape.intel.com:1883
[lidar-publisher] frames=100 fps=10.0 objects={'vehicle': 2, 'cyclist': 1}
```

## Step 2: Scene is seeded automatically

`lidar-scene-init` waits for the Manager (`web`) to become healthy, then
imports
[sample_data/lidar_intersection/LidarIntersection-scene-import.zip](../../../sample_data/lidar_intersection/LidarIntersection-scene-import.zip)
via the Scene Import REST API (`POST /api/v1/import-scene/`) - no manual
step, and no Manager source or DB-fixture changes are needed. It checks
`GET /api/v1/scenes` first and skips the import if a scene named "Lidar
Intersection" already exists, so it's safe to leave enabled across restarts;
after a full `make demo-close` (which wipes volumes) it re-imports cleanly
on the next `make demo LIDAR_DEMO=true`.

```bash
docker compose logs lidar-scene-init
```

After it runs, a new **Lidar Intersection** scene appears with the
`intersection-cam1` camera and `intersection-lidar1` LiDAR sensor already
positioned and calibrated.

> **Manual re-import:** if you ever need to force a re-import (e.g. after
> editing `LidarIntersection-scene-import.zip`), delete the existing "Lidar
> Intersection" scene from the UI (or via the API) and re-run
> `docker compose up -d lidar-scene-init`, or import the same ZIP manually
> via **Scenes -> + Import Scene** in the UI, or `curl -F
> zipFile=@sample_data/lidar_intersection/LidarIntersection-scene-import.zip`
> against `/api/v1/import-scene/` (see
> [Importing the scene](./build-a-scene/create-new-scene.md#importing-the-scene)
> for the full token/curl pattern).

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

The LiDAR branch defaults to `LIDAR_DEVICE=GPU`, with the `lidar-stream`
service's `devices`/`group_add`/`device_cgroup_rules` already enabled to
pass through `/dev/dri`. Make sure the host has an Intel GPU driver
installed first (see [Prerequisites](#prerequisites)). The camera branch
defaults to `CAM_DEVICE=CPU`; set `CAM_DEVICE=GPU` too if you want the
camera detector to also use the GPU.

**Falling back to CPU** (e.g. no GPU available): in
`sample_data/lidar_intersection/docker-compose.lidar-override.yml`,
comment out the `devices`, `group_add`, and `device_cgroup_rules` entries
under the `lidar-stream` service, and set `LIDAR_DEVICE=CPU` under the same
service's `environment` section. CPU inference works but is noticeably
slower (see the performance note in [Prerequisites](#prerequisites)).

## Configuration reference

The `lidar-stream` service reads its configuration from environment
variables (see the commented examples in
`sample_data/lidar_intersection/docker-compose.lidar-override.yml`):

| Variable                | Default                        | Description                                  |
| ------------------------ | ------------------------------- | ----------------------------------------------- |
| `LIDAR_SENSOR_ID`        | `intersection-lidar1`           | Sensor id used for the MQTT topic and payload |
| `LIDAR_DEVICE`           | `GPU`                           | OpenVINO device for PointPillars inference (`CPU` fallback is much slower) |
| `LIDAR_SCORE_THRESHOLD`  | `0.70`                          | Minimum detection confidence to publish       |
| `LIDAR_FRAME_RATE`       | `10`                            | Target playback frame rate                    |
| `LIDAR_LOOP`             | `true`                          | Loop the recorded frame sequence               |
| `CAM_SENSOR_ID`          | `intersection-cam1`             | Sensor id used for the MQTT topic and payload |
| `CAM_DEVICE`             | `CPU`                           | OpenVINO device for the camera detector        |
| `CAM_SCORE_THRESHOLD`    | `0.8`                           | Minimum detection confidence to publish       |
| `CAM_DETECTION_LABELS`   | `vehicle,cyclist`               | Comma-separated category allow-list           |

## Demo-only Manager patch

`sample_data/lidar_intersection/patches/0001-lidar-fusion-manager.patch` contains a
small set of changes that are only relevant to this demo, so they are kept
out of the normal source tree and applied on top of it instead:

| Change                                                          | File(s)                                                                 |
| ------------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| Seed default `vehicle`/`cyclist` objects (size, tracking radius, mark color) | `manager/src/manager/management/commands/init_default_assets.py` (new), `manager/src/manager/migrations/0003_default_asset3d_objects.py` (new), `manager/config/scenescape-init` |
| Debug UI: label/style marks by detection source (lidar vs camera), add cyclist mark styling | `manager/src/manager/static/js/marks.js`, `manager/src/manager/static/js/assetmanager.js`, `manager/src/manager/static/css/style.css` |

The Scene Controller itself is unmodified - LiDAR/camera fusion and rotation
handling use its existing, generic multi-sensor tracking logic.

`make build-core`/`make build-all` apply this patch to the working tree
automatically (and only) when `LIDAR_DEMO=true`, build the `manager`
image with it applied, then automatically revert it - the patch
only needs to be on disk while that image is being built (it's baked
into the image layers), so:

```bash
SUPASS=<password> make build-core demo LIDAR_DEMO=true
```

builds the patched image, reverts the source tree back to normal, and
starts the demo, all in one step. Your working tree stays clean throughout -
`git status` should never show `manager/` files as modified
because of this demo, so there's nothing extra to commit/push for it beyond
this demo's own files under `sample_data/lidar_intersection/`, `Makefile`,
and docs. The apply/revert cycle is idempotent - re-running the same command
does not re-apply, fail, or leave anything applied. To manually apply or
remove the patch (e.g. to inspect a diff without building):

```bash
make apply-lidar-patch    # apply sample_data/lidar_intersection/patches/0001-... to the working tree
make revert-lidar-patch   # revert it back to the unpatched source
```

> **Note:** if a build is interrupted between `apply-lidar-patch` and the
> automatic revert (e.g. `Ctrl+C` mid-build), `manager/` files may be
> left patched in your working tree. Run `make revert-lidar-patch` to clean
> up, or check `git status` before committing/pushing.

## Troubleshooting

- **`lidar-scene-init` fails to authenticate:** confirm `SUPASS` matches the
  password used for the running deployment (it must be the same value passed
  to `make demo LIDAR_DEMO=true`); check `docker compose logs lidar-scene-init`.
- **`lidar-model-init` fails or times out:** it compiles a GStreamer
  extension from `openvino_contrib` source on first run and needs outbound
  network access (respects `HTTPS_PROXY`/`https_proxy`); check `docker
  compose logs lidar-model-init`.
- **No detections published:** confirm `lidar-data-init` completed
  successfully (`docker compose logs lidar-data-init`) - the pipelines need
  the extracted `.bin`/`.jpg` frames in the shared sample-data volume.
- **Scene appears empty (or missing) after `make demo-close` + a fresh `make
  demo LIDAR_DEMO=true`:** check `docker compose logs lidar-scene-init` -
  it depends on `web` being healthy first, so a slow Manager startup can
  briefly delay the import; the container exits after one attempt and is not
  retried automatically. Re-trigger it with `docker compose up -d
  lidar-scene-init` if needed.
