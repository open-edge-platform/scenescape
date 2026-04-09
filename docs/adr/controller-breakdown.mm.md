---
title: Controller break-down
markmap:
  colorFreezeLevel: 2
---

## Data Flow

```
sensors ────────────────────────────────────────────────────────────────────────────────────────────────► data/sensor/{sensor-id}
                                                                                                                   │
                                                                                                                   ▼
cameras ──► data/camera/{camera-id} ──► Projection ──► MOT Tracking ──► data/scene/{scene-id}/{category} ──► Scene Analytics ──► regulated/scene/{scene-id}
                                                                                      │                            │
                                                                                      │                            ├──► events/+
                                                                                      │                            │
                                                                                      ▼                            ▼
                                                                                Scene Hierarchy             UUID Manager + ReID
                                                                                      │                     (sync query-response,
                                                                                      │                      called by Analytics)
                                                                                      ▼
                                                                            external/scene/{parent-scene-id}
                                                                                      │
                                                                                      ▼
                                                                            Scene Analytics (parent scene)
```

**[?] markers** indicate open questions, typically about which component is responsible when the same data could be handled in multiple places (e.g., sensors could be in MOT or Analytics). See [Opens](#opens) section.

## Functionalities

### Projection

- **Role**: perform 2D->3D projection
- **Responsible Component**: not decided yet (currently Tracker Service)
- **Communication Model**: Asynchronous, one-directional (messages)
- **Input**: `data/camera/{camera-id}` topics
- **Output**: currently Tracker Service internal buffer (to be changed to MQTT topic if it becomes a separate service, e.g. `data/projections/{scene-id}/{category}` topics)
- configuration:
  - scenes and cameras
- not aware of:
  - regions, tripwires
- technology: C++
- latency-critical, highly optimized
- scalability TBD

### MOT Tracking

- **Role**: 3D Multi-Object-Tracking
- **Responsible Component**: Tracker Service
- **Communication Model**: Asynchronous, one-directional (messages)
- **Input**:
  - currently Tracker Service internal buffer (to be changed to MQTT topic if it becomes a separate service, e.g. `data/projections/{scene-id}/{category}` topics)
- **Output**: `data/scene/{scene-id}/{category}` topics
  - passed-through:
    - detection metadata
      - cross-camera fusion: TBD
      - cross-frame carry-over (retaining attributes across frames for the same tracked object): TBD
    - camera timestamp (with optional correction)
  - produced:
    - object location projection to 3D scene
    - reliable tracks with local ID (unique per scene)
    - ~~visibility by camera matches [?] (see [Opens](#opens): whether sensor inputs are handled in tracker or analytics)~~
- configuration:
  - tracker config
- not aware of:
  - scene hierarchy (unless we decide to re-track in parent scene, see [Opens](#opens))
  - regions, tripwires
- technology: C++
- latency-critical, highly optimized
- time synchronization: timestamp correction with NTP server (configurable) [?] (see [Opens](#opens): NTP synchronization approach)
- scalability
  - vertical
    - thread per (scene, category)
    - OpenMP in tracking algorithm
  - horizontal (sharding):
    - exclusive subset of scenes
    - dynamically allocated (mechanism distributed vs centralized - TBD)

### Scene Analytics

- **Role**:
  - Generating scene analytics that build on top of 3D tracks from MOT and anything else existing in the scene
  - Including: Sensor Attributes, Events (ROI, Tripwires), Projecting Sub-detections, Camera Visibility
- **Communication Model**: Asynchronous, one-directional (messages)
- **Responsible Component**: Not Decided Yet
- **Input**:
  - `data/scene/{scene-id}/{category}` topics
  - `data/sensor/{sensor-id}` topics
  - `external/scene/{scene-id}` topics
  - **Note:** There are use cases (ex: wipro), in which the tracker is skipped and only analytics are used. And thus analytics should accept data from other sources apart from MOT (It needs to have its own input schema)
- **Output**:
  - `regulated/scene/{scene-id}` topic
    - passed-through:
      - ~~visibility by camera matches [?] (see [Opens](#opens): whether sensor inputs are handled in tracker or analytics)~~
      - semantic metadata from camera detections
    - produced:
      - sensor attributes
      - events (e.g. regions, tripwire)
      - visibility by camera view projection
  - `events/+` topics
    - produced: as today
- hierarchy handling (alternative approaches - one of):
  - receives hierarchy data via `external/` topics from tracker
  - analytics is the publisher to external topic and not tracker
- technology: Python and C++
- time synchronization: None
- latency-sensitive, most compute-expensive functions optimized (C++)
- scalability
  - vertical
    - Process-based parallelism [Python multi-processing library](https://docs.python.org/3/library/multiprocessing.html)
    - process per (scene), because output is aggregated for all categories
  - horizontal (sharding):
    - exclusive subset of scenes
    - dynamically allocated (mechanism distributed vs centralized - TBD)

### UUID manager + ReID

- **Role**:
  - Assign a global unique ID to objects with re-identification across scenes
- **Responsible Component**: Not Decided Yet
- **Communication Model**: Synchronous, two-directional (query-response)
- **Called by**: Scene Analytics (queries UUID Manager during output generation)
  - Publish local UUID when Re-ID is enabled and when enough embeddings to reliably Re-ID are not yet collected.
  - If the collection is done, query and from that point on use the global UUID
  - This approach enables async behavior and prioritizes latency in exchange for slight complexity.
- **Input**: REST API / gRPC requests
  - track local UUID
  - scene, category
  - metadata (attributes, ReID embeddings)
- **Output**: REST API / gRPC requests
  - unique track global UUID

### Scene Hierarchy

- **Role**: Transform reliable tracks upstream across the scene hierarchy
- **Input**: `data/scene/{scene-id}` topics of child scenes
- **Output**: `external/scene/{parent-scene-id}` topics
- **Communication Model**: Asynchronous, one-directional (messages)
- **Responsible Component**: Not Decided Yet
- Configuration
  - child - parent relationship and coordinate system transformations
  - broker instance endpoint
  - additional parameters (update rate etc.)
- technology: Python and C++
- time synchronization: None
- latency-sensitive, most compute-expensive functions optimized (C++)
- scalability:
  - horizontal: one instance per parent scene or one instance per parent-child pair

### Clustering

- **Role**: Spatial clustering of detected objects with tracking, shape detection, and movement analysis
- **Responsible Component**: Not Decided Yet
- **Current implementation** (`cluster_analytics/`):
  - DBSCAN clustering with category-specific density parameters (e.g., person: eps=2, vehicle: eps=4)
  - Multi-frame cluster tracking with 5-state lifecycle (NEW → ACTIVE → STABLE → FADING → LOST) using Hungarian Algorithm matching
  - ML-based shape detection (circle, rectangle, line, irregular) with size/area measurements
  - Velocity analysis: stationary, coordinated_parallel, converging, diverging, loosely_coordinated, chaotic
  - Runtime reconfiguration via WebUI SocketIO
- **Communication Model**: Asynchronous, one-directional (messages)
- **Input**:
  - `regulated/scene/{scene-id}` topics (objects with world coordinates and velocity vectors)
- **Output**:
  - `analytics/clusters/{scene-id}` topics (tracked clusters with UUID, state, confidence, centroid, shape, velocity analysis)

## Opens

- **Projection / Tracker / Analytics / Clustering**:
  - Whether Projection should be a separate service or part of Tracker Service.
  - **DONE** ~~do we need to implement object permanence? if so, how to provide input which tracks should be permanent~~ **NO**
  - **DONE** how to handle non camera detections like 3D sensors (e.g. LIDARs)
    - Expected to align to the metadata that tracker expects for object detections.
    - We will eventually provide Lidar calibration methods to position the sensor so that the detections from the lidar can be correctly positioned in the shared coordinate system.
  - **DONE** ~~whether to produce as output: unreliable and suspended (properly tagged)~~ **NO**
  - **DONE** how to generate camera visibility (two complementary approaches, can be used together)
    - ~~computed based on matched detections (e.g. last frame camera only, cameras in the last second)~~
    - computed from projecting camera field of view (as it is now) in scene analytics
  - **DONE** ~~whether to handle sensor inputs in tracker service or analytics?~~ **in analytics**
  - **DONE** ~~whether to extend cluster analytics with scene analytics or to implement new service~~ **NO, we will create new service**
- **Scene Hierarchy**
  - whether it should be a separate service or part of tracker or/and analytics?
    - if part of tracker / analytics, then should only analytics be aware of hierarchy or both?
  - which of the following should flow from child to parent:
    - camera detections
    - raw tracks (tracker outputs)
    - fused tracks (analytics outputs)
    - analytics events
  - in future how to make regions and tripwires shared across scene hierarchy (increases complexity) **need to check with Rob on the priority of this.**
- **NTP synchronization** (affects MOT Tracking `[?]` on time sync)
  - whether to internally synchronize timestamps with external NTP service vs rely on system-level clock synchronization (and shift the responsibility onto the user)?
    - relying on system clock NTP synchronization simplifies tracker implementation and the pipeline (we can use GStreamer timestamper then which takes time from system clock, gvapython may become deprecated), potentially decreasing pipeline latency
