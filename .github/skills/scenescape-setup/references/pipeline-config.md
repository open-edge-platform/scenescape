<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# DLStreamer Pipeline Config

Bootstrap sparse-checkouts `model-proc-files/`, `mosquitto/`, and `user_scripts/` from the
upstream SceneScape repo into `<deploy_dir>/dlstreamer-pipeline-server/`.

`user_scripts/gstplugins/` holds the native GStreamer Python plugins that replace the former
`gvapython` + `sscape_adapter.py` path:

| Plugin file                                      | Element name                         | Role                                      |
| ------------------------------------------------ | ------------------------------------ | ----------------------------------------- |
| `sscape_post_decode_timestamp_capture.py`        | `sscape_timestamp_capture`           | NTP / frame timestamp capture (`timesync`) |
| `sscape_post_inference_data_publish.py`          | `sscape_post_inference_data_publish` | MQTT metadata publish (`datapublisher`)    |
| `sscape_policies.py` / `sscape_3d_detector.py`   | (imported by datapublisher)          | Metadata generation policies               |

Compose mounts those files into
`/opt/intel/dlstreamer/gstreamer/lib/gstreamer-1.0/python/` so GStreamer can load them as
elements — see [docker-compose-template.md](./docker-compose-template.md).

`adapt_pipeline_config.py` **generates** `<deploy_dir>/dlstreamer-pipeline-server/pipeline-config.json`
from `deploy-inputs.json` using the specification below. No upstream `queuing-config.json` is
fetched or required.

## Output

Top-level shape:

```json
{
  "config": {
    "logging": { "C_LOG_LEVEL": "INFO", "PY_LOG_LEVEL": "INFO" },
    "pipelines": [
      /* one entry per camera */
    ]
  }
}
```

## Per-camera pipeline entry

For each `(camera_id, rtsp_url)` in `deploy-inputs.json`:

| Field                | Value                                                 |
| -------------------- | ----------------------------------------------------- |
| `name`               | User's `camera_id`                                    |
| `source`             | `gstreamer`                                           |
| `auto_start`         | `true`                                                |
| `pipeline`           | GStreamer string below with `{rtsp_url}` substituted  |
| `parameters`         | Element property schema (same for every camera)       |
| `payload.parameters` | Runtime defaults below with `{camera_id}` substituted |

### GStreamer pipeline

```
rtspsrc location={rtsp_url} add-reference-timestamp-meta=true latency=200
! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! video/x-raw,format=BGR
! sscape_timestamp_capture name=timesync ntp-server=ntpserv
! gvadetect
  model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml
  model-proc=/home/pipeline-server/model-proc-files/person-detection-retail-0013.json
! gvametaconvert add-tensor-data=true name=metaconvert
! sscape_post_inference_data_publish name=datapublisher
! gvametapublish name=destination method=file file-path=/dev/null ! appsink sync=true
```

### Payload defaults

Parameters map directly to native GST element properties (no nested `kwarg` JSON blobs):

```json
{
  "ntp_config": "ntpserv",
  "frame_ntp_config": false,
  "cameraid": "{camera_id}",
  "metadatagenpolicy": "detectionPolicy",
  "detection_labels": "person"
}
```

| Payload key          | Element        | GST property                 | Notes                                      |
| -------------------- | -------------- | ---------------------------- | ------------------------------------------ |
| `ntp_config`         | `timesync`     | `ntp-server`                 | string; matches `ntpserv` compose service  |
| `frame_ntp_config`   | `timesync`     | `use-frame-ntp-timestamp`    | boolean                                    |
| `cameraid`           | `datapublisher`| `cameraid`                   | string                                     |
| `metadatagenpolicy`  | `datapublisher`| `metadatagenpolicy`          | string                                     |
| `publish_image`      | `datapublisher`| `publish-image`              | boolean (optional; default false)          |
| `detection_labels`   | `datapublisher`| `detection-labels`           | comma-separated string, not a JSON array   |

## Manual re-run

```bash
python3 <skill-dir>/scripts/adapt_pipeline_config.py \
  --deploy-dir <deploy_dir> \
  --from-deploy-inputs
```

## Notes

- Model: `person-detection-retail-0013` via `download_detection_models.sh`
- External RTSP sources must be reachable from the SceneScape Docker network
- GPU/WSL2 segfaults with dual pipelines: see repo `queuing-config-gpu.json` / sample compose
- Local video files (folder or explicit list) instead of live RTSP cameras: see
  [video-file-input.md](./video-file-input.md) — they are looped through an internal RTSP
  re-streamer, so this file's spec applies unchanged once `deploy-inputs.json` is written.
- Canonical upstream examples: `dlstreamer-pipeline-server/queuing-config.json` and
  `docs/user-guide/other-topics/how-to-configure-dlstreamer-video-pipeline.md`
- **Planned**: `download_detection_models.sh` will be replaced by the Model Download Microservice;
  see `.github/plans/plan-modelDownloaderMigration.prompt.md`.
