---
title: Controller break-down
markmap:
  colorFreezeLevel: 2
---

## Functionalities

### MOT Tracking

- **Role**: perform near-real time 3D Multi-Object-Tracking
- input: data/camera topics
- output: data/scene topics
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
- not aware of scene hierarchy
- latency-critical, highly optimized
- horizontal scalability (sharding):
    - exclusive subset of scenes
    - dynamically allocated - mechanism TBD

### Scene Analytics (ROI, tripwires)

-

### UUID manager + ReID

- **Role**: Assign a global unique ID to objects with re-identification

### Scene Hierarchy

### Clustering
