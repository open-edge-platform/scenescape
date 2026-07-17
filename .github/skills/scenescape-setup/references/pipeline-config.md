# DLStreamer Pipeline Config

Bootstrap sparse-checkouts `model-proc-files/`, `mosquitto/`, and `user_scripts/` from the
upstream SceneScape repo into `<deploy_dir>/dlstreamer-pipeline-server/`.

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
| `parameters`         | MQTT parameter schema (same for every camera)         |
| `payload.parameters` | Runtime defaults below with `{camera_id}` substituted |

### GStreamer pipeline

```
rtspsrc location={rtsp_url} add-reference-timestamp-meta=true latency=200
! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! video/x-raw,format=BGR
! gvapython class=PostDecodeTimestampCapture function=processFrame
  module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync
! gvadetect
  model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml
  model-proc=/home/pipeline-server/model-proc-files/person-detection-retail-0013.json
! gvametaconvert add-tensor-data=true name=metaconvert
! gvapython class=PostInferenceDataPublish function=processFrame
  module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher
! gvametapublish name=destination ! appsink sync=true
```

### Payload defaults

```json
{
  "ntp_config": { "ntpServer": "ntpserv" },
  "frame_ntp_config": { "useFrameNtpTimestamp": false },
  "camera_config": {
    "cameraid": "{camera_id}",
    "metadatagenpolicy": "detectionPolicy",
    "detection_labels": ["person"]
  }
}
```

`ntpServer: ntpserv` matches the `ntpserv` service in `docker-compose.yml`.

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
