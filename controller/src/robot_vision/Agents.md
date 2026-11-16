<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# robot_vision — AI Agent Guide

Read this before changing code under `controller/src/robot_vision/`.

Library scope only: algorithms, APIs, bindings, and local tests. Service wiring
(Controller MQTT ingest, Tracker worker, schemas, Compose) belongs in those
services and their `Agents.md` files — do not restate those here.

Also follow repository guidance in [`../../../AGENTS.md`](../../../AGENTS.md)
and Kalman / filter details in [`README.md`](README.md).

---

## What this library is

**robot_vision** is a modality-agnostic multi-object tracking and state-estimation
library. Callers feed metric-frame detections (`TrackedObject`: position, size,
optional yaw, optional per-detection measurement noise `R`) from any sensor or
publisher. The tracker associates, fuses, predicts, and maintains tracks in a
shared world/scene frame.

It is **not** a camera pipeline, detector, or projection stack. Image geometry,
intrinsics/extrinsics, depth models, and sensor-native message formats live
outside this library (or behind an optional, explicitly modality-specific
helper), not in the MOT / UKF core.

---

## Modality policy (critical)

1. **Core tracking stays modality-agnostic.** Prefer names and comments that say
   _source_ (or detection / measurement), not _camera_, unless the code truly
   deals with camera geometry. Batched APIs use `objectsPerSource` /
   `objects_per_source`.

2. **Modality-specific geometry is handled before robot_vision.** Controllers,
   Tracker workers, adapters, and projection libraries convert sensor-native
   observations into `TrackedObject` measurements (world/metric frame, sizes,
   yaw when known, and `R` when the caller has a covariance). Do not pull
   pixel boxes, camera matrices, or sensor FOV assumptions into
   `MultipleObjectTracker`, association, or the Kalman models.

3. **If modality-specific behavior must live in this tree, isolate it.** Put it
   in a clearly named helper, optional strategy, or non-core utility (for
   example `CameraUtils`), not in the shared track lifecycle. Do not let
   camera-only assumptions leak into default association, birth clustering,
   or motion models used by every source.

4. **External and camera detections share the same track API.** A lidar, UWB,
   robot localization, or other external publisher that already emits world-frame
   detections should use the same `track()` / batched `objectsPerSource` path as
   camera-derived detections. Differences belong in how detections are built
   upstream, or in an explicit strategy—not in forked tracker APIs.

---

## Layout (where to look)

```
include/rv/tracking/   — MOT, UKF, motion models, fusion, TrackedObject
include/rv/            — shared utils + isolated modality helpers (CameraUtils)
src/rv/tracking/       — tracking implementations
src/rv/                — non-tracking implementations (CameraUtils, apollo/)
python/…/extensions/   — pybind11 bindings
test/                  — GoogleTest suite (+ support helpers)
benchmarks/            — performance benches
README.md              — build, Kalman settings, scenario recording
```

---

## Agent checklist

When editing this library:

- [ ] Does the change assume a camera, image plane, or other single modality?
      If yes, push that logic upstream or behind an isolated strategy/helper.
- [ ] Are new public names and comments source/measurement-neutral?
- [ ] Do camera and external (or other) sources still share the same track /
      fusion contract?
- [ ] Are filter / association invariants in `README.md` still accurate?

Build and test from this directory (`cmake` + `RobotVisionTests`) or via the
Tracker service’s robot_vision test targets; see `README.md`.
