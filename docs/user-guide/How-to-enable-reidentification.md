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

## Steps to Enable Re-identification

1. **Enable the ReID Database Container**\
   Uncomment the `vdms` container in `docker-compose.yml`:

   ```yaml
   vdms:
     image: intellabs/vdms:latest
     init: true
     networks:
       scenescape:
     restart: always
   ```

2. **Add Database Dependency to Scene Controller**\
   Add `vdms` to the `depends_on` list for the `scene` container:

   <!-- prettier-ignore -->
   ```yaml
   scene:
     image: scenescape
     ...
     depends_on:
       - broker
       - web
       - ntpserv
       - vdms
   ```

3. **Enable ReID in Percebro's Camera Chain**\
   Add the `reid` model to the `--camerachain` for the appropriate scene:

   <!-- prettier-ignore -->
   ```yaml
   command:
     - "percebro"
     ...
     - "--camerachain=retail+reid"
   ```

4. **Start the System**\
   Launch the updated stack:

   ```bash
   docker compose up --build
   ```

   **Expected Result**: Intel® SceneScape starts with ReID enabled and begins assigning UUIDs based on visual similarity.

---

## Steps to Disable Re-identification

1. **Comment Out the Database Container**\
   Disable `vdms` by commenting it out in `docker-compose.yml`:

   <!-- prettier-ignore -->
   ```yaml
   # vdms:
   #   image: intellabs/vdms:latest
   #   ...
   ```

2. **Remove the Dependency from Scene Controller**\
   Comment or delete the `vdms` dependency:

   ```yaml
   depends_on:
     - broker
     - web
     - ntpserv
     # - vdms
   ```

3. **Remove ReID from the Camera Chain**\
   Update the Percebro chain to exclude `reid`:

   ```yaml
   - "--camerachain=retail"
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
