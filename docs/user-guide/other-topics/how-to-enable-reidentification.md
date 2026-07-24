# How to Enable Re-identification Using Visual Similarity Search

This guide provides step-by-step instructions to enable or disable re-identification (ReID) using visual similarity search in a Scenescape deployment. By completing this guide, you will:

- Enable re-identification using a visual database and feature-matching model.
- Understand how to track and evaluate unique object identities across frames.
- Learn how to tune performance for specific use cases.

This task is important for enabling persistent object tracking across different camera scenes or time intervals.

---

## Prerequisites

Before you begin, ensure the following:

- **Docker** is installed and configured.
- You have access to modify the `docker-compose.yml` file in your deployment.
- You are familiar with scene and camera configuration in Scenescape.

---

## Steps to Enable Reidentification (ReID) for Out of Box Experience

> **Note:** The VDMS service is configured under the `vdms` Docker Compose profile. You must include `--profile vdms` (or set `COMPOSE_PROFILES` accordingly) when starting services. See [Docker Compose Profiles](../get-started.md#docker-compose-profiles) for more information.

1. **Enable VDMS storage by uncomment the following section in [docker-compose-dl-streamer-example.yml](/sample_data/docker-compose-dl-streamer-example.yml)**

```yaml
vdms:
  image: intellabs/vdms:v2.12.0
  init: true
  networks:
    scenescape:
      aliases:
        - vdms.scenescape.intel.com
  restart: always
```

For information on VDMS, visit the official documentation: https://intellabs.github.io/vdms/.

Scenescape leverages VDMS to store object vector embeddings for the purpose of reidentifying an object using visual features.

2. **Uncomment VDMS dependency in scene config**
   Uncomment the `vdms` dependency:

```yaml
depends_on:
  web:
    condition: service_healthy
  broker:
    condition: service_started
  ntpserv:
    condition: service_started
  vdms:
    condition: service_started
```

3. **Enable Visual Feature Extraction in Video Pipeline**
   Edit the retail-config setting in [Docker Compose](/sample_data/docker-compose-dl-streamer-example.yml) as follows:

```yaml
retail-config:
  file: ./dlstreamer-pipeline-server/retail-config-reid.json
```

This reidentification-specific configuration uses a vision pipeline that includes anonymous visual feature extraction (also called "visual embeddings") using a person reidentification model:

```
"pipeline": "multifilesrc loop=TRUE location=/home/pipeline-server/videos/apriltag-cam2.ts name=source ! decodebin ! videoconvert ! video/x-raw,format=BGR ! sscape_timestamp_capture name=timesync ntp-server=ntpserv use-frame-ntp-timestamp=false ! gvadetect model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model-proc=/home/pipeline-server/models/object_detection/person/person-detection-retail-0013.json name=detection ! gvainference model=/home/pipeline-server/models/intel/person-reidentification-retail-0277/FP32/person-reidentification-retail-0277.xml inference-region=roi-list ! gvametaconvert add-tensor-data=true name=metaconvert ! sscape_post_inference_data_publish name=datapublisher ! gvametapublish name=destination ! appsink sync=true",
```

4. **Start the System**
   Launch the updated stack with the `vdms` profile to enable the visual database (see [Docker Compose Profiles](../get-started.md#docker-compose-profiles) for details on available profiles):

   ```bash
   docker compose --profile controller --profile vdms up
   ```

**Expected Result**: Scenescape starts with ReID enabled and begins assigning UUIDs based on visual similarity.

---

## Steps to Disable Re-identification

1. **Comment Out the Database Container**
   Disable `vdms` by commenting it out in `docker-compose.yml`:

   <!-- prettier-ignore -->
   ```yaml
   # vdms:
   #   image: intellabs/vdms:v2.12.0
   #   ...
   ```

2. **Remove the Dependency from Scene Controller**
   Comment or delete the `vdms` dependency:

   ```yaml
   depends_on:
     - broker
     - web
     - ntpserv
     # - vdms
   ```

3. **Remove ReID from the Camera Pipeline**
   Edit the retail-config setting in [Docker Compose](/sample_data/docker-compose-dl-streamer-example.yml) and revert to the config without re-id model:

```yaml
retail-config:
  file: ./dlstreamer-pipeline-server/retail-config.json
```

4. **Restart the System** (the `vdms` profile is no longer needed since ReID is disabled):

   ```bash
   docker compose --profile controller up --build
   ```

**Expected Result**: Scenescape runs without ReID and no visual feature matching is performed.

---

## Evaluating Re-identification Performance

- **Track Unique IDs**:\
  Scenescape publishes `unique_detection_count` via MQTT under the scene category topic. Each object includes an `id` field (UUID) for tracking.

- **UI Support**:\
  UUID display in the 3D UI is planned for future releases.

> **Note**: The default ReID model is tuned for the 'person' category and may not generalize well to other object types.

---

## How Re-identification Works

When an object is first detected, it is assigned a UUID and no similarity score. If ReID is enabled, the system collects visual features over time. Once enough features are gathered, they are compared to those in the database:

- **Match Found**: The object is reassigned a matching UUID and given a similarity score.
- **No Match**: The object retains its original UUID.

The scene output includes `reid_state` for each tracked object. For canonical state definitions and lifecycle transitions, see [2-Tier Hybrid Search Implementation](../microservices/controller/Extended-ReID.md#reid-object-states). For output field contract details, see [Scene Controller Data Formats](../microservices/controller/data_formats.md#common-output-track-fields).

Descriptors written to VDMS now carry a time-to-live (`descriptor_ttl_secs`) so stored feature vectors expire automatically instead of accumulating indefinitely. See **Storage Bounding** below for details.

---

## Storage Bounding

To prevent unbounded growth of the VDMS descriptor store, each descriptor written for ReID matching is tagged with an expiration (VDMS's native `_expiration` property), and VDMS is configured to sweep for expired descriptors on a regular interval.

- **`descriptor_ttl_secs`** (client-side, set on the controller/adapter) — the lifetime, in seconds, assigned to each descriptor when it's written to VDMS. Once a descriptor's age exceeds this value, VDMS marks it eligible for auto-deletion. Defaults to `86400` (24 hours); configurable via the `DEFAULT_DESCRIPTOR_TTL_SECS` environment variable.
- **`OVERRIDE_autodelete_interval_s`** (VDMS server-side, Docker env var) — how often, in seconds, the VDMS server sweeps for and removes expired descriptors. This does not change _when_ a descriptor expires, only how promptly expired descriptors are cleaned up after the fact. Set on the `vdms` container, e.g.:

  ```bash
  docker run -d --net=host -e OVERRIDE_autodelete_interval_s=60 intellabs/vdms:v2.12.0
  ```

> **Note**: Both settings are time-based only. Storage is bounded by descriptor age, not by actual memory/storage usage — under heavy ingest, storage can still grow within the TTL window. Choose `descriptor_ttl_secs` conservatively for your expected peak ingest rate.

---

## Configuration Options

| Parameter                                                                 | Purpose                                                                                                                                                                                          | Expected Value/Range                                                                                                                                    |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DEFAULT_SIMILARITY_THRESHOLD_L2` / `DEFAULT_SIMILARITY_THRESHOLD_COSINE` | Match-acceptance threshold defaults selected by `similarity_metric`: `L2` uses `DEFAULT_SIMILARITY_THRESHOLD_L2`, and `COSINE` (mapped to VDMS `IP`) uses `DEFAULT_SIMILARITY_THRESHOLD_COSINE`. | Float; tune per metric. For `COSINE`/`IP`, values such as `0.2–0.8` may be used. For `L2`, use a distance threshold appropriate to the embedding/model. |
| `DEFAULT_MINIMUM_BBOX_AREA`                                               | Minimum bounding box size to consider a valid feature.                                                                                                                                           | Pixel area (e.g., 400–1600)                                                                                                                             |
| `DEFAULT_MINIMUM_FEATURE_COUNT`                                           | Minimum features needed before querying DB.                                                                                                                                                      | Integer (e.g., 5–20)                                                                                                                                    |
| `DEFAULT_MAX_FEATURE_SLICE_SIZE`                                          | Proportion of features stored to improve DB performance.                                                                                                                                         | Float (e.g., 0.1–1.0)                                                                                                                                   |
| `descriptor_ttl_secs`                                                     | Lifetime, in seconds, assigned to each descriptor written to VDMS before it becomes eligible for auto-deletion. Set via `DEFAULT_DESCRIPTOR_TTL_SECS` env var.                                   | Integer seconds (e.g., `86400` for 24 hours)                                                                                                            |
| `OVERRIDE_autodelete_interval_s`                                          | VDMS server-side Docker env var controlling how often (seconds) the server sweeps for and removes expired descriptors.                                                                           | Integer seconds (e.g., `60`)                                                                                                                            |

To apply changes (include `--profile vdms` if ReID is enabled; see [Docker Compose Profiles](../get-started.md#docker-compose-profiles)):

```bash
docker compose --profile controller --profile vdms down
make -C docker
docker compose --profile controller --profile vdms up --build
```

---

## Troubleshooting

1. **Issue: ReID not working**
   - **Cause**: Database container is not running or not linked.
   - **Resolution**:
     ```bash
     docker ps | grep vdms
     docker compose logs vdms
     ```

2. **Issue: Objects not re-identifying across scenes**
   - **Cause**: Insufficient visual features collected or poor lighting.
   - **Resolution**:
     - Lower `DEFAULT_MINIMUM_FEATURE_COUNT`.
     - Increase `DEFAULT_MINIMUM_BBOX_AREA` only if objects are large and visible.
