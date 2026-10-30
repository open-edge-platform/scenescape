<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# PTZ Pose Consumption in the Tracker

A pan-tilt-zoom (PTZ) camera is a tracking source only while it is parked. The
[Positioning service](../../docs/user-guide/microservices/positioning/positioning.md)
publishes a resolved `PoseContext` for each PTZ camera. The Tracker can use it to project
the camera's detections with the pose the camera had when it acquired them. Both modes on
this page are **off by default**. With both off, the Tracker behaves as before: it adds no
subscriptions, reads no PTZ configuration, and does no per-message PTZ work.

The message formats, admission rules, and reason values are defined in the
[Positioning PTZ v1 contracts](../../docs/design/positioning-ptz-contracts.md). The
Tracker applies the same normative dwell contract as the Scene Controller
([PTZ Pose Consumption in the Scene Controller](../../docs/user-guide/microservices/controller/ptz-pose-consumption.md)).
Both consumers replay the shared vectors in `tests/data/ptz/dwell_conformance.json`
unmodified, so they make the same decision for every vector. This page describes only how
the Tracker applies the contract.

## Modes

| Mode      | `tracker.json`    | Environment variable      | Effect                                                                                                                                                      |
| --------- | ----------------- | ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Enforcing | `ptz.enabled`     | `TRACKER_PTZ_ENABLED`     | Rejected PTZ detection batches never reach tracking. Admitted batches are projected with the PoseContext that admitted them, not with the static home pose. |
| Shadow    | `ptz.shadow_mode` | `TRACKER_PTZ_SHADOW_MODE` | Computes every decision and records it. Detections, projection, and track state are exactly as with PTZ off.                                                |

The two modes are mutually exclusive. The Tracker exits with code 1 at startup, with a
message that names the problem, in any of these cases:

- Both modes are on.
- A required bound is missing, is not finite, or is out of range.
- NTP is not configured (`infrastructure.ntp` or `TRACKER_NTP_SERVER`). The dwell
  contract needs a synchronized clock.
- The assignment manifest is missing or invalid.
- `ptz.shadow.run_id` or `ptz.shadow.sample_every_n` is invalid.

## Configuration

Every bound is deployment-owned and **required**; none has a default. Measure
`max_detection_pipeline_latency_s` for your deployment before enabling either mode. The
values are read only when a mode is on.

| `tracker.json` key                          | Environment variable                                | Unit | Validation                                                  |
| ------------------------------------------- | --------------------------------------------------- | ---- | ----------------------------------------------------------- |
| `ptz.max_pose_age_s`                        | `TRACKER_PTZ_MAX_POSE_AGE_S`                        | s    | finite, > 0                                                 |
| `ptz.max_clock_offset_s`                    | `TRACKER_PTZ_MAX_CLOCK_OFFSET_S`                    | s    | finite, > 0                                                 |
| `ptz.max_detection_pipeline_latency_s`      | `TRACKER_PTZ_MAX_DETECTION_PIPELINE_LATENCY_S`      | s    | finite, > 0                                                 |
| `ptz.max_detection_timestamp_uncertainty_s` | `TRACKER_PTZ_MAX_DETECTION_TIMESTAMP_UNCERTAINTY_S` | s    | finite, >= 0                                                |
| `ptz.assignments_path`                      | `TRACKER_PTZ_ASSIGNMENTS_PATH`                      | —    | default `/scenescape/config/positioning-assignments.json`   |
| `ptz.shadow.run_id`                         | `TRACKER_PTZ_SHADOW_RUN_ID`                         | —    | 1-128 characters of `[A-Za-z0-9._-]`, default `unspecified` |
| `ptz.shadow.sample_every_n`                 | `TRACKER_PTZ_SHADOW_SAMPLE_EVERY_N`                 | —    | integer >= 1, default 10                                    |
| `ptz.shadow.per_decision`                   | `TRACKER_PTZ_SHADOW_PER_DECISION`                   | —    | default `false`                                             |

Environment variables override `tracker.json`. The assignment manifest is the
deployment-owned `deployment/positioning-assignments.json`. It maps each PTZ `source_id` to
the `resolver_id` whose status topic marks the Resolver session. The Tracker reads only
that mapping from it.

```json
{
  "ptz": {
    "enabled": true,
    "max_pose_age_s": 0.5,
    "max_clock_offset_s": 0.05,
    "max_detection_pipeline_latency_s": 1.0,
    "max_detection_timestamp_uncertainty_s": 0.05,
    "assignments_path": "/scenescape/config/positioning-assignments.json"
  }
}
```

## Which cameras are managed

A camera is a PTZ camera when its Manager `ptz_calibration` is not null. Camera-to-scene
membership comes from the scenes the Tracker loads from Manager. The Tracker subscribes only
to these topics:

- `scenescape/positioning/pose/{source_id}` for each PTZ camera of its scenes that has a
  Resolver in the manifest.
- `scenescape/positioning/status/{resolver_id}` for each of those Resolvers.

A PTZ camera without a Resolver assignment is logged once, and its detections are rejected
as `no_sample` (`managed: false`). The Tracker uses `controller.auth` as its deployment
identity. For that identity, Manager's broker ACL allows pose reads only for cameras that
belong to a scene, and denies any pose or status publish
(`tests/functional/test_tracker_ptz_acl.py`).

The Tracker pins the PoseContext frame to `scene:{scene_uid}` of the camera's scene. It
also pins `calibration_version` when Manager provides one. A pose in any other frame,
including an unresolved child-scene frame, fails closed as `frame_mismatch`. Changing a
camera's calibration or scene triggers the existing restart in dynamic mode, so every dwell
starts again from fresh state.

## Enforcing mode

The decision is made once per detection message, on the MQTT callback thread, as soon as
the message arrives. It is never queued and never waits for a pose.

- **Observation time** is the message's acquisition `timestamp`, parsed to microseconds.
  It is never the receive time or the chunk time, and the Tracker has no option that
  rewrites acquisition time.
- **Rejected** batches are buffered as detection-less heartbeats. Existing tracks keep
  predicting and aging, and the rejected detections neither initiate nor update tracks.
  The message is counted in `tracker.mqtt.dropped` with `reason=ptz_dwell`.
- **Admitted** batches carry the admitting PoseContext. The tracking worker projects each
  batch with its own pose, passed to `CoordinateTransformer::transformDetections()` as an
  argument. Intrinsics and distortion stay those of the static camera.

### Multiple batches of one camera in a chunk

Static cameras keep the latest batch per camera and time chunk, as before. A PTZ camera's
batches with distinct acquisition timestamps are all kept, up to 8 per chunk. Each batch
carries its own dwell decision and pose, so a later batch can never apply its decision or
pose to another batch's detections. A rejected heartbeat never displaces a buffered batch
that has detections.

## Shadow mode

Shadow mode never modifies detections, batches, or track state. It records every decision
with the configured recorder:

- **Summary (default):** one log line per camera each time a new parked pose is first
  applied. The line summarizes the decisions since the previous line, including the
  residual median, p95, and max between the candidate (PoseContext) and static projections.
  To bound the cost, residuals come from every `sample_every_n`th admitted decision.
- **Per decision** (`ptz.shadow.per_decision`): sampled JSONL records written verbatim to
  stdout, one per line, without the log envelope. The sampling is per source: every Nth
  decision, plus the first occurrence of each distinct decision in that window. This
  matches the Controller.

Records have the same fields and field order as the Controller's, with
`"profile":"tracker"`:

```json
{
  "record_type": "ptz_shadow",
  "profile": "tracker",
  "mode": "shadow",
  "run_id": "run-1",
  "scene_id": "…",
  "source_id": "ptz-cam",
  "sequence": 42,
  "calibration_version": "v3",
  "observation_timestamp": "2026-10-01T10:00:00.250000Z",
  "pose_age_s": 0.02,
  "timestamp_uncertainty_s": 0.01,
  "dwell_elapsed_s": 1.4,
  "admitted": true,
  "managed": true,
  "invalid_reason": null,
  "reason_detail": null,
  "detections": [
    {
      "type": "person",
      "static_xyz": [0, 0, 0],
      "candidate_xyz": [5, 2, 0],
      "residual_m": 5.39
    }
  ]
}
```

The acceptance harness (`tests/utils/ptz_shadow.py`) collects Controller and Tracker
records by `run_id` into `tests/artifacts/ptz/shadow/<run_id>.jsonl`. The Tracker never
writes artifact files.

## Metrics

All labels are bounded, with no camera or object identifiers.

| Metric                               | Labels                  | Meaning                                                                                                      |
| ------------------------------------ | ----------------------- | ------------------------------------------------------------------------------------------------------------ |
| `tracker.ptz.detections.admitted`    | `mode`                  | PTZ detection messages admitted                                                                              |
| `tracker.ptz.detections.rejected`    | `mode`, `reason_detail` | PTZ detection messages rejected                                                                              |
| `tracker.ptz.pose_messages.rejected` | `stage`                 | PoseContext or status payloads rejected before use (`size`, `json`, `schema`, `guard`, `topic`, `unmanaged`) |

## Performance

The Tracker is on the latency-critical path, so the consumer is designed to cost
nothing when it is off and close to nothing for static cameras when it is on.

- **PTZ off:** one null check per message, plus an empty pose pointer in each batch.
- **PTZ on, static camera:** one hash lookup per message.
- **PTZ camera:** one timestamp parse, an uncontended lock, and an integer-nanosecond
  dwell evaluation per message. A unit test (`ptz_allocation_test.cpp`) asserts that this
  path does not allocate.
- **Each PoseContext:** size-bounded, schema-validated, and checked for finite, rigid
  matrices once. Its projection pose, including the precomputed rotation, origin, and
  horizon, is built once and shared by every batch it admits.
- **Shadow residuals:** computed only for sampled admitted decisions, on at most 50
  detections, with cached static transformers. Tracking workers are never involved.

## Deploy

**Compose:** set `TRACKER_PTZ_ENABLED=true` or `TRACKER_PTZ_SHADOW_MODE=true`, and set the
four `TRACKER_PTZ_MAX_*` bounds in the environment of the `tracker` service. The sample
Compose file mounts `deployment/positioning-assignments.json` read-only at the default
`ptz.assignments_path`.

**Helm:** set `tracker.ptz.enabled` or `tracker.ptz.shadowMode`, and provide
`tracker.ptz.config` with the four bounds and an optional
`shadow: {run_id, sample_every_n, per_decision}`. The chart:

- renders the manifest from `positioning.assignments`,
- mounts it,
- points the Tracker at the cluster NTP service,
- fails the render when both modes are set or a bound is missing.

```yaml
tracker:
  enabled: true
  ptz:
    shadowMode: true
    config:
      max_pose_age_s: 0.5
      max_clock_offset_s: 0.05
      max_detection_pipeline_latency_s: 1.0
      max_detection_timestamp_uncertainty_s: 0.05
      shadow: { run_id: site-a-run-1, per_decision: true }
positioning:
  assignments:
    ptz-cam-1: positioning
```

## Roll back

Set `TRACKER_PTZ_ENABLED` and `TRACKER_PTZ_SHADOW_MODE` (or `tracker.ptz.enabled` and
`tracker.ptz.shadowMode`) to `false`, then restart the Tracker. PTZ cameras are then
projected with their static home pose, exactly as before Phase 5. No other state needs to
be cleaned up.
