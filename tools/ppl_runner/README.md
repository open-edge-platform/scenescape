# Pipeline runner

This folder contains a set of scripts along with configuration files for testing and development of the `PipelineGenerator` and `PipelineConfigGenerator` Python classes that are used in production for dynamic pipeline configuration.

## Prerequisites

The minimum required steps are:

- Manager service Docker image is built. This can be done by running the command: `make manager` in the Intel® SceneScape repository root folder.
- Secrets are generated. This can be done by running the command: `make init-secrets` in the Intel® SceneScape repository root folder.
- Models are installed into a docker volume. This can be done by running the command: `make install-models` in the Intel® SceneScape repository root folder. Refer to the [model installer documentation](../../model_installer/src/README.md) for more details on model configuration.
- Volume with sample video files is created with `make init-sample-data`.

Building Intel® SceneScape will perform all the above steps and additionally build all images.

The commands below will perform all the above steps and additionally build all images (adjust environment variables if needed):

```
make install-models PRECISIONS=FP32
make init-sample-data
```

## Basic usage

### Starting the pipeline

To start the pipeline with **detection metadata in SceneScape format** use:

```
./start-dlsps-pipeline.sh <CAMERA_SETTINGS_FILE>
```

Example command: `./start-dlsps-pipeline.sh sample_camera_configs/camera_settings_person_reid.json`

To start the pipeline with **detection metadata in DL Streamer format** use:

```
DUMP_DLS_METADATA=true ./start-dlsps-pipeline.sh <CAMERA_SETTINGS_FILE>
```

Example command: `DUMP_DLS_METADATA=true ./start-dlsps-pipeline.sh sample_camera_configs/camera_settings_agegender.json`

### Stopping the pipeline

To stop the pipeline regardless of the metadata format, use:

```
./stop-dlsps-pipeline.sh
```

## Configuration

- Run `./start-dlsps-pipeline.sh` without arguments for detailed information on the script configurability.
- Edit the parameters in `sample_camera_configs/*.json` to provide input parameters for pipeline generation that simulate user input via the camera calibration UI page.
- If custom models downloaded into the docker models volume need to be used, then provide the updated model config file in `/models/model_configs/` in the models volume and update the camera settings accordingly.

The DLSPS configuration file generated along with the pipeline string in the `gst-launch-1.0` format can be viewed in the generated `dlsps-config.json` file.

## Inspecting the detection metadata

### Pipeline using SceneScape metadata format

The detection metadata published by the pipeline can be monitored with an MQTT client, e.g., MQTT Explorer. Run the MQTT client on port 1884 (this port was chosen to avoid conflicts with Intel® SceneScape deployment that can be run at the same time) and watch for messages under the `scenescape/data/camera/<camera-id>` topic.

Additionally, an `mqtt_recorder` service is run by docker compose which dumps the detections within an arbitrary time interval to a file with default location `tools/ppl_runner/output/scenescape_metadata.jsonl`. Detections from a single frame are described by a single line in this file.

### Pipeline using DL Streamer metadata format

If the pipeline is run with DL Streamer metadata dumps, the detections are dumped to a file with default location `tools/ppl_runner/output/dls_metadata.jsonl`. Detections from a single frame are described by a single line in this file.

## Measuring pipeline latency

Create the output folder and define the following variables in the shell:

```
mkdir -p /tmp/latency_tracer
export GST_DEBUG=GST_TRACER:7
export GST_TRACERS="latency_tracer(flags=element+pipeline)"
export GST_DEBUG_FILE=/tmp/trace.log
```

> **Note**: For guidance on GStreamer debug levels and general debugging of GStreamer applications, see the [Troubleshooting](#troubleshooting) section.

Enable the following setting in the [Docker Compose file](./docker-compose-ppl.yaml):

```
services:
  video-pipeline:
    volumes:
      - "/tmp/latency_tracer:/tmp"
```

Start the pipeline using the `rtsp` profile and wait a couple of minutes until the pipeline stabilizes and enough tracing data is gathered. An RTSP source is required for reliable latency results, as file video sources introduce frame buffering that makes the measurements unreliable.

Use the following command to check how many data points are available; at least 1500 are recommended before proceeding.

```
grep latency_tracer_pipeline /tmp/latency_tracer/trace.log | wc -l
```

Once the measurement data is available, the average and standard deviation of pipeline latency can be calculated with the command:

```
grep latency_tracer_pipeline /tmp/latency_tracer/trace.log | grep -oP 'frame_latency=\(double\)\K[0-9]+\.[0-9]+' | tail -n 1000 | awk '{sum+=$1; sumsq+=$1*$1; count++} END {avg=sum/count; std=sqrt(sumsq/count - avg*avg); printf "Count: %d\nAverage: %.6f\nStd Dev: %.6f\n", count, avg, std}'
```

Please refer to [DL Streamer documentation](https://docs.openedgeplatform.intel.com/2026.0/edge-ai-libraries/dlstreamer/dev_guide/latency_tracer.html) and [DL Streamer Pipeline Server documentation](https://docs.openedgeplatform.intel.com/2026.0/edge-ai-libraries/dlstreamer-pipeline-server/advanced-guide/detailed_usage/how-to-advanced/performance/processing-latency.html) for more details on interpreting the latency tracer output.

### Disabling latency tracer

To disable the latency tracer, unset the environment variables `GST_DEBUG`, `GST_TRACERS`, and `GST_DEBUG_FILE` and comment out the volume mount in the [Docker Compose file](./docker-compose-ppl.yaml):

```
services:
  video-pipeline:
    volumes:
    #  - "/tmp/latency_tracer:/tmp"
```

## Troubleshooting

For information on GStreamer debug levels and debugging GStreamer applications, refer to the [GStreamer documentation](https://gstreamer.freedesktop.org/documentation/gstreamer/running.html?gi-language=python).

It is assumed that the docker models volume is created with the default name `scenescape_vol-models`. It may be different if the user explicitly sets the `COMPOSE_PROJECT_NAME` variable. If the volume is not found, please check which name it was created with.
