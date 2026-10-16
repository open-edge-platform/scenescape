# Positioning API Reference

The Positioning service uses two versioned (v1) contracts for PTZ cameras:

- `PTZSample`, a protobuf message that carries the raw pan/tilt/zoom reading a camera
  reports over ONVIF. It is defined in `ptz.proto` in the protobuf package
  `scenescape.ptz.v1`.
- `ptz_calibration`, a JSON object that defines how raw pan/tilt values map to the
  camera orientation relative to its home pose.

Source files:

- `docs/user-guide/api-docs/positioning/v1/ptz.proto`
- `docs/user-guide/api-docs/positioning/v1/ptz_calibration.schema.json`

Within v1, fields are only ever added. Existing fields keep their numbers, names,
types, and meaning.

## PTZ Sample (Protobuf)

### Service `PTZPoseIngest`

| RPC               | Request     | Response       |
| ----------------- | ----------- | -------------- |
| `SubmitPTZSample` | `PTZSample` | `PTZSampleAck` |

> **Note:** In v1, the ONVIF poller passes samples to the Positioning service
> in-process. The `PTZPoseIngest` service is reserved for a future authenticated
> external producer and is not exposed on the network.

### Message `PTZSample`

| #   | Field                      | Type                        | Description                                                                                            |
| --- | -------------------------- | --------------------------- | ------------------------------------------------------------------------------------------------------ |
| 1   | `camera_id`                | `string`                    | Manager camera UID.                                                                                    |
| 2   | `adapter_instance_id`      | `string`                    | Identifies the poller instance. Changes on every poller restart.                                       |
| 3   | `sequence`                 | `uint64`                    | Monotonically increasing within one `adapter_instance_id`.                                             |
| 4   | `measured_at`              | `google.protobuf.Timestamp` | Midpoint of the ONVIF request/response interval.                                                       |
| 5   | `timestamp_uncertainty_ns` | `uint64`                    | Uncertainty of `measured_at`, at least half of the ONVIF request/response interval.                    |
| 6   | `position`                 | `PTZPosition`               | Raw position reported by the device.                                                                   |
| 7   | `reported_move_status`     | `ReportedMoveStatus`        | Move status reported by the device. Advisory only: the service derives the authoritative motion state. |

### Message `PTZPosition`

Raw device-reported values in the ONVIF position space that the camera advertises.

| #   | Field                | Type              | Description                                  |
| --- | -------------------- | ----------------- | -------------------------------------------- |
| 1   | `pan`                | `double`          | Raw pan position.                            |
| 2   | `tilt`               | `double`          | Raw tilt position.                           |
| 3   | `zoom`               | `optional double` | Raw zoom position, if the camera reports it. |
| 4   | `position_space_uri` | `string`          | ONVIF position space URI.                    |
| 5   | `pan_min`            | `double`          | Lower bound of the pan range.                |
| 6   | `pan_max`            | `double`          | Upper bound of the pan range.                |
| 7   | `tilt_min`           | `double`          | Lower bound of the tilt range.               |
| 8   | `tilt_max`           | `double`          | Upper bound of the tilt range.               |

### Enum `ReportedMoveStatus`

| Value | Name                               |
| ----- | ---------------------------------- |
| 0     | `REPORTED_MOVE_STATUS_UNSPECIFIED` |
| 1     | `REPORTED_MOVE_STATUS_IDLE`        |
| 2     | `REPORTED_MOVE_STATUS_MOVING`      |

### Message `PTZSampleAck`

| #   | Field               | Type              | Description                                                          |
| --- | ------------------- | ----------------- | -------------------------------------------------------------------- |
| 1   | `result`            | `PTZSampleResult` | Outcome of the submission.                                           |
| 2   | `detail`            | `string`          | Human-readable detail, for example the reason a sample was rejected. |
| 3   | `accepted_sequence` | `uint64`          | Sequence number of the sample.                                       |

### Enum `PTZSampleResult`

| Value | Name                               | Meaning                                             |
| ----- | ---------------------------------- | --------------------------------------------------- |
| 0     | `PTZ_SAMPLE_RESULT_UNSPECIFIED`    | Not set.                                            |
| 1     | `PTZ_SAMPLE_RESULT_ACCEPTED`       | The sample was accepted.                            |
| 2     | `PTZ_SAMPLE_RESULT_DUPLICATE`      | A sample with this `sequence` was already received. |
| 3     | `PTZ_SAMPLE_RESULT_OUT_OF_ORDER`   | `sequence` is older than the last accepted sample.  |
| 4     | `PTZ_SAMPLE_RESULT_UNKNOWN_CAMERA` | `camera_id` does not match a known camera.          |
| 5     | `PTZ_SAMPLE_RESULT_INVALID`        | The sample failed validation.                       |

## PTZ Calibration (JSON)

A `ptz_calibration` object is a per-camera model that converts raw ONVIF pan/tilt
readings into an orientation relative to the camera's home pose. The home pose
itself is stored in the Manager camera record. Unknown properties are rejected.

### Top-Level Fields

| Field                          | Type   | Required | Description                                                                                                                          |
| ------------------------------ | ------ | -------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `parameterization_version`     | string | Yes      | Must be `"v1"`.                                                                                                                      |
| `calibration_version`          | string | Yes      | Identifier of this calibration, 1 to 128 characters.                                                                                 |
| `position_space`               | object | Yes      | ONVIF position space the calibration was measured in. See [Position Space](#position-space).                                         |
| `settle_angular_threshold_deg` | number | Yes      | Angular change, in degrees, below which the camera is treated as settled. Must be > 0 and within the calibrated travel of each axis. |
| `settle_interval_s`            | number | Yes      | Time, in seconds, the position must stay within the threshold to count as settled. Must be > 0.                                      |
| `composition_order`            | array  | Yes      | Permutation of `"pan"`, `"home"`, and `"tilt"`. See [Orientation](#orientation).                                                     |
| `axes`                         | object | Yes      | Object with `pan` and `tilt` entries, each an [Axis](#axis) object.                                                                  |
| `quality`                      | object | Yes      | Contains `reprojection_rms_px` (number, >= 0): reprojection RMS error of the calibration, in pixels.                                 |
| `provenance`                   | object | No       | Measurement provenance: instrument and version, camera model and firmware, date, operator, and fitting script revision.              |

### Position Space

| Field      | Type   | Required | Description                                    |
| ---------- | ------ | -------- | ---------------------------------------------- |
| `uri`      | string | Yes      | ONVIF position space URI, 1 to 512 characters. |
| `pan_min`  | number | Yes      | Lower bound of the pan range.                  |
| `pan_max`  | number | Yes      | Upper bound of the pan range.                  |
| `tilt_min` | number | Yes      | Lower bound of the tilt range.                 |
| `tilt_max` | number | Yes      | Upper bound of the tilt range.                 |

### Axis

All fields are required.

| Field                         | Type                    | Description                                                                                                                                                                                                                                                        |
| ----------------------------- | ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `axis`                        | array of 3 numbers      | Rotation axis as a unit vector, expressed in `frame`.                                                                                                                                                                                                              |
| `frame`                       | string                  | `"world_home"`: scene frame with the head at home. `"camera_local"`: optical frame of the camera at home.                                                                                                                                                          |
| `curve`                       | array of 2 to 8 numbers | Polynomial coefficients, in increasing power, that map the raw ONVIF position to degrees. Encodes both scale and sign; axis inversion is expressed only by negative coefficients, and there is no separate inversion flag. The constant term cancels out.          |
| `home_position`               | number                  | Raw ONVIF position at the calibrated home pose.                                                                                                                                                                                                                    |
| `approach_direction`          | string                  | `"increasing"` or `"decreasing"`: direction of travel used to reach home during calibration.                                                                                                                                                                       |
| `backlash`                    | number or array         | Total gear slack in degrees. Either one value (>= 0), or 1 to 64 `[position, degrees]` nodes interpolated linearly and held constant beyond the end nodes.                                                                                                         |
| `backlash_home_tolerance_deg` | number                  | When backlash state is unknown, for example after a restart, the service initializes it from `home_position` and `approach_direction` only if the reported position is within this many degrees of home. Must be > 0 and within the calibrated travel of the axis. |
| `backlash_history_s`          | number                  | How far back, in seconds, observed motion is kept to track backlash state. Must be > 0.                                                                                                                                                                            |

### Orientation

The camera orientation is the left-to-right product of rotations in
`composition_order`. For example, `["pan", "home", "tilt"]` gives
`R_pan · R_home · R_tilt`. The translation is the same as in the home pose.

An axis whose `frame` is `world_home` must come before `home` in `composition_order`.
An axis whose `frame` is `camera_local` must come after `home`.

### Additional Validation

When a calibration is loaded, the service also checks these rules, which the JSON
Schema cannot express:

- All values are finite.
- Each `axis` is a unit vector.
- Each `*_min` value is less than the matching `*_max` value.
- `home_position` is inside the axis range.
- Each axis `frame` matches its place in `composition_order`.
- `backlash` nodes have distinct positions.
- `settle_angular_threshold_deg` and each `backlash_home_tolerance_deg` do not exceed
  the calibrated travel: the angular span of the axis `curve` over its
  `position_space` range.

### Manager Import Threshold

Manager accepts a non-null `ptz_calibration` only when its
`reprojection_rms_px` does not exceed `PTZ_CALIBRATION_RESIDUAL_THRESHOLD_PX`, a
finite, positive maximum in pixels. The Manager image sets it to `12.0`, which is
about 1 degree of pointing error at 3 m in a 1080p image. To override
it, set the variable in the Compose project `.env` file or the environment used to
launch Compose; for Helm, set `web.ptzCalibrationResidualThresholdPx`, or export
`PTZ_CALIBRATION_RESIDUAL_THRESHOLD_PX` before `make -C kubernetes install`. If the
configured value is empty, malformed, non-finite, zero, or negative, calibration
imports and non-null calibration writes are rejected.

### Manager Validation Errors

`POST` and `PUT /api/v1/camera/{uid}` and scene import validate `ptz_calibration`
with the rules above and return `400` on the first violation. The error is a stable
`<path>: <code>` string; clients should match on it rather than on free text:

```json
{ "ptz_calibration": ["axes.pan.axis: not_unit_vector"] }
```

`<path>` is the dotted field path; backlash nodes use an index, for example
`axes.tilt.backlash[1]`.

| Code                        | Meaning                                                                           |
| --------------------------- | --------------------------------------------------------------------------------- |
| `not_object`                | Value must be a JSON object.                                                      |
| `required`                  | Required field is missing.                                                        |
| `unknown_field`             | Field is not part of the v1 schema.                                               |
| `unsupported_version`       | `parameterization_version` is not `v1`.                                           |
| `not_string`                | Value must be a string.                                                           |
| `invalid_length`            | String length is outside the allowed range.                                       |
| `not_number`                | Value must be a number. Booleans are rejected.                                    |
| `not_finite`                | Number is NaN or infinite.                                                        |
| `negative`                  | Number must be >= 0.                                                              |
| `not_positive`              | Number must be > 0.                                                               |
| `invalid_range`             | `*_min` is not less than `*_max`.                                                 |
| `invalid_composition_order` | `composition_order` is not a permutation of `pan`, `home`, and `tilt`.            |
| `not_array`                 | Value must be an array.                                                           |
| `invalid_size`              | Array has the wrong number of items.                                              |
| `not_unit_vector`           | `axis` is not a unit vector.                                                      |
| `invalid_choice`            | Value is not one of the allowed strings.                                          |
| `frame_order_mismatch`      | `frame` does not match the axis position in `composition_order`.                  |
| `constant_curve`            | All non-constant `curve` coefficients are zero.                                   |
| `out_of_range`              | `home_position` is outside the position-space range.                              |
| `invalid_node`              | Backlash node is not a `[position, degrees]` pair.                                |
| `duplicate_position`        | Backlash node repeats a position.                                                 |
| `exceeds_travel`            | Angular parameter exceeds the calibrated travel.                                  |
| `threshold_not_configured`  | `PTZ_CALIBRATION_RESIDUAL_THRESHOLD_PX` is unset or not a finite positive number. |
| `exceeds_threshold`         | `reprojection_rms_px` exceeds the configured import threshold.                    |

### Home Pose

The Manager camera record also exposes the read-only `pose_matrix`: the 4x4
camera-to-scene home pose matrix (row-major, scale included) computed by Manager for
both Euler and point-correspondence cameras. It is present only when the camera
belongs to a scene and has a pose. Positioning uses `pose_matrix` as `R_home` and the
home translation; it does not rebuild the pose from the Euler `rotation` field.

### Camera Configuration Invalidation

After a camera save commits, Manager publishes to
`scenescape/cmd/camera/config/{camera_id}` at QoS 1, not retained:

```json
{ "calibration_version": "cam1-2026-10-01" }
```

`calibration_version` is `null` when the camera has no calibration. Manager publishes
on every committed camera save, including cameras without calibration and saves that
change only the home pose or scene. Moving a camera to another scene clears its
`transforms`, so the home pose must be calibrated again. A rolled-back save publishes
nothing. The message only invalidates cached state; Positioning reloads the camera
through the Manager REST API and does not treat the payload as configuration.

To onboard a PTZ camera, follow
[Onboard PTZ Cameras](./how-to-guides/calibrate-cameras/onboard-ptz-cameras.md).

### Example

```json
{
  "parameterization_version": "v1",
  "calibration_version": "cam1-2026-10-01",
  "position_space": {
    "uri": "http://www.onvif.org/ver10/tptz/PanTiltSpaces/PositionGenericSpace",
    "pan_min": -1.0,
    "pan_max": 1.0,
    "tilt_min": -1.0,
    "tilt_max": 1.0
  },
  "settle_angular_threshold_deg": 0.05,
  "settle_interval_s": 0.5,
  "composition_order": ["pan", "home", "tilt"],
  "axes": {
    "pan": {
      "axis": [0, 0, 1],
      "frame": "world_home",
      "curve": [0, 180],
      "home_position": 0.0,
      "approach_direction": "increasing",
      "backlash": 0.1,
      "backlash_home_tolerance_deg": 0.2,
      "backlash_history_s": 10
    },
    "tilt": {
      "axis": [1, 0, 0],
      "frame": "camera_local",
      "curve": [0, -45],
      "home_position": 0.0,
      "approach_direction": "decreasing",
      "backlash": [
        [-1.0, 0.1],
        [1.0, 0.15]
      ],
      "backlash_home_tolerance_deg": 0.2,
      "backlash_history_s": 10
    }
  },
  "quality": { "reprojection_rms_px": 1.2 }
}
```
