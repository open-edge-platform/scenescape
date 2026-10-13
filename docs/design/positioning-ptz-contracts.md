# Positioning PTZ v1: Contracts Reference

- **Date**: 2026-10-12
- **Status**: `Accepted` (Phase 1: contracts and pose math)
- **Design**: [PTZ Pose, v1 Capability of the Positioning Service](./ptz-camera-pose-service.md)

This document is the canonical reference for the contracts shared by the
Positioning service, the Manager, and the pose consumers (Controller and Tracker).
The rationale is in the design document. This document records the exact rules
that implementations and tests must follow.

## Artifact Locations

| Contract                          | Location                                                                            |
| --------------------------------- | ----------------------------------------------------------------------------------- |
| Raw PTZ sample protobuf           | `docs/user-guide/api-docs/positioning/v1/ptz.proto` (package `scenescape.ptz.v1`)   |
| Generated Python stubs            | `positioning/src/positioning/v1/` (import `positioning.v1.ptz_pb2`)                 |
| PTZ calibration schema            | `docs/user-guide/api-docs/positioning/v1/ptz_calibration.schema.json`               |
| PoseContext / status JSON schemas | `controller/src/schema/metadata.schema.json` (`pose_context`, `positioning_status`) |
| Pose math and calibration loader  | `positioning/src/positioning/pose_math.py`, `ptz_model.py`                          |
| Consumer-shared logic             | `scene_common/src/scene_common/positioning_*.py`                                    |
| Dwell conformance vectors         | `tests/data/ptz/dwell_conformance.json` ([format](../../tests/data/ptz/README.md))  |

The user-facing description of these contracts is in the
[Positioning API Reference](../user-guide/positioning-api-reference.md).

## Protobuf Package and Import Path

The protobuf package is `scenescape.ptz.v1`. The Python import path is
`positioning.v1` (for example, `from positioning.v1 import ptz_pb2`). The import path
comes from the file location relative to the `-I docs/user-guide/api-docs` include
root, not from the `package` statement. The two names are different on purpose.

## Protobuf Compatibility Policy

The `scenescape.ptz.v1` package is the wire compatibility boundary.

- Within v1, you can only add new optional fields.
- Never renumber, rename, retype, or reuse a field, and never change what an existing
  field means. Mark removed fields as `reserved`.
- Any incompatible change requires a new package, for example `scenescape.ptz.v2`.

In v1, the ONVIF poller passes `PTZSample` to the Resolver in-process. The
`PTZPoseIngest` service is kept for a future authenticated external producer.

## Regenerating Stubs

```bash
pip install grpcio-tools==1.71.2   # protobuf 5.29.x, as pinned in tests/requirements.txt
docs/user-guide/api-docs/positioning/v1/generate.sh  # set PYTHON=<interpreter> to override python3
```

The script writes `ptz_pb2.py`, `ptz_pb2.pyi`, and `ptz_pb2_grpc.py` to
`positioning/src/positioning/v1/`. It adds SPDX headers and lint-skip directives, and
reindents the Python files to the repository's 2-space style. Running it again
produces identical output.

## MQTT Topics

The topic names are defined in this phase. They are registered in
`scene_common.mqtt.PubSub` and the ACLs in Phase 2.

| Topic                                         | Publisher   | QoS / retain      | Payload schema       |
| --------------------------------------------- | ----------- | ----------------- | -------------------- |
| `scenescape/positioning/pose/{source_id}`     | Positioning | 0 / retained      | `pose_context`       |
| `scenescape/positioning/status/{resolver_id}` | Positioning | 0 / retained, LWT | `positioning_status` |
| `scenescape/cmd/camera/config/{camera_id}`    | Manager     | Phase 2           | Phase 2              |

In v1, `source_id` is the Manager camera UID. Raw PTZ samples are never sent over MQTT.

The `positioning_status` payload has `resolver_id`, `status`
(`online` | `offline`), and `timestamp`. The `timestamp` is the session start time.
The LWT keeps the timestamp that was registered at CONNECT, so do not use it to
determine when the Resolver failed.

## PoseContext Payload

The `pose_context` schema is self-contained and compatible with draft-04 (it has no
`$ref`, `const`, or `if`/`then`/`else`). This lets the Tracker copy it unchanged.

- `valid: true` requires `pose` and `quality`, and must not include
  `invalid_reason` or `reason_detail`.
- `valid: false` requires `invalid_reason` and must not include `pose`.
- `pose.matrix_4x4` is a row-major `scene_from_camera` rigid transform in metres.

After schema validation, consumers run
`scene_common.positioning_schema_guards`. These guards check that the payload is at most
4096 bytes, that all numbers are finite, that the matrix is exactly 4x4 with last row
`[0, 0, 0, 1]`, and that the rotation block is orthonormal with determinant +1.

Sequence semantics: `PoseContext.sequence` equals the accepted
`PTZSample.sequence`. Every accepted sample produces exactly one PoseContext, which
can be valid or invalid. A rejected sample produces no PoseContext, so consumers see
it as a sequence gap.

## Failure Reasons

The canonical `invalid_reason` values are shared with
`controller/src/controller/external_source.py`. A unit test checks that the two
definitions do not drift apart.

| `reason_detail`            | `invalid_reason`    | Published by       |
| -------------------------- | ------------------- | ------------------ |
| `no_sample`                | `no_pose_available` | Resolver, consumer |
| `sample_stale`             | `pose_expired`      | Resolver, consumer |
| `moving`                   | `invalid_pose`      | Resolver, consumer |
| `settling`                 | `invalid_pose`      | Resolver, consumer |
| `calibration_missing`      | `invalid_pose`      | Resolver           |
| `calibration_changed`      | `invalid_pose`      | Resolver, consumer |
| `invalid_sample`           | `invalid_pose`      | Resolver           |
| `backlash_unknown`         | `invalid_pose`      | Resolver           |
| `dwell_incomplete`         | `invalid_pose`      | Consumer only      |
| `observation_before_dwell` | `invalid_pose`      | Consumer only      |
| `detection_too_old`        | `pose_expired`      | Consumer only      |
| `frame_mismatch`           | `invalid_pose`      | Consumer only      |

The consumer-only details are admission decisions. They are used for metrics and
shadow records and are never included in a PoseContext.

## Dwell Admission (v1)

Implemented by `scene_common.positioning_dwell.DwellTracker`. Every timestamp and
duration is converted to integer nanoseconds, so boundary comparisons are exact.

The tracker resets dwell when any of the following occur:

- An invalid or non-stationary PoseContext arrives.
- The sequence has a gap or does not increase.
- The timestamp does not increase.
- The source, frame, or calibration version does not match.
- The calibration version changes.
- The Resolver session changes. This includes a new status `timestamp` or any
  status other than `online`.

`stationary_since` and its uncertainty come from the first PoseContext of the new
dwell.

Checks are evaluated in this order. The first check that fails determines the
reported reason:

1. A PoseContext has been received. If not, the result is `no_sample`.
2. The latest PoseContext is valid. If not, its own reason is reported.
3. The latest PoseContext is stationary. Otherwise, the result is `moving` or
   `settling`, or `no_sample` when the state is `unknown`.
4. The frame and calibration version match the consumer's expected values.
   Otherwise, the result is `frame_mismatch` or `calibration_changed`.
5. A dwell is active. If not, the result is `dwell_incomplete`.
6. The pose is fresh: `local_now < valid_until` and
   `local_now - latest.timestamp < max_pose_age_s`. Otherwise, the result is
   `sample_stale`.
7. `local_now - observation <= max_detection_pipeline_latency_s`. Otherwise, the
   result is `detection_too_old`.
8. `observation <= latest.timestamp`. Otherwise, the result is `no_sample`.
9. `(latest.timestamp - stationary_since) - latest.uncertainty - stationary_since_uncertainty >= max_detection_pipeline_latency_s`.
   Otherwise, the result is `dwell_incomplete`.
10. `observation - max_detection_timestamp_uncertainty_s >= stationary_since`.
    Otherwise, the result is `observation_before_dwell`.

Consumers drop a rejected detection immediately and never queue it.

## Configuration

`scene_common.positioning_config.load_consumer_config` validates only the values that
consumers hold. All of these values are required and none has a default.

| Parameter                               | Unit | Validation   |
| --------------------------------------- | ---- | ------------ |
| `max_pose_age_s`                        | s    | finite, > 0  |
| `max_clock_offset_s`                    | s    | finite, > 0  |
| `max_detection_pipeline_latency_s`      | s    | finite, > 0  |
| `max_detection_timestamp_uncertainty_s` | s    | finite, >= 0 |

The Positioning service validates its own runtime settings at startup in Phases 3a
and 3b. These include `poll_interval_s`, `sample_ring_buffer_size`, and the inequality
`max_pose_age_s >= poll_interval_s + max_timestamp_uncertainty_s`.
The motion and backlash parameters are stored in `ptz_calibration`.

## PTZ Calibration Model

`ptz_calibration` (`parameterization_version: "v1"`) has these parts:

- The advertised position space: URI and pan/tilt ranges.
- `settle_angular_threshold_deg` and `settle_interval_s`.
- A `composition_order`, which is a permutation of `pan`, `home`, and `tilt`.
- One entry per axis with these fields:
  - `axis`: a unit vector.
  - `frame`: `world_home` when the axis is left of `home`, or `camera_local` when it
    is right of `home`.
  - `curve`: polynomial coefficients. The curve encodes both scale and sign, so
    `scale` and `invert` fields are not allowed.
  - `home_position` and `approach_direction`.
  - `backlash`: a scalar, or `[position, degrees]` nodes.
  - `backlash_home_tolerance_deg` and `backlash_history_s`.
- `quality.reprojection_rms_px`.
- An optional `provenance` object.

The orientation is the left-to-right product in the composition order. For example,
`["pan", "home", "tilt"]` gives `R_pan · R_home · R_tilt`. Translation is unchanged
from the home pose.

`positioning.ptz_model.load_ptz_model` also checks constraints that the JSON Schema
cannot express: finite values, unit axes, ordered ranges, home position inside the
range, frame consistency with the composition order, and distinct backlash nodes.

## Golden Data Prerequisite

`tests/data/ptz/provisional_pose_math.json` uses PoC values and placeholders. It is
for development only. Phase 1 math acceptance closes only after
`tests/data/ptz/reprojection_golden.json` is committed. That file comes from a
hardware measurement session and contains measured calibration, held-out residuals
in both travel directions, and full provenance.
