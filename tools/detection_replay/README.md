<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Detection Replay

`detection_replay.py` stands in for detection-only DL Streamer Pipeline Server (DLSPS) camera
pipelines when no model can detect the objects in the video, for example in synthetic scenes. It
plays video files and publishes detections recorded for each frame instead of running inference.
SceneScape receives the same MQTT messages as from a DLSPS pipeline:

- detections on `scenescape/data/camera/<camera_id>`;
- Live View frames with the detection boxes drawn on `scenescape/image/camera/<camera_id>`, and
  calibration frames on `scenescape/image/calibration/camera/<camera_id>`, when requested on
  `scenescape/cmd/camera/<camera_id>`.

## How it works

The tool runs one GStreamer pipeline with a branch per camera. Each branch uses the SceneScape
DLSPS elements from
[`dlstreamer-pipeline-server/user_scripts/gstplugins`](../../dlstreamer-pipeline-server/user_scripts/gstplugins),
with `sscape_detection_replay` (from [`gstplugins`](gstplugins)) in place of `gvadetect`:

```text
filesrc ! decodebin ! videoconvert ! identity sync=true ! sscape_timestamp_capture
  ! sscape_detection_replay ! gvametaconvert ! sscape_post_inference_data_publish ! fakesink
```

- `identity sync=true` releases each frame at its presentation time, like a live camera, and
  `sscape_timestamp_capture` timestamps it with the current (NTP-corrected) time.
- `sscape_detection_replay` attaches the frame's recorded detections as GVA regions of interest.
  Object IDs are numbered 1..n in each frame, as in a pipeline without `gvatrack`.
- All branches share the pipeline clock, so frame N of every camera is published at the same time.
  The videos loop together until the tool is stopped. The longest video sets the loop length.

## Detection metadata

One JSON Lines file per camera, with one SceneScape camera message per line. Only `timestamp` and
each object's `category`, `confidence` and `bounding_box_px` are used:

```json
{
  "timestamp": "2026-11-13T09:20:12.270Z",
  "objects": {
    "person": [
      {
        "category": "person",
        "confidence": 1.0,
        "bounding_box_px": { "x": 120, "y": 235, "width": 78, "height": 227 }
      }
    ]
  }
}
```

`--sync` selects the record for a video frame:

- `time` (default): the first record whose time since the first record is at or after the
  frame's stream time. Use it when the video was resampled to a constant frame rate from a
  variable-rate recording, which drops or repeats source frames.
- `frame`: the record at the frame's position in the file. Decoded frames are counted, restarting on each loop, whatever their timestamps. Use it when the file has exactly one record per frame.

Frames after the last record are published without detections.

## Usage

Run the tool in the DLSPS image, which provides GStreamer, the GVA elements and gst-python.
Mount both plugin directories as `<dir>/python` and list them in `ADDITIONAL_GST_PLUGIN_PATH`, as
DLSPS does:

```bash
docker run --rm --network scenescape_scenescape \
  -e ADDITIONAL_GST_PLUGIN_PATH=/home/sscape:/home/detection_replay \
  -v "$PWD/dlstreamer-pipeline-server/user_scripts/gstplugins:/home/sscape/python:ro" \
  -v "$PWD/tools/detection_replay/gstplugins:/home/detection_replay/python:ro" \
  -v "$PWD/tools/detection_replay/detection_replay.py:/home/detection_replay/detection_replay.py:ro" \
  -v "$PWD/manager/secrets/certs/scenescape-ca.pem:/run/secrets/certs/scenescape-ca.pem:ro" \
  -v "$PWD/sample_data/spp_demo/Stairs-synthetic:/workspace:ro" \
  --entrypoint python3 \
  intel/dlstreamer-pipeline-server:2026.3.0-20261027-weekly-ubuntu24 \
  /home/detection_replay/detection_replay.py \
  --camera cam1_front_left /workspace/video/cam1_front_left.mp4 /workspace/metadata/cam1_front_left.json \
  --camera cam2_back_right /workspace/video/cam2_back_right.mp4 /workspace/metadata/cam2_back_right.json
```

| Option                   | Default                                       | Description                                                                                           |
| ------------------------ | --------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `--camera ID VIDEO META` | required                                      | Camera ID, video file and detection metadata. Repeat per camera.                                      |
| `--sync`                 | `time`                                        | `time` or `frame` (see above).                                                                        |
| `--detection-labels`     | all                                           | Comma-separated categories to publish.                                                                |
| `--ntp-server`           | `ntpserv`                                     | NTP server for frame timestamps; empty uses the system clock.                                         |
| `--mqtt-host`            | `$MQTT_HOST` or `broker.scenescape.intel.com` | MQTT broker. TLS uses `/run/secrets/certs/scenescape-ca.pem` when present (overridable by `ROOT_CA`). |
| `--mqtt-port`            | `$MQTT_PORT` or `1883`                        | MQTT broker port.                                                                                     |
| `--no-loop`              | loop                                          | Exit at the end of the videos.                                                                        |
| `--print-pipeline`       |                                               | Print the GStreamer pipeline and exit.                                                                |

The [SPP demo](../../sample_data/spp_demo/README.md) uses the tool for its `Stairs-synthetic` scene
([`compose.stairs-synthetic-video.yml`](../../sample_data/spp_demo/compose.stairs-synthetic-video.yml)).

Unit tests: `pytest tests/sscape_tests/detection_replay`.
