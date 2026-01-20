# How to Configure the Tracker

This document guides users and developers on configuring the tracker for specific use cases during Intel® SceneScape deployment.

## Tracker Configuration with Time-Based Parameters

### Enabling Time-Based Parameters

A `tracker-config.json` file is pre-stored in the `controller` directory. The only change required is to mount this file to the Docker container in the `scene` service. The `scene` service in the `docker-compose.yml` file should look as follows. Note the `configs` section.

```yaml
scene:
  image: scenescape-controller:${VERSION:-latest}
  # ...
  # mount the trackerconfig file to the container
  configs:
    - source: tracker-config
      target: /home/scenescape/SceneScape/tracker-config.json
```

The default content of the `tracker-config.json` file is shown below. It is recommended to keep the default values of these parameters unchanged.

```json
{
  "max_unreliable_time_s": 1.0,
  "non_measurement_time_dynamic_s": 0.8,
  "non_measurement_time_static_s": 1.6,
  "effective_object_update_rate": 10,
  "time_chunking_enabled": false
}
```

Here is a brief description of each configuration parameter:

- `max_unreliable_time_s`: Defines the time (in seconds) the tracker will wait before publishing a tracked object to the web interface. Expects a positive number.

- `non_measurement_time_dynamic_s`: Defines the time (in seconds) the tracker will wait before deleting a dead tracked object if the object was dynamic (i.e., had non-zero velocity). Expects a positive number.

- `non_measurement_time_static_s`: Defines the time (in seconds) the tracker will wait before deleting a dead tracked object if the object was static (i.e., had zero velocity). Expects a positive number.

- `effective_object_update_rate`: The effective rate at which a tracked object is observed by the tracker, derived from camera FPS and multi-camera overlap. This is not the FPS of any individual camera. **Note:** This parameter is used when `time_chunking_enabled` is `false`. If time chunking is enabled, this parameter is ignored and may be omitted.

- `time_chunking_enabled`: Enables or disables the time-chunking feature. Set to `false` for standard tracking mode.

### How Time-Based Parameters Work

Time-based tracker parameters use time durations (in seconds) instead of frame counts, providing consistent tracking behavior regardless of camera frame rates. The three time-based parameters are:

- `max_unreliable_time_s`: Time to wait before publishing a tracked object
- `non_measurement_time_dynamic_s`: Time to wait before deleting a dynamic dead track
- `non_measurement_time_static_s`: Time to wait before deleting a static dead track

These parameters define absolute time durations, ensuring predictable tracking behavior across different camera configurations and frame rates.

### Setting effective_object_update_rate

The `effective_object_update_rate` parameter should be adjusted based on individual camera FPS and camera overlap to match the object refresh rate from the tracker's perspective—the effective temporal sampling rate of object observations as seen by the tracker.

For example:

- If cameras run at 10 FPS and there is **no camera overlap**, set `effective_object_update_rate = 10`
- If cameras run at 10 FPS and there is an **average overlap of two cameras** covering the area, set `effective_object_update_rate = 20`

This ensures that the tracker's internal timing parameters are calibrated correctly for your specific deployment scenario.

## Time-Chunking Configuration

If time-chunking is disabled, the tracker processes each camera frame individually, meaning it processes data at a rate equal to the cumulative camera FPS (frames per second). Cumulative camera FPS is the sum of FPS for all cameras.

Enabling time-chunking changes how the tracker processes input data: instead of processing each frame individually, the tracker processes data at a constant rate defined by `time_chunking_rate_fps`. Detections from different cameras are grouped into chunks based on a time window of `1 / time_chunking_rate_fps` seconds. If a single camera produces multiple frames within a time chunk, only the most recent frame from that camera is processed.

### When to Use Time-Chunking

Time-chunking should be used to reduce the load on the tracker when high cumulative camera FPS prevents the tracker from processing new detections within the given time budget, effectively causing input data to be dropped. This manifests as `Tracker work queue is not empty` warnings in controller logs. This typically occurs when the number of cameras is high, even if individual camera FPS is at the minimum acceptable level.

If high FPS from individual cameras is causing pressure on the tracker, it is recommended to first reconfigure the cameras to use the lowest acceptable FPS for the use case.

### Enabling Time-Chunking

In the `configs` section of your `docker-compose.yml`, change the `tracker-config` to point to `controller/config/tracker-config-time-chunking.json`:

```yaml
configs:
  tracker-config:
    # Use this configuration file to run tracking with time-chunking enabled
    file: ./controller/config/tracker-config-time-chunking.json
    # file: ./controller/config/tracker-config.json
```

The content of the `tracker-config-time-chunking.json` file is shown below.

```json
{
  "max_unreliable_time_s": 1.0,
  "non_measurement_time_dynamic_s": 0.8,
  "non_measurement_time_static_s": 1.6,
  "time_chunking_enabled": true,
  "time_chunking_rate_fps": 10
}
```

Here is a brief description of the time-chunking-specific configuration parameters:

- `time_chunking_enabled`: Enables or disables the time-chunking feature. Set to `true` to enable.
- `time_chunking_rate_fps`: Defines the tracker processing rate in frames per second (valid range: 1–100). The tracker processes data in chunks at intervals of `1 / time_chunking_rate_fps` seconds. For example, if `time_chunking_rate_fps` is 10, the time chunking interval is 0.1 seconds (100 ms). **Note:** This parameter is required when `time_chunking_enabled` is `true`. If time chunking is disabled, this parameter is ignored and may be omitted.

### How to Set Time-Chunking Interval

The rule of thumb for setting the time-chunking rate is to match the highest camera frame rate in your deployment: `time_chunking_rate_fps = highest_camera_FPS`. This way, no input data will be dropped during time-chunking.

The time-chunking rate may be further decreased below the recommended value if additional performance improvements are needed. However, in this case, more than one frame from a camera might fall within a time chunk, and the potential accuracy loss caused by dropped frames should be carefully balanced against performance benefits.

### Adjusting Time-Based Parameters for Time-Chunking

When time-chunking is enabled, time-based parameters (`max_unreliable_time_s`, `non_measurement_time_dynamic_s`, `non_measurement_time_static_s`) continue to define absolute time durations in seconds. However, the track refresh rate changes to match the tracker processing rate defined by `time_chunking_rate_fps` instead of being determined by individual camera frame rates.

You may need to adjust the time-based parameters when enabling time-chunking, depending on:

- Camera overlap in your deployment
- The relationship between your cameras' FPS and the chosen `time_chunking_rate_fps`
- The expected object dynamics in your scene

Always experimentally verify which parameters work best for your specific use case.

## Converting from Frame-Based to Time-Based Configuration

If you have an older configuration that has proven to work well using frame-based parameters, use the following instructions to convert it to the time-based format.

### Converting with Time-Chunking Disabled

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
  "time_chunking_interval_milliseconds": 100
}
```

The converted time-based configuration would be:

```json
{
  "max_unreliable_time_s": 1.0,
  "non_measurement_time_dynamic_s": 0.8,
  "non_measurement_time_static_s": 1.6,
  "time_chunking_enabled": true,
  "time_chunking_rate_fps": 10
}
```
