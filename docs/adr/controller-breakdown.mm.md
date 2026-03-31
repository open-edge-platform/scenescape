---
title: Controller break-down
markmap:
  colorFreezeLevel: 2
---

## Functionalities

### MOT Tracking

- **Role**: perform 2D->3D projection and 3D Multi-Object-Tracking
- **Input**: `data/camera` topics
- **Output**: `data/scene` topics
  - passed-through:
    - detection metadata
      - cross-camera fusion: TBD
      - cross-frame carry-over: TBD
    - camera timestamp
  - produced:
    - object location projection to 3D scene
    - reliable tracks with local UUID (unique per scene)
    - [?] visibility by camera matches
- configuration:
  - tracker config
  - scenes and cameras
- not aware of:
  - scene hierarchy
  - regions, tripwires, [?] sensors
- technology: C++
- latency-critical, highly optimized
- time synchronization: timestamp correction with NTP server (configurable)
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
- **Input**:
  - `data/scene` topics
  - `data/sensor` topics
- **Output**:
  - `regulated/scene` topic
    - passed-through:
      - [?] visibility by camera matches
      - semantic metadata from camera detections
    - produced:
      - [?] sensor attributes
      - events (e.g. regions, tripwire)
      - visibility by camera view projection
  - `events/+` topics
    - produced: TBD
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

- **Role**: Assign a global unique ID to objects with re-identification
- **Input**: REST API / gRPC requests
  - track local UUID
  - scene, category
  - metadata (attributes, ReID embeddings)
- **Output**: REST API / gRPC requests
  - unique track global UUID

### Scene Hierarchy

- **Role**: Transform reliable tracks upstream across the scene hierarchy

### Clustering

- **Role**: Clustering analytics
- to be merged with Scene Analytics

## Opens

- **Tracker / Analytics**:
  - how to provide feedback loop to dynamically provide input on detected objects:
    - how to implement object permanence? how to provide input which tracks should be permanent
    - in general: how to inject input from other sources (e.g. GPS, badge sensor) augmenting tracking input
  - how to handle non camera detections like 3D sensors (e.g. LIDARs)
  - whether to produce as output: unreliable and suspended (properly tagged)
  - how to generate camera visibility
    - computed from based on matched detections (e.g. last frame camera only, cameras in the last second)
    - computed from projecting camera field of view (as it is now)
  - whether to handle sensor inputs in tracker service or analytics
