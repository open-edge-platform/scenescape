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

## Persisting Object Attributes Across Detection Gaps

Detection pipelines don't always re-report every attribute (e.g. shirt color, license plate,
age/gender) on every frame. By default, an attribute that's missing from the current detection is
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
