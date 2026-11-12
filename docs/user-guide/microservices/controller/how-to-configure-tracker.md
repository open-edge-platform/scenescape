# How to Configure the Tracker

This document guides users and developers on configuring the tracker for specific use cases
during Scenescape deployment.

> **Note:** When using the separate Tracker microservice (`--profile tracker` /
> `make demo-tracker`), configure the Tracker service rather than the Scene
> Controller's `tracker-config.json`. Scene Controller tracker configuration
> applies to Controller-proper deployments (`--profile controller`).

## Tracker Configuration with Time-Based Parameters

### Enabling Time-Based Parameters

A `tracker-config.json` file is pre-stored in the [`config` directory](https://github.com/open-edge-platform/scenescape/tree/main/controller/config) in the repository.
The only change required is to mount this file to the Docker container in the `scene` service.
The `scene` service in the `docker-compose.yml` file should look as follows. Note the `configs`
section.

```yaml
scene:
  image: intel/scenescape-controller:${VERSION:-latest}
  # ...
  # mount the trackerconfig file to the container
  configs:
    - source: tracker-config
      target: /home/scenescape/Scenescape/tracker-config.json
```

The default content of the `tracker-config.json` file is shown below. It is recommended to
keep the default values of these parameters unchanged.

```json
{
  "max_unreliable_time_s": 1.0,
  "non_measurement_time_dynamic_s": 0.8,
  "non_measurement_time_static_s": 1.6,
  "time_chunking_enabled": true,
  "time_chunking_rate_fps": 10
}
```

Here is a brief description of each configuration parameter:

- `max_unreliable_time_s`: Defines the time (in seconds) the tracker will wait before
  publishing a tracked object to the web interface. Expects a positive number.

- `non_measurement_time_dynamic_s`: Defines the time (in seconds) the tracker will wait before
  deleting a dead tracked object if the object was dynamic (i.e., had non-zero velocity).
  Expects a positive number.

- `non_measurement_time_static_s`: Defines the time (in seconds) the tracker will wait before
  deleting a dead tracked object if the object was static (i.e., had zero velocity). Expects a
  positive number.

- `time_chunking_enabled`: Enables or disables the time-chunking feature. Set to `true` for
  time-chunking mode (default).

- `time_chunking_rate_fps`: Defines the tracker processing rate in frames per second (valid
  range: 1–100). The tracker processes data in chunks at intervals of `1 / time_chunking_rate_fps`
  seconds. For example, if `time_chunking_rate_fps` is 10, the time chunking interval is 0.1
  seconds (100 ms). **Note:** This parameter is used when `time_chunking_enabled` is `true`.
  If time chunking is disabled, this parameter is ignored and may be omitted.

### How Time-Based Parameters Work

Time-based tracker parameters use time durations (in seconds) instead of frame counts,
providing consistent tracking behavior regardless of camera frame rates. The three time-based
parameters are:

- `max_unreliable_time_s`: Time to wait before publishing a tracked object
- `non_measurement_time_dynamic_s`: Time to wait before deleting a dynamic dead track
- `non_measurement_time_static_s`: Time to wait before deleting a static dead track

These parameters define absolute time durations, ensuring predictable tracking behavior across
different camera configurations and frame rates.

### How to Set Time-Chunking Rate

The rule of thumb for setting the time-chunking rate is to match the highest camera frame rate
in your deployment: `time_chunking_rate_fps = highest_camera_FPS`. This way, no input data
will be dropped during time-chunking.

The time-chunking rate may be further decreased below the recommended value if additional
performance improvements are needed. However, in this case, more than one frame from a camera
might fall within a time chunk, and the potential accuracy loss caused by dropped frames should
be carefully balanced against performance benefits.

## Time-Chunking Overview

Time-chunking is the default tracking mode. Instead of processing each camera frame
individually, the tracker processes data at a constant rate defined by
`time_chunking_rate_fps`. Detections from different cameras are grouped into chunks based on
a time window of `1 / time_chunking_rate_fps` seconds. If a single camera produces multiple
frames within a time chunk, only the most recent frame from that camera is processed.

Time-chunking reduces load on the tracker when high cumulative camera FPS (sum of FPS for all
cameras) prevents the tracker from processing new detections within the given time budget.

### Adjusting Time-Based Parameters for Time-Chunking

When time-chunking is enabled, time-based parameters (`max_unreliable_time_s`,
`non_measurement_time_dynamic_s`, `non_measurement_time_static_s`) continue to define absolute
time durations in seconds. However, the track refresh rate changes to match the tracker
processing rate defined by `time_chunking_rate_fps` instead of being determined by individual
camera frame rates.

You may need to adjust the time-based parameters depending on:

- Camera overlap in your deployment
- The relationship between your cameras' FPS and the chosen `time_chunking_rate_fps`
- The expected object dynamics in your scene

Always experimentally verify which parameters work best for your specific use case.

## Immediate Mode (Time-Chunking Disabled)

Immediate mode means `time_chunking_enabled` is set to `false`, so inputs are
processed as they arrive without time-chunk buffering.

If time-chunking is disabled, the tracker processes each camera frame individually, meaning it
processes data at a rate equal to the cumulative camera FPS.

In the `configs` section of your `docker-compose.yml`, change the `tracker-config` to point
to `controller/config/tracker-config-immediate.json`:

```yaml
configs:
  tracker-config:
    # Use this configuration file to run tracking in immediate mode
    file: ./controller/config/tracker-config-immediate.json
    # file: ./controller/config/tracker-config.json
```

The content of the `tracker-config-immediate.json` file is shown below.

```json
{
  "max_unreliable_time_s": 1.0,
  "non_measurement_time_dynamic_s": 0.8,
  "non_measurement_time_static_s": 1.6,
  "effective_object_update_rate": 10,
  "time_chunking_enabled": false
}
```

- `effective_object_update_rate`: The effective rate at which a tracked object is observed by
  the tracker, derived from camera FPS and multi-camera overlap. This is not the FPS of any
  individual camera. **Note:** This parameter is used when `time_chunking_enabled` is `false`.
  If time chunking is enabled, this parameter is ignored and may be omitted.

- `time_chunking_enabled`: Set to `false` to disable time-chunking.

### Setting effective_object_update_rate

The `effective_object_update_rate` parameter should be adjusted based on individual camera FPS
and camera overlap to match the object refresh rate from the tracker's perspective—the
effective temporal sampling rate of object observations as seen by the tracker.

For example:

- If cameras run at 10 FPS and there is **no camera overlap**, set
  `effective_object_update_rate = 10`
- If cameras run at 10 FPS and there is an **average overlap of two cameras** covering the
  area, set `effective_object_update_rate = 20`

This ensures that the tracker's internal timing parameters are calibrated correctly for your
specific deployment scenario.

## Converting from Frame-Based to Time-Based Configuration

If you have an older configuration that has proven to work well using frame-based parameters, use the following instructions to convert it to the time-based format.

### Converting with Immediate Mode

First, determine the `effective_object_update_rate` as described above, then apply the following conversion formula:

```
time_parameter_s = frame_parameter / effective_object_update_rate
```

For example, to convert this frame-based configuration:

```json
{
  "max_unreliable_frames": 10,
  "non_measurement_frames_dynamic": 8,
  "non_measurement_frames_static": 16,
  "baseline_frame_rate": 30
}
```

Assuming `effective_object_update_rate = 10`, the converted time-based configuration would be:

```json
{
  "max_unreliable_time_s": 1.0,
  "non_measurement_time_dynamic_s": 0.8,
  "non_measurement_time_static_s": 1.6,
  "effective_object_update_rate": 10,
  "time_chunking_enabled": false
}
```

### Converting with Time-Chunking Enabled

When converting to a time-chunking enabled configuration, apply the following conversion formulas:

```
time_parameter_s = frame_parameter / time_chunking_rate_fps
time_chunking_rate_fps = 1000 / time_chunking_interval_milliseconds
```

For example, to convert this frame-based configuration with time-chunking:

```json
{
  "max_unreliable_frames": 10,
  "non_measurement_frames_dynamic": 8,
  "non_measurement_frames_static": 16,
  "time_chunking_enabled": true,
  "time_chunking_interval_milliseconds": 100,
  "suspended_track_timeout_secs": 60.0
}
```

The converted time-based configuration would be:

```json
{
  "max_unreliable_time_s": 1.0,
  "non_measurement_time_dynamic_s": 0.8,
  "non_measurement_time_static_s": 1.6,
  "time_chunking_enabled": true,
  "time_chunking_rate_fps": 10,
  "suspended_track_timeout_secs": 60.0
}
```

## Suspended Track Timeout

The tracker may accumulate suspended tracks for some time for re-tracking purposes (tracks that have been temporarily suspended rather than deleted). To avoid unbounded memory growth, suspended tracks are deleted after a configurable period. You can set an upper bound on how long suspended tracks are retained.

- **Parameter:** `suspended_track_timeout_secs`
- **Meaning:** Maximum age in seconds for suspended tracks before they are cleaned up. Default: `60.0` seconds.
- **How to set it:**
  - Add `"suspended_track_timeout_secs": <value>` to `controller/config/tracker-config.json` (or `tracker-config-immediate.json` for immediate mode).
  - The parameter follows the same configuration flow as other tracker parameters like `max_unreliable_time_s` and `non_measurement_time_dynamic_s`.

## Detection-to-Track Association

Association decides which detections update which tracks, with one of two methods:

- `euclidean`: a meter gate. The shipped configs use it, as association worked before the
  `association` block: `controller/config/tracker-config.json` (also `-immediate` and
  `-persist-attr`) and the Tracker service's `tracker/config/tracker.json`.
- `position_mahalanobis`: covariance-aware Mahalanobis gating, and the default when a config has
  no `association` block. The alternative configs `controller/config/tracker-config-mahalanobis.json`
  and `tracker/config/tracker-mahalanobis.json` select it.

Set the `association` block in `controller/config/tracker-config.json` (Controller-proper) or
under `tracking.association` in the Tracker service `tracker.json`:

```json
{
  "association": {
    "method": "position_mahalanobis",
    "gate_probability": 0.99,
    "max_radius_m": 10.0,
    "birth_cluster_radius_m": 2.0
  }
}
```

To use Mahalanobis gating in a deployment, point the Scene Controller's `tracker-config` (the
`configs` section of `docker-compose.yml`) at `tracker-config-mahalanobis.json`, and set
`TRACKER_ASSOCIATION_METHOD=position_mahalanobis` for the Tracker service, which then uses the
same values as its `tracker-mahalanobis.json`.

| Field              | Meaning                                                                                                                                                                                                                                                                                                                                                                                                                        | Default                                                                                                                         |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------- |
| `method`           | `position_mahalanobis` (UKF predicted covariance + χ² gate) or `euclidean` (meter gate; the shipped configs)                                                                                                                                                                                                                                                                                                                   | `position_mahalanobis`                                                                                                          |
| `gate_probability` | χ² gate probability for Mahalanobis: on x, y and z (3 DOF) when the track and the detection both have measured z, on x and y (2 DOF) otherwise. Ignored for Euclidean.                                                                                                                                                                                                                                                         | `0.99`                                                                                                                          |
| `max_radius_m`     | Euclidean: track↔detection association distance (m); without it, see Euclidean below. Mahalanobis: hard Euclidean **safety ceiling** (m) so a bad track covariance cannot associate arbitrarily far (also keeps the χ² gate from being clipped under long coast). Does **not** set cross-camera birth clustering radius (2 m). Does **not** model multi-camera pose disagreement—that is Phase 2 measurement R (see ADR-0019). | `10.0` for `position_mahalanobis`; for `euclidean` the objects' `tracking_radius` (Scene Controller) or `2.0` (Tracker service) |
| `birth_cluster_radius_m`| Euclidean radius (m) that groups new detections of one object seen by different cameras into one track; optional, see below. Independent of `method` and `max_radius_m`.                                                                                                                                                                                                                                                       |

**Euclidean:** with `"method": "euclidean"` and no `max_radius_m`, as in the shipped configs,
association works as before the `association` block: the
Scene Controller gates and clusters cross-camera births on the average `tracking_radius` of the
frame's objects (set per object class in the [Object Library](../../other-topics/how-to-define-object-properties.md#tracking-behavior-settings));
the Tracker service on 2 m. With `max_radius_m`, every class uses that gate, births cluster at 2 m,
and the Scene Controller logs a warning for objects whose `tracking_radius` it ignores.

**Birth clustering:** detections of one new object seen by several cameras start one track when they
lie within the birth-clustering radius of each other. Without `birth_cluster_radius_m`, the Tracker
service uses 2 m and the Scene Controller uses the gate described above for `euclidean` without
`max_radius_m` (the average `tracking_radius`), else 2 m. With `birth_cluster_radius_m`, **the explicit
value wins**: every class and both services use it, also for `euclidean` without `max_radius_m`, where
the association gate stays on `tracking_radius`. The Scene Controller applies a changed value to running
trackers; the Tracker service reads it at startup.

**Tracker service env overrides** (optional): `TRACKER_ASSOCIATION_METHOD`,
`TRACKER_ASSOCIATION_GATE_PROBABILITY`, `TRACKER_ASSOCIATION_MAX_RADIUS_M`,
`TRACKER_ASSOCIATION_BIRTH_CLUSTER_RADIUS_M`.

A `gate_probability` outside (0, 1], or a negative or non-finite (`nan`, `inf`) `max_radius_m` or
`birth_cluster_radius_m`, fails Tracker service startup; the Controller logs an error and uses the
default (for `birth_cluster_radius_m`: the behaviour without it).

An invalid `method` fails Tracker service startup. The Scene Controller logs an error and uses
the default `association` block, ignoring the block's other fields, as it does for a block that
is not a JSON object. Omitting the `association` block uses the defaults above.

## Kalman Filter Settings

The tracker smooths and predicts object motion with a Kalman filter. Its noise settings are global
(one value for all scenes and categories) and read once at startup; a change needs a restart. They are
optional: without them both services run the production filter, bit for bit.

Set the `filter` block at the top level of `controller/config/tracker-config.json` (Controller-proper)
or under `tracking.filter` in the Tracker service `tracker.json`:

```json
{
  "filter": {
    "process_noise": 0.0001,
    "base_measurement_noise": 0.2,
    "init_state_covariance": 1.0
  }
}
```

| Field                    | Default  | Meaning                                                                                                                                                                                                                                                                                                                             |
| ------------------------ | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `process_noise`          | `0.0001` | Process noise scale _q_: how much the object's motion may deviate from the model per second. It scales all process noise: velocity (more along the direction of motion, growing with speed), acceleration, vertical velocity, turn rate and yaw. There is no direct position or size noise. Larger values follow manoeuvres faster and smooth less. |
| `base_measurement_noise` | `0.2`    | Measurement noise _r_: the variance assumed for every detection component (position, size, yaw), and the initial variance of the measured states. Larger values trust detections less and smooth more.                                                                                                                              |
| `init_state_covariance`  | `1.0`    | Initial velocity variance _P0_ (m²/s²) of a new track. It sets how fast a track picks up an object that enters already moving, and caps the initial acceleration (0.1), yaw (0.05) and yaw-rate (0.01) variances, so values below 0.1 lower them.                                                                                    |

Every value must be a finite number greater than 0. The Tracker service takes the same values from
`TRACKER_FILTER_PROCESS_NOISE`, `TRACKER_FILTER_BASE_MEASUREMENT_NOISE` and
`TRACKER_FILTER_INIT_STATE_COVARIANCE` (environment over config file over default); an invalid value, or
an unknown field in the block, fails Tracker service startup. The Scene Controller logs an error for an
invalid field and uses its default; a `filter` block that is not a JSON object is ignored the same way.

The shipped configs have no `filter` block. Treat any change as a tuning step:

- The filter also decides the association gate. With `position_mahalanobis` the gate is the track's
  predicted covariance plus _r_, so every change to _q_, _r_ or _P0_ moves it as well; with `euclidean`
  the gate is fixed but the predicted positions it is measured from still change.
- Change one value at a time and check identity switches and track fragmentation on your own data.
- The motion models, the shape of the process noise and the filter's internal constants are not
  configurable.

## Persisting Object Attributes Across Detection Gaps

Detection pipelines do not always re-report every attribute (e.g., shirt color, license plate,
age/gender) on every frame. By default, an attribute that is missing from the current detection is
cleared on the tracked object. The `persist_attributes` field carries specific attributes forward
between updates instead of letting them flicker or disappear.

- **Parameter:** `persist_attributes` (object, keyed by detection type)
- **Default:** `{}` (not set) — no attributes are persisted; every detection overwrites what was there before.
- **Format:**

  ```json
  {
    "persist_attributes": {
      "vehicle": ["color", { "license": "plate,state" }],
      "person": ["age", "gender"]
    }
  }
  ```

  - Top-level keys are detection types and must match the object type string the pipeline
    publishes (e.g. `person`, `vehicle`).
  - List entries are either a plain attribute name (`"color"`) or a `{parent: "sub,fields"}` dict
    for nested/sub-attributes (e.g. a `license` object with `plate` and `state` fields) — only the
    listed sub-fields are persisted, not the whole nested object.
  - Only list attributes that actually appear in the detection pipeline's output metadata;
    persisting a key that never appears has no effect.

- **How to set it:** Add the `persist_attributes` key to `controller/config/tracker-config.json`
  (or `tracker-config-immediate.json`), alongside the timing/motion parameters above, and restart
  the scene controller (`docker compose up -d --force-recreate scene`) to pick up the change.
