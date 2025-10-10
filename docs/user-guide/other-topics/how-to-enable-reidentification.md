# How to Enable Re-identification Using Visual Similarity Search

This guide provides step-by-step instructions to enable or disable re-identification (ReID) using visual similarity search in a Intel® SceneScape deployment. By completing this guide, you will:

- Enable re-identification using a visual database and feature-matching model.
- Understand how to track and evaluate unique object identities across frames.
- Learn how to tune performance for specific use cases.

This task is important for enabling persistent object tracking across different camera scenes or time intervals.

---

## Prerequisites

Before you begin, ensure the following:

- **Docker** is installed and configured.
- You have access to modify the `docker-compose.yml` file in your deployment.
- You are familiar with scene and camera configuration in Intel® SceneScape.

---

## Steps to Enable Reidentification (ReID) for Out of Box Experience

1. **Enable VDMS storage by uncomment the following section in [docker-compose-dl-streamer-example.yml](/sample_data/docker-compose-dl-streamer-example.yml)**

```yaml
vdms:
  image: intellabs/vdms:latest
  init: true
  networks:
    scenescape:
      aliases:
        - vdms.scenescape.intel.com
  environment:
    - OVERRIDE_ca_file=/run/secrets/certs/scenescape-ca.pem
    - OVERRIDE_cert_file=/run/secrets/certs/scenescape-vdms-s.crt
    - OVERRIDE_key_file=/run/secrets/certs/scenescape-vdms-s.key
  secrets:
    - source: root-cert
      target: certs/scenescape-ca.pem
    - source: vdms-server-cert
      target: certs/scenescape-vdms-s.crt
    - source: vdms-server-key
      target: certs/scenescape-vdms-s.key
  restart: always
```

For information on VDMS, visit the official documentation: https://intellabs.github.io/vdms/.

SceneScape leverages VDMS to store object vector embeddings for the purpose of reidentifying an object using visual features.

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
"pipeline": "multifilesrc loop=TRUE location=/home/pipeline-server/videos/apriltag-cam2.ts name=source ! decodebin ! videoconvert ! video/x-raw,format=BGR ! gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync ! gvadetect model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model-proc=/home/pipeline-server/models/object_detection/person/person-detection-retail-0013.json name=detection ! gvainference model=/home/pipeline-server/models/intel/person-reidentification-retail-0277/FP32/person-reidentification-retail-0277.xml inference-region=roi-list ! gvametaconvert add-tensor-data=true name=metaconvert ! gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher ! gvametapublish name=destination ! appsink sync=true",
```

4. **Start the System**
   Launch the updated stack:

   ```bash
   docker compose up
   ```

**Expected Result**: Intel® SceneScape starts with ReID enabled and begins assigning UUIDs based on visual similarity.

---

## Steps to Disable Re-identification

1. **Comment Out the Database Container**
   Disable `vdms` by commenting it out in `docker-compose.yml`:

   <!-- prettier-ignore -->
   ```yaml
   # vdms:
   #   image: intellabs/vdms:latest
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

4. **Restart the System**:

   ```bash
   docker compose up --build
   ```

**Expected Result**: Intel® SceneScape runs without ReID and no visual feature matching is performed.

---

## Evaluating Re-identification Performance

- **Track Unique IDs**:\
  Intel® SceneScape publishes `unique_detection_count` via MQTT under the scene category topic. Each object includes an `id` field (UUID) for tracking.

- **UI Support**:\
  UUID display in the 3D UI is planned for future releases.

> **Note**: The default ReID model is tuned for the 'person' category and may not generalize well to other object types.

---

## How Re-identification Works

When an object is first detected, it is assigned a UUID and no similarity score. If ReID is enabled, the system collects visual features over time. Once enough features are gathered, they are compared to those in the database:

- **Match Found**: The object is reassigned a matching UUID and given a similarity score.
- **No Match**: The object retains its original UUID.

> **Known Issue**: Current VDMS implementation does not support feature expiration, leading to degraded performance over time. This will be addressed in a future release.

---

## Configuration Options

| Parameter                        | Purpose                                                                           | Expected Value/Range        |
| -------------------------------- | --------------------------------------------------------------------------------- | --------------------------- |
| `DEFAULT_SIMILARITY_THRESHOLD`   | Controls match sensitivity. Higher values increase matches (and false positives). | Float (e.g., 0.7–0.95)      |
| `DEFAULT_MINIMUM_BBOX_AREA`      | Minimum bounding box size to consider a valid feature.                            | Pixel area (e.g., 400–1600) |
| `DEFAULT_MINIMUM_FEATURE_COUNT`  | Minimum features needed before querying DB.                                       | Integer (e.g., 5–20)        |
| `DEFAULT_MAX_FEATURE_SLICE_SIZE` | Proportion of features stored to improve DB performance.                          | Float (e.g., 0.1–1.0)       |

To apply changes:

```bash
docker compose down
make -C docker
docker compose up --build
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
