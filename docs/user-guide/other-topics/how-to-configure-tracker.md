# How to Configure the Tracker

This document is intended to guide users and developers on how to enable the use of time-based parameters and time-chunking during the deployment of Intel® SceneScape.

## Tracker Configuration with Time-Based Parameters

This section explains how to enable and use time-based parameters for the tracker.

### Enabling Time-Based Parameters

A `tracker-config.json` file is pre-stored in the `controller` directory. The only change required is to mount this file to the docker container in the `scene` service. The `scene` service in `docker-compose.yml` file should look as follows. Please note the `configs` section.

```yaml
scene:
    image: scenescape-controller:${VERSION:-latest}
    init: true
    networks:
      scenescape:
    depends_on:
      web:
        condition: service_healthy
      broker:
        condition: service_started
      ntpserv:
        condition: service_started
      # vdms:
      #   condition: service_started
    environment:
      - CONTROLLER_ENABLE_METRICS
      - CONTROLLER_METRICS_ENDPOINT
      - CONTROLLER_METRICS_EXPORT_INTERVAL_S
      - CONTROLLER_ENABLE_TRACING
      - CONTROLLER_TRACING_ENDPOINT
      - CONTROLLER_TRACING_SAMPLE_RATIO
    command: >
      --restauth /run/secrets/controller.auth
      --brokerauth /run/secrets/controller.auth
      --broker broker.scenescape.intel.com
      --ntp ntpserv
    # mount the trackerconfig file to the container
    configs:
      - source: tracker-config
        target: /home/scenescape/SceneScape/tracker-config.json
    volumes:
      - vol-media:/home/scenescape/SceneScape/media
      - vol-sample-data:/home/scenescape/SceneScape/sample_data
    secrets:
      - source: root-cert
        target: certs/scenescape-ca.pem
      - source: vdms-client-key
        target: certs/scenescape-vdms-c.key
      - source: vdms-client-cert
        target: certs/scenescape-vdms-c.crt
      - django
      - controller.auth
    restart: always
    pids_limit: 1000
```

The content of the `tracker-config.json` file is given below. It is recommended to keep the default values of these parameters unchanged.

```
{
  "max_unreliable_frames": 10,
  "non_measurement_frames_dynamic": 8,
  "non_measurement_frames_static": 16,
  "baseline_frame_rate": 30
}
```

Here is a brief description of each of the config parameters.

- `max_unreliable_frames`: This value defines the number of frames the tracker will wait before publishing a tracked object to the web interface GUI. Expects a positive integer.

- `non_measurement_frames_dynamic`: This value defines the number of frames the tracker will wait before deleting a dead tracked object, given the tracked object was dynamic (i.e. non-zero velocity). Expects a positive integer.

- `non_measurement_frames_static`: This value defines the number of frames the tracker will wait before deleting a dead tracked object, given the tracked object was static (i.e. zero velocity). Expects a positive integer.

- `baseline_frame_rate`: The above three parameters are assumed to be optimized for a camera feed with a frame rate = `baseline_frame_rate`. Expects a positive integer.

### How Time-Based Parameters Work

The time-based tracker parameters enable automatic adjustment of the following three values as a function of the frame rate of the scene camera feeds (instead of using fixed values):

- `max_unreliable_frames`

- `non_measurement_frames_dynamic`

- `non_measurement_frames_static`

For instance, if `max_unreliable_frames` is set to a fixed value, the wait time for publishing reliable tracklets will vary with camera fps. There will be a huge lag between camera feed and the scene update for low fps cameras. When `max_unreliable_frames = 10`, the wait time for 10fps camera = 1 second, compared to the wait time for a 1 fps camera = 10 seconds (too long).

When time-based parameters are enabled, these three parameters will be scaled as a linear function of the camera fps:

```
updated max_unreliable_frames = (default max_unreliable_frames / baseline_frame_rate) × incoming camera frame rate
```

The default values of `max_unreliable_frames` and `baseline_frame_rate` are defined in the `tracker-config.json` file. The same is true for the other two parameters.

Note: If the scene contains multiple cameras publishing at different frame rates, we use the one with the minimum frame rate for the update.

### Note on Changing Camera Frame Rate

Re-launching the Scene Controller is necessary if one or multiple camera frame rates are changed adhoc after the initial deployment. In these cases, first use `docker compose down` to terminate the current deployment and re-launch with the command: `docker compose up`, given the necessary modifications to the video sources are done in the `docker-compose.yml` file.

## Time-Chunking Configuration

This section is intended to guide users and developers on how to enable the use of time-chunking parameters during the deployment of Intel® SceneScape.

### Enabling Time-Chunking

To enable time-chunking, you need to modify the `docker-compose.yml` file to use the `tracker-config-time-chunking.json` file.

In the `configs` section of your `docker-compose.yml`, change the `tracker-config` to point to `controller/config/tracker-config-time-chunking.json`:

```yaml
configs:
  mosquitto-secure:
    file: ./dlstreamer-pipeline-server/mosquitto/mosquitto-secure.conf
  tracker-config:
    # Use this configuration file to run tracking with time-chunking enabled
    file: ./controller/config/tracker-config-time-chunking.json
    # file: ./controller/config/tracker-config.json
  retail-config:
    # Use this configuration file to run decoding and inference on GPU
    # file: ./dlstreamer-pipeline-server/retail-config-gpu.json
    file: ./dlstreamer-pipeline-server/retail-config.json
  queuing-config:
    # Use this configuration file to run decoding and inference on GPU
    # file: ./dlstreamer-pipeline-server/queuing-config-gpu.json
    file: ./dlstreamer-pipeline-server/queuing-config.json
```

The content of the `tracker-config-time-chunking.json` file is given below.

```json
{
  "max_unreliable_frames": 5,
  "non_measurement_frames_dynamic": 4,
  "non_measurement_frames_static": 8,
  "baseline_frame_rate": 30,
  "time_chunking_enabled": true,
  "time_chunking_interval_milliseconds": 66
}
```

Here is a brief description of the time-chunking specific config parameters.

- `time_chunking_enabled`: This value enables or disables the time chunking feature. Set to `true` to enable.
- `time_chunking_interval_milliseconds`: This value defines the interval in milliseconds at which the tracker processes data in chunks.
