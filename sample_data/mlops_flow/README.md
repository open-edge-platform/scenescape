# MLOps Flow Demo

> **⚠️ Experimental feature.** The MLOps Flow is experimental and supported
> only with Docker Compose. See
> [How to Use the MLOps Flow](../../docs/user-guide/other-topics/how-to-use-mlops-flow.md)
> for the feature reference, and
> [ADR 12](../../docs/adr/0012-mlops-integration-reuse.md) for its background.

This demo shows the Scenescape MLOps Flow:

1. Author camera pipelines in ViPPET (Visual Pipeline and Platform Evaluation Tool).
2. Import them into Scenescape with **Sync with ViPPET** on the **Pipelines** page.
3. Select a pipeline on a camera. Scenescape starts it on DL Streamer Pipeline
   Server 2.0 (DLSPS) with automatic restarts enabled, and the detections appear in
   the Queuing scene. Changing or clearing the selection stops the running instance.

ViPPET runs outside Scenescape. This demo deploys Scenescape configured to use
it, a DLSPS 2.0 instance that runs the camera pipelines, and the Queuing sample
camera streams.

## Prerequisites

- ViPPET and its `dlstreamer-pipeline-server` container running on the same
  host. In the ViPPET directory run:

  ```bash
  make build run
  ```

  The demo starts a separate DLSPS 2.0 for Scenescape; ViPPET's own pipeline
  server is also required for the proxy configuration step.

- Scenescape images built (`make build-core`) and the super user password set:

  ```bash
  export SUPASS=<password>
  ```

## Start the Demo

From the repository root:

```bash
make demo-mlops-flow
```

The target checks that ViPPET's Docker network and `/models` mount exist (it
warns if the `vippet` container is not running on that network yet; Scenescape
reaches it by name once it starts). It detects whether `/models` is a named
Docker volume or a host-directory bind mount and shares the same source with
DLSPS read-only at `/models`, then:

- adds `mediaserver` to the proxy-bypass lists of ViPPET and its DLSPS, preserving
  their existing exclusions, using
  [compose.vippet-proxy-override.yml](./compose.vippet-proxy-override.yml).
  The target discovers ViPPET's existing Compose project and files from its
  container labels; that project's directory must be accessible on this host.
  It keeps the running containers' images (`DOCKER_TAG`, `DLSPS2_IMAGE`) and
  proxy settings, and loads the project's `.env`; it never builds or pulls
  images, so prebuilt-only (`make run-prebuilt`) setups are not changed.
  If the exclusion is missing, it recreates those two containers, interrupting
  any running ViPPET pipelines. It reloads the running ViPPET UI proxy so it
  resolves the current backend address. No ViPPET source files are changed;
- deploys Scenescape with
  [compose.scenescape-override.yml](./compose.scenescape-override.yml): the
  MLOps Flow flag (`ENABLE_MLOPS_FLOW=true`), `VIPPET_URL`,
  `DLSPS_URL`, the `web`, `broker` and `ntpserv` services joined to
  ViPPET's network, and the broker published on host loopback port `1883` (TLS;
  set `BROKER_PORT` to change it). The broker allows anonymous clients, so TLS
  alone does not authenticate them;
- starts DLSPS 2.0 with [compose.dlsps2.yml](./compose.dlsps2.yml) as container
  `dlsps2-pipeline-server` on the Scenescape network
  (`http://dlsps.scenescape.intel.com:8080`, available to Manager over Docker networking
  only). The host API port is not published: ViPPET's DLSPS and this Scenescape DLSPS are
  separate containers, so both can listen on internal port `8080` without a conflict.
  It loads the Scenescape GStreamer elements
  (`sscape_timestamp_capture`, `sscape_post_inference_data_publish`) from
  `dlstreamer-pipeline-server/user_scripts/gstplugins`, trusts the Scenescape
  root CA (the MQTT broker only accepts TLS), and mounts ViPPET's model source
  read-only at `/models`, using the same named Docker volume or host directory
  that ViPPET mounts there. ViPPET's model-download service populates this
  source, so Scenescape does not download or copy a second model set. The
  external volume or host directory is not removed when the demo stops;
- starts the Queuing video loopers with
  [compose.queuing-cams-override.yml](./compose.queuing-cams-override.yml) as
  `rtsp://mediaserver:8554/queuing-cam1` and `rtsp://mediaserver:8554/queuing-cam2`,
  reachable from ViPPET's network (and from the host on port `18554`);
- uploads the **Queuing** scene with cameras `atag-qcam1` and `atag-qcam2`.

The defaults can be changed with these variables:

| Variable               | Default                                                                  |
| ---------------------- | ------------------------------------------------------------------------ |
| `VIPPET_NETWORK`       | `visual-pipeline-and-platform-evaluation-tool_default`                   |
| `VIPPET_MODELS_DIR`    | Detected from a bind mount at `/models`; setting it forces bind mounting |
| `VIPPET_MODELS_VOLUME` | Detected from a named volume mounted at `/models`                        |
| `VIPPET_URL`           | `http://vippet:7860/api/v1`                                              |
| `DLSPS_URL`            | `http://dlsps.scenescape.intel.com:8080`                                 |
| `DLSPS2_IMAGE`         | `intel/dlstreamer-pipeline-server:2026.3.0-ubuntu24-2.0-rc1`             |
| `MLOPS_FLOW_RTSP_PORT` | `18554` (ViPPET's own media server already uses `8554`)                  |
| `DEMO_REBUILD_IMAGES`  | `true`; set to `false` to skip rebuilding images                         |

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

The pipelines consume the RTSP streams directly from the demo media server.

Manager sets `cameraid` to the ID of the camera the pipeline is assigned to
when it starts the pipeline, replacing the value in the string. The MQTT broker
defaults to `broker.scenescape.intel.com:1883`, the Scenescape broker, which the
demo DLSPS reaches on the Scenescape network.

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
warning is shown; save the camera again to retry. The camera page shows the live
DLSPS state of the pipeline (and the DLSPS error, if any) beneath the
**Pipeline** selector.

## Without the Feature Flag

Outside this demo the MLOps Flow is disabled by default. The **Sync with
ViPPET**, **+ New Pipeline**, edit and delete controls and the camera
**Pipeline** selector are shown greyed out; hovering them explains how to
enable the MLOps Flow. Enable it with one of:

- the `--enable-mlops-flow` option of the Manager `webserver` command,
- `ENABLE_MLOPS_FLOW=true` in the environment of the `web` service.

## Troubleshooting

- `make demo-mlops-flow` reports a missing network or models mount:
  make sure ViPPET's Docker network exists and `/models` is mounted in its
  `vippet` container. The target detects named volumes and bind mounts
  automatically. Override discovery with `VIPPET_NETWORK`,
  `VIPPET_MODELS_VOLUME`, or an absolute `VIPPET_MODELS_DIR` path.
- If a ViPPET prerequisite container is stopped, start it with
  `docker start <container-name>` and retry. If it fails to start, inspect
  `docker logs <container-name>`.
- If ViPPET is restarted while the demo is running, restart the demo with
  `make demo-mlops-flow-close` followed by `make demo-mlops-flow` so its
  containers rejoin ViPPET's network.
- If ViPPET was recreated without the demo's proxy override, run
  `make configure-mlops-vippet` to reapply it without redeploying Scenescape.
- If the DLSPS container restarts, the camera pipelines are not restarted.
  Save each camera again to start its pipeline.
- **Sync with ViPPET** restarts the pipeline of every camera whose pipeline
  string changed.

This override exposes the Scenescape broker and NTP server to all containers on
ViPPET's network, and the broker to the host network. Use it for demos only.

To watch the camera detections from the host:

```bash
mosquitto_sub -h localhost -p 1883 --cafile manager/secrets/certs/scenescape-ca.pem \
  --insecure -t 'scenescape/data/camera/#' -v
```

`--insecure` skips the host name check, because the broker certificate is
issued for `broker.scenescape.intel.com`.

## Stop the Demo

```bash
make demo-mlops-flow-close
```

This stops the camera pipelines that Scenescape started, then stops DLSPS, the
Queuing camera streams and Scenescape and removes the Scenescape volumes.
ViPPET keeps running. `make demo-close` does the same for this demo.
