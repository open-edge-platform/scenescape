<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Plan: Hierarchy External Publish vs Camera Hot-Path Jitter

## Background

`publishSceneDetections` emits full-rate `DATA_SCENE`. On the same camera
callback it also calls `publishExternalDetections`, which rebuilds detections
with sensors / ReID provenance and publishes `DATA_EXTERNAL` for hierarchy.

[ADR 16](../../docs/adr/0016-unified-external-source-ingestion.md) requires that
standalone root scenes must not emit hierarchy echoes. Always publishing for
every root (including black-box / Unity) regresses controller-immediate jitter.

## Interim (done)

Gate `publishExternalDetections` on `scene.parent` **or** controller
`--publish-external` / `CONTROLLER_PUBLISH_EXTERNAL`. Standalone / black-box
roots stay off by default; local children publish via `scene.parent`; remote
children opt in by enabling the flag on the child Scene Controller.

Non-blocking hot-path publish (below) remains deferred — hierarchy work still
shares the camera callback when export is enabled.

## Ultimate fix

1. Keep lean `DATA_SCENE` on the MQTT/camera thread.
2. Hand off a **snapshot** (or immutable hierarchy payload) to a worker for
   `DATA_EXTERNAL`.
3. Target **free-threaded CPython 3.14** so hierarchy CPU can run truly in
   parallel with the next camera frames (not just overlap I/O under the GIL).

## References

- ADR 16 root-echo rule + remote-child `--publish-external` /
  `CONTROLLER_PUBLISH_EXTERNAL`
- `controller/src/controller/scene_controller.py` —
  `publishSceneDetections` / `publishExternalDetections`
- `controller/src/controller-cmd` CLI / env wiring
- `tests/system/metric/test_black_box_evaluation.py` —
  `black_box_controller_immediate` jitter thresholds
