<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Plan: Hierarchy External Publish vs Camera Hot-Path Jitter

## Background

`publishSceneDetections` emits full-rate `DATA_SCENE`. On the same camera
callback it also calls `publishExternalDetections`, which rebuilds detections
with sensors / ReID provenance and publishes `DATA_EXTERNAL` for hierarchy.

[ADR 16](../../docs/adr/0016-unified-external-source-ingestion.md) already
requires that root scenes must not emit hierarchy echoes. #1788 removed the
early return for scenes with no parent so **remote children** (roots on their
own broker) could export to a parent `ChildSceneController`. That made every
standalone root pay hierarchy cost every frame and regressed black-box
controller-immediate jitter:

| Condition | `rms_jerk_ratio` | `acceleration_variance_ratio` |
|-----------|------------------|-------------------------------|
| Root skip (ADR 16 / pre-#1788) | ~0.7 | ~0.6 |
| Always publish (#1788) | ~4.4 | ~17–20 |
| Metric thresholds | ≤ 3.0 | ≤ 6.0 |

## Interim (done)

Restore the early return in `publishExternalDetections` when `scene.parent` is
unset. Standalone / black-box roots recover; local children still publish.
Remote children with `parent=None` on the child broker are again blocked from
exporting until the follow-up below.

## Attempts that did not land

Same Unity controller-immediate harness:

1. **Background `ThreadPoolExecutor`** — offload rebuild + MQTT after lean
   `DATA_SCENE`. Jitter passed (~2.0 / ~4.8), but under CPython 3.12 the GIL
   makes this a band-aid (starvation / shared live-track races if free-threaded
   without a snapshot).

2. **Pay-once rich-first** — one rich build, derive lean scene. Failed (~4.4 /
   ~17.6): at 10 fps vs 30 Hz external, rich work always runs before
   `DATA_SCENE`.

3. **Pay-once lean-first + augment** — lean scene first, then enrich for
   external. Failed (~4.7 / ~20.3): enrich + JSON + MQTT still block the camera
   callback.

**Lesson:** Cutting duplicate serialization is not enough while hierarchy work
shares the camera callback on 3.12.

## Ultimate fix

1. Keep lean `DATA_SCENE` on the MQTT/camera thread.
2. Hand off a **snapshot** (or immutable hierarchy payload) to a worker for
   `DATA_EXTERNAL`.
3. Target **free-threaded CPython 3.14** so hierarchy CPU can run truly in
   parallel with the next camera frames (not just overlap I/O under the GIL).

Ship remote-child export restore (parent signal or explicit hierarchy flag)
**only with** that non-blocking path so child metrics do not regress again.

## References

- ADR 16 root-echo rule; #1788 / `278a9866`
- `controller/src/controller/scene_controller.py` —
  `publishSceneDetections` / `publishExternalDetections`
- `tests/system/metric/test_black_box_evaluation.py` —
  `black_box_controller_immediate` jitter thresholds
