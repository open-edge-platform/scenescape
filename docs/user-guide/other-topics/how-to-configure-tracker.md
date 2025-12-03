### Tracker Configuration

This section is intended to guide users and developers on how to enable the use of time-based parameters during the deployment of Intel® SceneScape.

- **How to enable time-based parameters for tracker**:

A `tracker-config.json` file is pre-stored in the `controller` directory. The only change required is to mount this file to the docker container in the `scene` service. The `scene` service in `docker-compose.yml` file should look as follows. Please note the `volumes` section.

```
scene:
    image: scenescape
    init: true
    networks:
      scenescape:
    depends_on:
     - broker
     - web
     - ntpserv
    # - vdms
    command: controller --broker broker.scenescape.intel.com --ntp ntpserv
    volumes:
     - vol-media:/home/scenescape/SceneScape/media
    configs:
     - source: tracker-config
       target: /home/scenescape/SceneScape/tracker-config.json
    secrets:
     - certs
     - django
     - controller.auth
    restart: always
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

- **How do the time-based parameters work**:

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

- **Note on changing camera frame rate**:

Re-launching the Scene Controller is necessary if one or multiple camera frame rates are changed adhoc after the initial deployment. In these cases, first use `docker compose down` to terminate the current deployment and re-launch with the command: `docker compose up`, given the necessary modifications to the video sources are done in the `docker-compose.yml` file.
