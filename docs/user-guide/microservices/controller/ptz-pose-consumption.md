<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# PTZ Pose Consumption in the Scene Controller

A pan-tilt-zoom (PTZ) camera is a tracking source only while it is parked. The
[Positioning service](../positioning/positioning.md) publishes a resolved `PoseContext`
for each PTZ camera, and the Scene Controller can use it to project the camera's
detections with the pose the camera had when it acquired them. Both modes described here
are **off by default**. With both off, the Controller behaves as before and reads no PTZ
configuration.

The exact message formats, admission rules, and reason values are defined in the
[Positioning PTZ v1 contracts](../../../design/positioning-ptz-contracts.md). This page
describes only how the Controller applies them.

## Modes

| Mode      | Environment variable         | Command-line option | Effect                                                                                                                      |
| --------- | ---------------------------- | ------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Enforcing | `CONTROLLER_PTZ_ENABLED`     | `--ptz`             | Drops PTZ detections the dwell contract rejects. Projects admitted detections with the PoseContext, not with the home pose. |
| Shadow    | `CONTROLLER_PTZ_SHADOW_MODE` | `--ptz-shadow`      | Computes every decision and the candidate projection, records them, and changes nothing else. Tracking uses the home pose.  |

Set a flag to `true`, `1`, `yes`, or `on`. A command-line option overrides the environment
variable, and `--no-ptz` / `--no-ptz-shadow` turn a mode off. The two modes are mutually
exclusive: the Controller fails to start when both are on.

The Controller also fails to start, with a message that names the problem, when:

- `--rewriteAllTime` or `--rewriteBadTime` is set. Replacing acquisition time with receive
  time makes pose matching meaningless.
- No NTP server is configured (`--ntp`). The dwell contract needs a synchronized clock.
- The configuration file or the assignment manifest is missing or invalid.

## Configuration

All values are deployment-owned and **required**; there are no defaults. Measure
`max_detection_pipeline_latency_s` for your deployment before enabling either mode.

| Option                           | Default                        | Description                                                             |
| -------------------------------- | ------------------------------ | ----------------------------------------------------------------------- |
| `--ptz_config_file`              | `ptz-consumer-config.json`     | JSON file with the bounds below, next to the Controller executable.     |
| `--positioning_assignments_file` | `positioning-assignments.json` | The shared `source_id -> resolver_id` manifest, next to the executable. |

```json
{
  "max_pose_age_s": 0.5,
  "max_clock_offset_s": 0.05,
  "max_detection_pipeline_latency_s": 1.0,
  "max_detection_timestamp_uncertainty_s": 0.05,
  "shadow": { "run_id": "unspecified", "sample_every_n": 10 }
}
```

| Key                                     | Unit | Meaning                                                                                           |
| --------------------------------------- | ---- | ------------------------------------------------------------------------------------------------- |
| `max_pose_age_s`                        | s    | A PoseContext older than this, by the Controller's clock, is not used. Must be greater than 0.    |
| `max_clock_offset_s`                    | s    | PTZ detections are dropped while the measured NTP offset exceeds it. Must be greater than 0.      |
| `max_detection_pipeline_latency_s`      | s    | Hard bound on camera-to-Controller latency. It is also the minimum dwell. Must be greater than 0. |
| `max_detection_timestamp_uncertainty_s` | s    | Uncertainty of the detection acquisition timestamp. Must be 0 or greater.                         |
| `shadow.run_id`                         |      | Label of the run for the shadow records (`A-Z a-z 0-9 . _ -`, up to 128 characters).              |
| `shadow.sample_every_n`                 |      | Record every Nth decision of a source, and always a change of decision. An integer, 1 or greater. |

The image ships an example `ptz-consumer-config.json` and an empty assignment manifest.
Replace them by mounting your files read-only. The manifest is the same file the
Positioning service and Manager read; it only maps a PTZ camera to the Resolver that
owns it. A camera belongs to the scenes Manager says it does.

## Which cameras are managed

A camera is a PTZ camera when Manager returns a `ptz_calibration` block for it. For each
PTZ camera in a scene that the Controller loads:

- If the manifest names a Resolver for it, the Controller subscribes to
  `scenescape/positioning/pose/{camera_id}` and to the status topic of that Resolver
  `scenescape/positioning/status/{resolver_id}`. It never subscribes with a wildcard, and
  Manager's ACL allows pose reads only for cameras that belong to a scene. The
  subscriptions follow scene and camera changes.
- If the manifest does not name a Resolver, the camera **fails closed**. Its detections
  are dropped, and the Controller logs an error once for the camera.

Cameras without `ptz_calibration` are never affected.

## Enforcing mode

Each detection message of a PTZ camera is checked when it arrives, before tracking. The
check is the dwell admission from the contracts document. It never waits for a pose and
never queues a detection.

- **Rejected:** the whole message is skipped. Nothing is tracked or published for it, and
  the existing tracks age normally on the next update from any source. In a scene that
  is tracked only by PTZ cameras, tracks therefore stay as they were until a PTZ message
  is admitted again.
- **Admitted:** the detections are projected with the transform of the PoseContext that
  admitted them. The camera's intrinsics and distortion stay those of its home
  calibration, and the stored home pose is never modified.
- **Visibility:** a PTZ camera sees an object only through its latest valid, fresh pose
  that matches the camera's frame and calibration version. A camera without one sees
  nothing, and the home view region is never a fallback. The same pose is used for the
  per-camera bounds of the regulated output.
- **Frame:** the pose must be expressed in `scene:{scene_uid}` of the scene that owns the
  camera, and the calibration version must equal the version Manager returns. Anything
  else is dropped as `frame_mismatch` or `calibration_changed`.
- **Clock:** while the Controller has not synchronized with the NTP server, or the
  offset exceeds `max_clock_offset_s`, PTZ detections are dropped as `sample_stale`.

Reasons are the canonical `invalid_reason` values and the bounded `reason_detail`
values of the contracts document.

## Shadow mode

Shadow mode runs the same decisions on the same messages, then lets every message
continue exactly as it would without PTZ support. For an admitted message it also
projects a copy of the detections with the PoseContext, and writes the residual against
the static projection. It never creates tracks or changes track state, and a failure in
the comparison is logged and ignored.

Each sampled decision is one JSON line on the Controller's standard output:

```json
{
  "record_type": "ptz_shadow",
  "profile": "controller",
  "mode": "shadow",
  "run_id": "run-1",
  "scene_id": "3bc091c7-e449-46a0-9540-29c499bca18c",
  "source_id": "ptz-cam-1",
  "sequence": 10432,
  "calibration_version": "ptz-cam-1-v3",
  "observation_timestamp": "2026-10-01T10:15:30.123000Z",
  "pose_age_s": 0.05,
  "timestamp_uncertainty_s": 0.012,
  "dwell_elapsed_s": 2.9,
  "admitted": true,
  "managed": true,
  "invalid_reason": null,
  "reason_detail": null,
  "detections": [
    {
      "type": "person",
      "static_xyz": [3.1, 2.0, 0.0],
      "candidate_xyz": [3.4, 2.2, 0.0],
      "residual_m": 0.36
    }
  ]
}
```

Rejected decisions have `admitted: false`, the reason, and no detections. The Controller
writes no files and needs no volume. The acceptance harness collects the lines by `run_id`
into `tests/artifacts/ptz/shadow/<run_id>.jsonl`; for a field run, export the same lines
from the Controller's logs. Enforcing mode writes the same records, without the
candidate projection.

## Metrics

With [observability](../../other-topics/how-to-enable-observability.md) enabled, the
Controller adds three counters. Labels are bounded; none is an object identifier.

| Metric                                             | Labels                  | Meaning                                                                                                              |
| -------------------------------------------------- | ----------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `scenescape_controller_ptz_detections_admitted`    | `mode`                  | PTZ messages admitted.                                                                                               |
| `scenescape_controller_ptz_detections_rejected`    | `mode`, `reason_detail` | PTZ messages rejected, by reason.                                                                                    |
| `scenescape_controller_ptz_pose_messages_rejected` | `stage`                 | Pose or status messages dropped before use. The stage is `size`, `json`, `schema`, `guard`, `topic`, or `unmanaged`. |

## Deploy

- **Docker Compose:** the sample stack passes `CONTROLLER_PTZ_ENABLED` and
  `CONTROLLER_PTZ_SHADOW_MODE` (both `false` by default), mounts
  `controller/config/ptz-consumer-config.json`, and mounts
  `deployment/positioning-assignments.json` read-only into the Controller.
  Set the variables in `.env`.
- **Kubernetes:** set `scene.ptz.enabled` or `scene.ptz.shadowMode`, and supply the four
  bounds in `scene.ptz.config`. The chart renders them, together with
  `positioning.assignments`, into a ConfigMap, and fails to render if both modes are on
  or a bound is missing.

```yaml
scene:
  ptz:
    shadowMode: true
    config:
      max_pose_age_s: 0.5
      max_clock_offset_s: 0.05
      max_detection_pipeline_latency_s: 1.0
      max_detection_timestamp_uncertainty_s: 0.05
      shadow: { run_id: field-run-1, sample_every_n: 10 }
```

## Roll back

Turn the mode off (`CONTROLLER_PTZ_ENABLED=false`, `CONTROLLER_PTZ_SHADOW_MODE=false`,
or the chart values) and restart the Controller. It returns to static projection and
stops subscribing to poses. Enable enforcing mode for a deployment only after shadow
mode meets your spatial-error, latency, and availability budgets.
