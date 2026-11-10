# ViPPET and DL Streamer Pipeline Server 2.0 Demo

This demo shows the Scenescape MLOps flow:

1. Author camera pipelines in ViPPET (Visual Pipeline and Platform Evaluation Tool).
2. Import them into Scenescape with **Sync with ViPPET** on the **Pipelines** page.
3. Select a pipeline on a camera. Scenescape starts it on DL Streamer Pipeline
   Server 2.0 (DLSPS) with automatic restarts enabled, and the detections appear in
   the Queuing scene. Changing or clearing the selection stops the running instance.

ViPPET and DLSPS run outside Scenescape. This demo deploys Scenescape configured
to use them, plus the Queuing sample camera streams.

## Prerequisites

- ViPPET running on the same host with DL Streamer Pipeline Server 2.0 enabled.
  In the ViPPET directory run:

  ```bash
  make build run DLSPS2=1
  ```

  DLSPS must provide the Scenescape GStreamer elements
  (`sscape_timestamp_capture`, `sscape_post_inference_data_publish`) and trust
  the Scenescape root CA (`manager/secrets/certs/scenescape-ca.pem` of this
  repository, read from `/run/secrets/certs/scenescape-ca.pem` or the path in
  `ROOT_CA`), because the Scenescape MQTT broker only accepts TLS connections.

- Scenescape images built (`make build-core`) and the super user password set:

  ```bash
  export SUPASS=<password>
  ```

## Start the Demo

From the repository root:

```bash
make demo-vippet-dlsps2
```

The target checks that ViPPET's Docker network exists (and warns if the
`vippet` or `dlstreamer-pipeline-server` container is not running yet; Scenescape
reaches them by name once they start), then:

- deploys Scenescape with
  [compose.scenescape-override.yml](./compose.scenescape-override.yml): the
  pipeline integration flag (`ENABLE_MLOPS_FLOW=true`), `VIPPET_URL`,
  `DLSPS_URL`, and the `web`, `broker` and `ntpserv` services joined to
  ViPPET's network;
- starts the Queuing video loopers with
  [compose.queuing-cams-override.yml](./compose.queuing-cams-override.yml) as
  `rtsp://mediaserver:8554/queuing-cam1` and `rtsp://mediaserver:8554/queuing-cam2`,
  reachable from ViPPET's network (and from the host on port `18554`);
- uploads the **Queuing** scene with cameras `atag-qcam1` and `atag-qcam2`.

The defaults can be changed with these variables:

| Variable                  | Default                                                 |
| ------------------------- | ------------------------------------------------------- |
| `VIPPET_NETWORK`          | `visual-pipeline-and-platform-evaluation-tool_default`  |
| `VIPPET_URL`              | `http://vippet:7860/api/v1`                             |
| `DLSPS_URL`               | `http://dlstreamer-pipeline-server:8080`                |
| `VIPPET_DLSPS2_RTSP_PORT` | `18554` (ViPPET's own media server already uses `8554`) |
| `DEMO_REBUILD_IMAGES`     | `true`; set to `false` to skip rebuilding images        |

## Create the Camera Pipelines in ViPPET

1. Open the ViPPET UI (`http://<host>/`). On the **Models** page, install an
   object detection model that detects people, for example **YOLO 11n 640x640**.
2. Create a new pipeline and open **Import pipeline > Import GST Description**.
   Paste the description for the first camera:

   ```text
   rtspsrc location=rtsp://mediaserver:8554/queuing-cam1 add-reference-timestamp-meta=true latency=200 ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! video/x-raw,format=BGR ! sscape_timestamp_capture name=timesync ntp-server=ntpserv ! gvadetect model="" device=CPU ! queue ! gvametaconvert add-tensor-data=true name=metaconvert ! sscape_post_inference_data_publish name=datapublisher cameraid=atag-qcam1 detection-labels=person ! gvametapublish name=destination method=file file-path=/dev/null ! appsink sync=true
   ```

3. Select the installed model in the `gvadetect` node, add the tag `Scenescape`
   and save the pipeline as `Queuing qcam1`.
4. Repeat for the second camera with `queuing-cam2` and `cameraid=atag-qcam2`,
   saved as `Queuing qcam2` with the same tag.

`cameraid` must match the Scenescape camera ID, so detections are attributed to
the right camera. The MQTT broker defaults to `broker.scenescape.intel.com:1883`,
which resolves to the Scenescape broker on ViPPET's network.

## Run the Pipelines from Scenescape

1. Log in to Scenescape (`https://<host>/`) as `admin` with `SUPASS`.
2. Open **Pipelines**, type `Scenescape` in the tag filter next to **Sync with
   ViPPET** (match **Any**) and click **Sync with ViPPET**. Only ViPPET pipelines
   tagged `Scenescape` (case-insensitive) are imported; leave the filter empty to
   import all of them. Each ViPPET variant is stored as
   `<pipeline name> (<variant name>)`, for example `Queuing qcam1 (CPU)`.
   Variants whose model is not installed in ViPPET are skipped and listed in the
   sync summary.
3. Open the **Queuing** scene, manage camera `atag-qcam1`, select
   `Queuing qcam1 (CPU)` in **Pipeline** and save. The **DLSPS instance UUID**
   below the selector shows the started instance and the camera's detections
   appear in the scene. Do the same for `atag-qcam2`.
4. Clear the selection and save to stop the pipeline, or select another one to
   replace it.

If DLSPS is unreachable or rejects the pipeline, the camera is still saved and a
warning is shown; save the camera again to retry.

## Without the Feature Flag

Outside this demo the integration is disabled by default. The **Sync with
ViPPET**, **+ New Pipeline**, edit and delete controls and the camera
**Pipeline** selector are shown greyed out; hovering them explains how to
enable the integration. Enable it with one of:

- the `--enable-mlops-flow` option of the Manager `webserver` command,
- `ENABLE_MLOPS_FLOW=true` in the environment of the `web` service,
- `web.enableMlopsFlow=true` in the Helm chart.

## Troubleshooting

- `make demo-vippet-dlsps2` reports a missing network: start ViPPET with
  `make build run DLSPS2=1`, or set `VIPPET_NETWORK` to the network ViPPET runs
  on (`docker network ls`).
- Camera saves warn that DLSPS failed: check that `dlstreamer-pipeline-server`
  runs on ViPPET's network (`docker ps`).
- A pipeline starts but no detections appear: check the DLSPS logs with
  `docker logs dlstreamer-pipeline-server`.
  - RTSP errors behind an HTTP proxy: add `mediaserver` to `no_proxy` before
    starting ViPPET.
  - MQTT connection errors: DLSPS does not trust the Scenescape root CA (see
    [Prerequisites](#prerequisites)).
- ViPPET was restarted while the demo was running: restart the demo
  (`make demo-vippet-dlsps2-close`, then `make demo-vippet-dlsps2`) so the
  Scenescape containers rejoin ViPPET's network.

This override exposes the Scenescape broker and NTP server to all containers on
ViPPET's network. Use it for demos only.

## Stop the Demo

```bash
make demo-vippet-dlsps2-close
```

This stops the camera pipelines that Scenescape started on DLSPS, then stops the
Queuing camera streams and Scenescape and removes the Scenescape volumes. ViPPET
and DLSPS keep running.
