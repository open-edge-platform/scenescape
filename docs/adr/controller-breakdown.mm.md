---
title: Controller break-down
markmap:
  colorFreezeLevel: 2
---

## Functionalities

### MOT Tracking

- **Role**: perform 2D->3D projection and n3D Multi-Object-Tracking
- **Input**: `data/camera` topics
- **Output**: `data/scene` topics
  - passed-through:
    - detection metadata
      - cross-camera fusion: TBD
      - cross-frame carry-over: TBD
    - camera timestamp
  - produced:
    - [open] camera visibility (e.g. last only, all in the last second)
    - object location projection to 3D scene
    - reliable tracks
    - [open] unreliable and suspended (properly tagged)
- configuration:
  - tracker config
  - scenes and cameras
- not aware of:
  - scene hierarchy
  - sensors, regions, tripwires
- latency-critical, highly optimized
- scalability
    - vertical
      - thread per (scene, category)
      - OpenMP in tracking algorithm
    - horizontal (sharding):
      - exclusive subset of scenes
      - dynamically allocated (mechanism ditributed vs centralized - TBD)

### Scene Analytics

- **Role**: Sensor Attributes, Permanance, ROI, tripwires, Camera Visibility, Projecting Sub-detections
- **Input**: `data/scene` topics
- **Output**:
  - `regulated/scene` topics
    - produced:
  - `events/+` topics
    - produced

### UUID manager + ReID

- **Role**: Assign a global unique ID to objects with re-identification

### Scene Hierarchy

- **Role**:

### Clustering

- **Role**: Clustering analytics
- to be merged