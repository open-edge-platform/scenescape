# How to Enable Re-identification Using Visual Similarity Search

This guide provides step-by-step instructions to enable or disable re-identification (ReID) using visual similarity search in a Scenescape deployment. By completing this guide, you will:

- Enable re-identification using a visual database and feature-matching model.
- Understand how to track and evaluate unique object identities across frames.
- Learn how to tune performance for specific use cases.

This task is important for enabling persistent object tracking across different camera scenes or time intervals.

---

## Prerequisites for Re-identification

Before you begin, ensure the following:

- **Docker** is installed and configured.
- You have access to modify the `docker-compose.yml` file in your deployment.
- You are familiar with scene and camera configuration in Scenescape.

---

## Steps to Enable Reidentification (ReID) for Out of Box Experience

1. **Select one ReID database**

   Use one backend override with the base Compose file. Both overrides create
   the same logical `reid` service and configure the Scene Controller. Run
   these commands from the `sample_data/` directory:

   ```bash
   # VDMS
   docker compose -f docker-compose-dl-streamer-example.yml \
     -f docker-compose.vdms-override.yml \
     --profile controller up

   # Or Qdrant
   docker compose -f docker-compose-dl-streamer-example.yml \
     -f docker-compose.qdrant-override.yml \
     --profile controller up
   ```

   Use exactly one override. Do not combine them. No backend-specific Compose
   profile or manual service/dependency editing is required.

   From the repository root, `make demo-reid` starts the core demo plus the
   ReID database, defaulting to VDMS. Switch backends with `REID_BACKEND`:

   ```bash
   make demo-reid
   make demo-reid REID_BACKEND=qdrant
   ```

   Plain `make demo` runs tracking without ReID. `make demo-close` uses the
   backend override recorded when the demo was started.

2. **Enable Visual Feature Extraction in Video Pipeline**
   Edit the retail-config setting in [Docker Compose](/sample_data/docker-compose-dl-streamer-example.yml) as follows:

```yaml
retail-config:
  file: ./dlstreamer-pipeline-server/retail-config-reid.json
```

This reidentification-specific configuration uses a vision pipeline that includes anonymous visual feature extraction (also called "visual embeddings") using a person reidentification model:

```
"pipeline": "multifilesrc loop=TRUE location=/home/pipeline-server/videos/apriltag-cam2.ts name=source ! decodebin ! videoconvert ! video/x-raw,format=BGR ! sscape_timestamp_capture name=timesync ntp-server=ntpserv use-frame-ntp-timestamp=false ! gvadetect model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model-proc=/home/pipeline-server/models/object_detection/person/person-detection-retail-0013.json name=detection ! gvainference model=/home/pipeline-server/models/intel/person-reidentification-retail-0277/FP32/person-reidentification-retail-0277.xml inference-region=roi-list ! gvametaconvert add-tensor-data=true name=metaconvert ! sscape_post_inference_data_publish name=datapublisher ! gvametapublish name=destination ! appsink sync=true",
```

**Expected Result**: Scenescape starts with ReID enabled and begins assigning UUIDs based on visual similarity.

---

## Selecting the ReID Vector Database Backend

VDMS and Qdrant are mutually exclusive alternatives. They use the same service
name (`reid`), hostname (`reid.scenescape.intel.com`), port (`55555`), TLS
material, and controller connection settings. The selected override sets
`REID_DATABASE` and starts the matching database implementation.

### Prerequisites

- ReID is already enabled (feature extraction pipeline and `reid-config.json` as in the steps above).
- Secrets include shared ReID certificates (`scenescape-reid*` / `scenescape-reid-s*`). Regenerate with `make clean-secrets && make init-secrets` if those files are missing.
- You can pass an override file when starting services.

### Steps

1. **Stop the stack** using the same base and backend override files used to start it:

   ```bash
   docker compose -f docker-compose-dl-streamer-example.yml \
     -f docker-compose.vdms-override.yml \
     --profile controller down
   ```

2. **Start with the other backend override**. For example, to select Qdrant:

   ```bash
   docker compose -f docker-compose-dl-streamer-example.yml \
     -f docker-compose.qdrant-override.yml \
     --profile controller up
   ```

   The override ([docker-compose.qdrant-override.yml](/sample_data/docker-compose.qdrant-override.yml)):

   - Starts the logical `reid` service using Qdrant, with TLS on shared host `reid.scenescape.intel.com` and port `55555`
   - Sets `REID_DATABASE=QDRANT` on the `scene` service
   - Connection defaults (hostname, port, TLS=`true`, cert paths) are shared via `REID_*` settings

3. **Do not combine the backend override files.** A deployment has one logical
   `reid` service and one selected adapter.

### Shared ReID environment variables

Only `REID_DATABASE` selects the backend. Connection and tuning use shared `REID_*` names (adapters ignore knobs they do not need). Hostname, port, TLS, and certificate paths are the same for every backend.

| Variable                                                | Purpose                               | Default                                                                              |
| ------------------------------------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------ |
| `REID_DATABASE`                                         | Backend selector (`VDMS` or `QDRANT`) | `VDMS`                                                                               |
| `REID_HOSTNAME`                                         | Database host                         | `reid.scenescape.intel.com`                                                          |
| `REID_PORT`                                             | Database port (1–65535)               | `55555`                                                                              |
| `REID_USE_TLS`                                          | Use TLS (`true`/`false`)              | `true`                                                                               |
| `REID_API_KEY`                                          | Optional API key                      | unset (Qdrant)                                                                       |
| `REID_CONFIDENCE_THRESHOLD`                             | TIER 1 metadata confidence threshold  | `0.8`                                                                                |
| `REID_CA_CERT` / `REID_CLIENT_CERT` / `REID_CLIENT_KEY` | TLS / mTLS material                   | `/run/secrets/certs/scenescape-ca.pem`, `scenescape-reid.crt`, `scenescape-reid.key` |

Backend-prefixed names such as `VDMS_HOSTNAME` or `QDRANT_PORT` are no longer read. Set the `REID_*` equivalent instead.

Values are validated at controller startup. A port outside 1–65535, a confidence threshold outside 0.0–1.0, or an unrecognized boolean stops the controller with a message naming the variable and its value, so a typo cannot silently disable TLS or widen a threshold.

### Switching back to VDMS

1. Stop the Qdrant-backed stack.
2. Replace the Qdrant override with the VDMS override:

   ```bash
   docker compose -f docker-compose-dl-streamer-example.yml \
     -f docker-compose.vdms-override.yml \
     --profile controller up
   ```

> **Note:** Vector data is not migrated between VDMS and Qdrant. After a backend switch, identities are matched only against embeddings stored in the newly selected database.

### Kubernetes (Helm)

The Helm chart mirrors the Compose model: a single logical `reid` Service backed
by exactly one database Deployment, sharing the `reid.scenescape.intel.com`
certificates and port `55555`. Select the backend with `reid.backend`:

```bash
helm upgrade scenescape-release-1 --install kubernetes/scenescape-chart/ \
  -n scenescape --create-namespace \
  --set reid.enabled=true --set reid.backend=qdrant
```

The chart sets `REID_DATABASE` on the Scene Controller from `reid.backend`, so
no other value needs to change. Setting `reid.enabled=false` removes the
database Deployment, Service, and ReID certificates, and drops the ReID client
certificates from the Scene Controller.

From the repository root, `make demo-k8s` follows the same tiers as the Compose
demo:

```bash
make demo-k8s                                        # core services, no ReID
make demo-k8s DEMO_K8S_MODE=reid                     # core plus ReID (VDMS)
make demo-k8s DEMO_K8S_MODE=reid REID_BACKEND=qdrant # core plus ReID (Qdrant)
make demo-k8s DEMO_K8S_MODE=all                      # ReID plus mapping and cluster analytics
```

**Expected Result**: The Scene Controller connects to Qdrant, creates or verifies the ReID collection, and continues UUID assignment via visual similarity.

#### Service-link environment variables

The ReID Service is named `reid`, so Kubernetes injects `REID_PORT=tcp://<clusterIP>:<port>`
into every pod in the namespace, which collides with the `REID_PORT` setting
described above. The chart sets `enableServiceLinks: false` on the Scene
Controller to suppress this; all of its dependencies are addressed by DNS.

If you write your own manifests, either do the same or set `REID_PORT`
explicitly, since values in `env` take precedence over service links. As a
backstop, the controller ignores any `REID_*` value that looks like a service
link (`tcp://…`) and logs a warning rather than failing to start.

#### ReID pod filesystem

The ReID container runs with `readOnlyRootFilesystem: true`. Each backend gets
`emptyDir` volumes for the only paths it writes:

| Backend | Writable mounts                        | Notes                                                                  |
| ------- | -------------------------------------- | ---------------------------------------------------------------------- |
| VDMS    | `/vdms/data`, `/tmp`                   | `OVERRIDE_db_root_path` moves the database off the image layer         |
| Qdrant  | `/qdrant/storage`, `/qdrant/snapshots` | `QDRANT_INIT_FILE_PATH` moves the init indicator into writable storage |

Because the VDMS image writes its generated config next to the server binary,
the chart renders that config into `/vdms/data` and starts the server with
`-cfg`. If you pin a different VDMS image, confirm it still provides
`override_default_config.py` and the `-cfg` flag.

ReID vector data is stored in `emptyDir` and is lost when the pod restarts,
which matches the behaviour before the volumes existed. Replace `reid-data`
with a PersistentVolumeClaim if the embeddings must survive restarts.

The pod still runs as root (`runAsUser: 0`) because both upstream images expect
it; that is a separate hardening step.

---

## Steps to Disable Re-identification

1. **Stop using the backend override**

   Stop the stack with its active override, then restart the base Compose file
   without either ReID backend override. The base file does not contain a ReID
   database service.

   ```bash
   docker compose -f docker-compose-dl-streamer-example.yml \
     -f docker-compose.vdms-override.yml \
     --profile controller down
   ```

   Substitute `docker-compose.qdrant-override.yml` when Qdrant is active.

2. **Remove ReID from the Camera Pipeline**
   Edit the retail-config setting in [Docker Compose](/sample_data/docker-compose-dl-streamer-example.yml) and revert to the config without re-id model:

```yaml
retail-config:
  file: ./dlstreamer-pipeline-server/retail-config.json
```

3. **Restart the System**:

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

In a scene hierarchy, a parent scene can match identities using embeddings its children forward. Query first: if the crop is already enrolled, rematch only; if not (for example parent-only ReID), the parent may enroll under its UUID. When a ReID-enabled child stamps `will_enroll` / `enrolled` on hierarchy provenance, the parent still queries but does not write a second UUID for that crop. See [Embeddings in a Scene Hierarchy](../microservices/controller/Extended-ReID.md#embeddings-in-a-scene-hierarchy) and [write authority](../how-to-guides/build-a-scene/deploy-multi-controller-on-one-host.md#write-authority-on-the-hierarchy-wire-will_enroll--enrolled).

For multi-controller setups: **unrelated** scenes may **share** one ReID backend
or use **separate** instances. In a **hierarchy**, do not split backends across
children when you expect one identity space. **Parent-only ReID** with children
forwarding embeddings (no local child ReID) is supported—parent enrolls on
query-no-match; see
[ReID across controllers](../how-to-guides/build-a-scene/deploy-multi-controller-on-one-host.md#reid-across-controllers-what-is-supported).

> **Known Issue**: Current VDMS implementation does not support feature expiration, leading to degraded performance over time. This will be addressed in a future release.

---

## Configuration Options

| Parameter                                                                 | Purpose                                                                                                                                              | Expected Value/Range                                                                                                                                    |
| ------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DEFAULT_SIMILARITY_THRESHOLD_L2` / `DEFAULT_SIMILARITY_THRESHOLD_COSINE` | Match-acceptance threshold defaults selected by `similarity_metric`: the default `COSINE` metric uses `0.5`; explicitly configured `L2` uses `40.0`. | Float; tune per metric. For `COSINE`/`IP`, values such as `0.2–0.8` may be used. For `L2`, use a distance threshold appropriate to the embedding/model. |
| `DEFAULT_MINIMUM_BBOX_AREA`                                               | Minimum bounding box size to consider a valid feature.                                                                                               | Pixel area (e.g., 400–1600)                                                                                                                             |
| `DEFAULT_MINIMUM_FEATURE_COUNT`                                           | Minimum features needed before querying DB.                                                                                                          | Integer (e.g., 5–20)                                                                                                                                    |
| `DEFAULT_MAX_FEATURE_SLICE_SIZE`                                          | Proportion of features stored to improve DB performance.                                                                                             | Float (e.g., 0.1–1.0)                                                                                                                                   |

To apply changes, use the same backend override you selected when starting the stack:

```bash
docker compose -f docker-compose-dl-streamer-example.yml \
  -f docker-compose.vdms-override.yml \
  --profile controller down
make -C docker
docker compose -f docker-compose-dl-streamer-example.yml \
  -f docker-compose.vdms-override.yml \
  --profile controller up --build
```

---

## Troubleshooting

1. **Issue: ReID not working**
   - **Cause**: Database container is not running, not linked, or TLS/certs do not match the shared ReID defaults.
   - **Resolution**:
     ```bash
     docker compose -f docker-compose-dl-streamer-example.yml \
       -f docker-compose.vdms-override.yml \
       --profile controller ps reid
     docker compose -f docker-compose-dl-streamer-example.yml \
       -f docker-compose.vdms-override.yml \
       --profile controller logs reid
     ```
     Substitute the Qdrant override when it is selected. Confirm the `reid`
     service is healthy, the expected `REID_DATABASE` is set on `scene`, and
     the shared `scenescape-reid*` certificates exist.

2. **Issue: Objects not re-identifying across scenes**
   - **Cause**: Insufficient visual features collected or poor lighting.
   - **Resolution**:
     - Lower `DEFAULT_MINIMUM_FEATURE_COUNT`.
     - Increase `DEFAULT_MINIMUM_BBOX_AREA` only if objects are large and visible.

3. **Issue: Backend switch appears to “lose” identities**
   - **Cause**: VDMS and Qdrant do not share stored embeddings.
   - **Resolution**: Expected after switching `REID_DATABASE`. Re-accumulate features in the new backend, or restore the previous backend and its data volume.
