# PTZ Test Data

| File                         | Purpose                                                                                                                                                                                       |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `dwell_conformance.json`     | Shared dwell-admission vectors. The Controller and Tracker suites load this file unmodified. The Controller replays it in `tests/sscape_tests/scenescape/test_controller_ptz_conformance.py`. |
| `provisional_pose_math.json` | Development-only pose-math fixture with early measured values and placeholders (`"provisional": true`). It is not golden data.                                                                |
| `reprojection_golden.json`   | Held-out hardware measurement used by `test_positioning_hardware_golden.py`: calibration, ONVIF traces, published PoseContexts and AprilTag correspondences. No images.                       |
| `acceptance_profile.json`    | Acceptance budgets per MOT profile, checked against the golden measurement.                                                                                                                   |

`source.measured` and `source.placeholders` list which provisional values were
measured and which are placeholders. The fixture is not validated calibration data.

## `dwell_conformance.json` Format

Top-level fields:

- `fixture_version`: An integer. Increment it for any incompatible format change.
- `epsilon_s`: `1e-6` (1 µs). This is the step used in every boundary vector. A
  `*_boundary` vector checks one value exactly at the limit and one value a single
  `epsilon_s` past it.
- `vectors[]`: The test vectors. Each vector is replayed on a fresh consumer.

Each vector has these fields:

- `name` and `description`.
- `config`: The four consumer values `max_pose_age_s`, `max_clock_offset_s`,
  `max_detection_pipeline_latency_s`, and `max_detection_timestamp_uncertainty_s`.
  The last value is the observation timestamp uncertainty.
- `consumer`: `source_id`, `resolver_id`, `expected_frame_id`, and
  `expected_calibration_version`. When `expected_calibration_version` is `null`, the
  consumer does not pin a calibration version.
- `events[]`: Events in wire-arrival order. Each event has a `type` field:
  - `status`: `payload` is a `positioning_status` message.
  - `pose`: `payload` is a `pose_context` message that passes schema validation.
  - `observation`: A detection to evaluate against the state at this point. It has
    `timestamp` (acquisition time), `local_now` (the consumer's synchronized clock
    at admission), and `expected`, which is
    `{admitted, invalid_reason?, reason_detail?}`.

All timestamps are ISO-8601 UTC strings with microsecond precision. Convert them to
integer nanoseconds before comparing so that boundary checks are exact. For the
order of the admission checks and the reason mapping, see
[docs/design/positioning-ptz-contracts.md](../../../docs/design/positioning-ptz-contracts.md).
