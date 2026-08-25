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
> feature - no Manager DB-fixture changes needed. All demo-only source
> changes (default vehicle/cyclist objects, debug source labels in the UI,
> carrying a `source` field and a LiDAR heading-disambiguation fix through
> Controller tracking, and forwarding that field through scene_common and
> Analytics) are kept as one patch per component under
> `sample_data/lidar_intersection/patches/` and are applied to the source
> tree automatically by `make build-core`/`make build-all` only when
> `LIDAR_DEMO=true` - a normal build/demo never touches these files. See
> [Demo-only patches](#demo-only-patches) below for details.

## What this demo adds

| Asset                                                              | Purpose                                                                                                                                 |
| ------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------- |
| `sample_data/lidar_intersection/docker-compose.lidar-override.yml` | Opt-in Compose override adding the `lidar-scene-init`, `lidar-data-init`, `lidar-model-init`, and `lidar-stream` services               |
| `sample_data/lidar_intersection/lidar_publisher.py`                | Runs the LiDAR (PointPillars) and camera (person-vehicle-bike) GStreamer pipelines and publishes detections over MQTT                   |
| `sample_data/lidar_intersection/patches/`                          | Demo-only patches, one per component (Manager, Controller, scene_common, Analytics), applied automatically when building with `LIDAR_DEMO=true` |
| `sample_data/lidar_intersection/`                                  | Scene config, map image, scene-import ZIP, recorded LiDAR/camera frames, and the PointPillars model installer, all scoped to this demo  |

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
make demo-all LIDAR_DEMO=true
```

This starts four extra containers, on top of the normal demo services:

| Service            | Role                                                                                                                                                                   |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `lidar-scene-init` | One-shot: seeds the "Lidar Intersection" scene, camera, and sensor via the Scene Import REST API (idempotent - skips if the scene already exists)                      |
| `lidar-data-init`  | One-shot: extracts the recorded `.bin` LiDAR frames and `.jpg` camera frames into the shared sample-data volume                                                        |
| `lidar-model-init` | One-shot: builds and installs the PointPillars OpenVINO model + GStreamer inference extension into the shared models volume (first run only; can take several minutes) |
| `lidar-stream`     | Long-running: runs both GStreamer pipelines and publishes fused-ready detections over MQTT                                                                             |

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
zipFile=@sample_data/lidar_intersection/LidarIntersection-scene-import.zip`
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

| Variable                | Default               | Description                                                                |
| ----------------------- | --------------------- | -------------------------------------------------------------------------- |
| `LIDAR_SENSOR_ID`       | `intersection-lidar1` | Sensor id used for the MQTT topic and payload                              |
| `LIDAR_DEVICE`          | `GPU`                 | OpenVINO device for PointPillars inference (`CPU` fallback is much slower) |
| `LIDAR_SCORE_THRESHOLD` | `0.70`                | Minimum detection confidence to publish                                    |
| `LIDAR_FRAME_RATE`      | `10`                  | Target playback frame rate                                                 |
| `LIDAR_LOOP`            | `true`                | Loop the recorded frame sequence                                           |
| `CAM_SENSOR_ID`         | `intersection-cam1`   | Sensor id used for the MQTT topic and payload                              |
| `CAM_DEVICE`            | `CPU`                 | OpenVINO device for the camera detector                                    |
| `CAM_SCORE_THRESHOLD`   | `0.8`                 | Minimum detection confidence to publish                                    |
| `CAM_DETECTION_LABELS`  | `vehicle,cyclist`     | Comma-separated category allow-list                                        |

## Demo-only patches

Four small patches - one per affected component - are kept out of the normal
source tree and applied on top of it only for this demo:

`sample_data/lidar_intersection/patches/0001-lidar-fusion-manager.patch` (Manager):

| Change                                                                                      | File(s)                                                                                                                                                                          |
| ------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Seed default `vehicle`/`cyclist` objects (size, tracking radius, mark color, `rotation_from_velocity=true`) | `manager/src/manager/management/commands/init_default_assets.py` (new), `manager/src/manager/migrations/0003_default_asset3d_objects.py` (new), `manager/config/scenescape-init` |
| Debug UI: label/style marks by detection source (lidar vs camera), add cyclist mark styling | `manager/src/manager/static/js/marks.js`, `manager/src/manager/static/js/assetmanager.js`, `manager/src/manager/static/css/style.css`                                            |

`sample_data/lidar_intersection/patches/0002-controller-lidar-fusion.patch` (Controller):

| Change                                                                                                                                                                                                          | File(s)                                     |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| Carry the publisher's `source` field (`"lidar"`/`"camera"`) through tracking/fusion so the debug UI labels from patch `0001` have real data                                                                      | `controller/src/controller/moving_object.py` |
| LiDAR heading-disambiguation fix: PointPillars (like other oriented-bbox 3-D detectors) can flip a reported heading ~180 degrees front-to-back; `_disambiguateRotationWithVelocity()` corrects it using the track's own (unambiguous) velocity direction - see [Rotation/orientation handling](#rotationorientation-handling) | `controller/src/controller/moving_object.py` |

`sample_data/lidar_intersection/patches/0003-scene-common-source-passthrough.patch` (scene_common):

| Change                                                                                          | File(s)                                                                                                                          |
| ------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| Forward the same `source` field through the shared detections-builder/ingestion helpers so it reaches the regulated/UI-facing output | `scene_common/src/scene_common/detections_builder.py`, `scene_common/src/scene_common/ingestion.py`                              |

`sample_data/lidar_intersection/patches/0004-analytics-source-passthrough.patch` (Analytics):

| Change                                                                                                                                                             | File(s)                                          |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| Forward the same `source` field through the Analytics service's own tracked-object representation - the Analytics split re-derives objects through an allowlisted dataclass, so it needs the field added independently of the Controller | `analytics/src/analytics/analytics_models.py`     |

Other than the `source` field pass-through and the LiDAR heading-disambiguation
fix above, fusion/tracking logic itself is unmodified by these patches.

`make build-core`/`make build-all` apply all four patches to the working tree
automatically (and only) when `LIDAR_DEMO=true`, build the `manager`,
`controller`, `analytics`, and shared `scene_common` base images with them
applied, then automatically revert them - the patches only need to be on
disk while those images are being built (they're baked into the image
layers), so:

```bash
SUPASS=<password> make build-core demo LIDAR_DEMO=true
```

builds the patched images, reverts the source tree back to normal, and
starts the demo, all in one step. Your working tree stays clean throughout -
`git status` should never show `controller/`/`manager/`/`scene_common/`/
`analytics/` files as modified because of this demo, so there's nothing
extra to commit/push for it beyond this demo's own files under
`sample_data/lidar_intersection/`, `Makefile`, and docs. The apply/revert
cycle is idempotent - re-running the same command does not re-apply, fail,
or leave anything applied. To manually apply or remove the patches (e.g. to
inspect a diff without building):

```bash
make apply-lidar-patch    # apply all four patches to the working tree
make revert-lidar-patch   # revert them back to the unpatched source
```

> **Note:** if a build is interrupted between `apply-lidar-patch` and the
> automatic revert (e.g. `Ctrl+C` mid-build), `controller/`/`manager/`/
> `scene_common/`/`analytics/` files may be left patched in your working
> tree. Run `make revert-lidar-patch` to clean up, or check `git status`
> before committing/pushing.

## Rotation/orientation handling

LiDAR gives real 3-D orientation (`rotation` on each detection), but PointPillars
(like other oriented-bbox 3-D detectors) can occasionally mistake an object's
front for its back, flipping its reported heading ~180 degrees even while it
keeps moving in the same direction. Patch `0002` (above) adds a
`_disambiguateRotationWithVelocity()` method to
`controller/src/controller/moving_object.py` for this: once a track's speed is
clearly above noise level, it flips a LiDAR-reported heading 180 degrees about
Z whenever that heading points against the track's own (unambiguous) velocity
direction. It's a no-op for every other existing demo, since it only runs when
both `has_detection_rotation` (i.e. the detection carried a `rotation`, as
LiDAR's does) and the object's class has `rotation_from_velocity: true` - the
same flag that already gates the existing camera-only hysteresis-based heading
inference (`inferRotationFromVelocity()`/`SPEED_THRESHOLD_ON`/`SPEED_THRESHOLD_OFF`).

The `vehicle`/`cyclist` default assets seeded by patch `0001` (above) set
`rotation_from_velocity=true` so both fixes are active out of the box for this
demo. If you reset the objects library or add these classes another way,
re-enable it per class from the Manager UI's asset config (or
`manager_asset3d.rotation_from_velocity` directly) to keep this behavior.

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
- **A vehicle/cyclist's heading flips ~180 degrees while moving in a
  straight line:** confirm `rotation_from_velocity` is still `true` for that
  class in the Manager's asset config (Django `manager_asset3d` table) - the
  fix in [Rotation/orientation handling](#rotationorientation-handling) above
  is a no-op otherwise.
- **`intersection-cam1` shows "offline"/no picture in the UI:** the Manager
  UI only marks a camera online once it gets a reply to its "getimage"
  request; `lidar_publisher.py` answers this for `intersection-cam1` using
  the current camera frame. If it still shows offline, check `docker compose
logs lidar-stream` for encode errors, and confirm `lidar-data-init`
  completed (the preview needs the same extracted `.jpg` frames as
  detection). `intersection-lidar1` has no camera picture and will always
  show offline/no-preview - that's expected for a LiDAR sensor.
