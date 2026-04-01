---
title: Controller break-down
markmap:
  colorFreezeLevel: 2
---

## Functionalities

### MOT Tracking

- **Role**: perform 2D->3D projection and 3D Multi-Object-Tracking
- **Responsible Component**: Tracker Service
- **Communication Model**: Asynchronous, one-directional (messages)
- **Input**:
  - `data/camera/{camera-id}` topics
  - `data/sensor/{sensor-id}` topics [?]
- **Output**: `data/scene/{scene-id}/{category}` topics
  - passed-through:
    - detection metadata
      - cross-camera fusion: TBD
      - cross-frame carry-over: TBD
    - camera timestamp (with optional correction)
  - produced:
    - sensors [?]
    - object location projection to 3D scene
    - reliable tracks with local ID (unique per scene)
    - [?] visibility by camera matches
- configuration:
  - tracker config
  - scenes and cameras
- not aware of:
  - scene hierarchy
  - regions, tripwires
- technology: C++
- latency-critical, highly optimized
- time synchronization: timestamp correction with NTP server (configurable) [?]
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
  - `data/sensor/{sensor-id}` topics [?]
  - `external/scene/{scene-id}` topics
- **Output**:
  - `regulated/scene/{scene-id}` topic
    - passed-through:
      - visibility by camera matches [?]
      - semantic metadata from camera detections
    - produced:
      - sensors [?]
      - events (e.g. regions, tripwire)
      - visibility by camera view projection
  - `events/+` topics
    - produced: as today
- not aware of:
  - scene hierarchy (no hierarchy for scene analytics)
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
- Configuration
  - child - parent relationship and coordinate system transformations
  - broker instance endpoint
  - additional parameters (update rate etc.)

### Clustering

- **Role**: Clustering detected objects
- **Responsible Component**: Not Decided Yet
- **Input**:
  - TBD
- **Output**:
  - TBD

## Opens

- **Tracker / Analytics / Clustering**:
  - do we need to implement object permanence? if so, how to provide input which tracks should be permanent
  - how to handle non camera detections like 3D sensors (e.g. LIDARs)
  - whether to produce as output: unreliable and suspended (properly tagged)
  - how to generate camera visibility
    - computed from based on matched detections (e.g. last frame camera only, cameras in the last second)
    - computed from projecting camera field of view (as it is now)
  - whether to handle sensor inputs in tracker service or analytics?
    - if in tracker service then
      - sensor readings go to data/scene topics (as it is now)
      - can be sent to parent (as it is now)
    - if in analytics service then
      - sensor readings go to regulated/scene topics
      - not sent to parent (breaking change)
  - whether to extend cluster analytics with scene analytics or to implement new service
- **Scene Hierarchy**
  - give up re-tracking in parent scene? (only tracks are sent to parent) - would simplify a lot
  - only tracks are sent to parent, not events?
    - in future how to make regions and tripwires shared across scene hierarchy (increases complexity)
  - NTP - whether to internally synchronize timestamps with external NTP service vs rely on system-level clock synchronization (and shift the responsibility onto the user)?
    - relying on system clock NTP synchronization simplifies tracker implementation and the pipeline (we can use GStreamer timestamper then which takes time from system clock, gvapython may become deprecated), potentially decreasing pipeline latency
