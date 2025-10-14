# Pipeline runner

This folder contains a simple wrapper `ppl_runner.py` alongside with configuration files for testing `PipelineGenerator` and `PipelineConfigGenerator` Python classes that are used in production for dynamic pipeline configuration.

## Prerequisites

The minimum required steps are:

- Secrets are generated. This can be done by running the command: `make init-secrets` in the Scenescape repository root folder.
- Models are installed into a docker volume. This can be done by running the command: `make install-models` in the Scenescape repository root folder.
- Sample video files are created with `make init-sample-data`.
- Python dependencies from `requirements.txt` are installed.

Building Scenescape with `make build` will perform the steps related to build (not the Python dependencies).

## Basic usage

The tool can be run by command `python ppl_runner.py` in the default configuration. It executes DLStreamer-Pipeline-Server and MQTT broker containers using docker compose under the hood.

Stop the runner with the command `docker compose -f docker-compose-ppl.yaml down`.

## Configuration

- Run `python ppl_runner.py --help` for detailed information on the runner configurability.
- Edit the parameters in `sample_camera_settings.json` to simulate user input via camera calibration UI page.
- Edit the parameters in `sample_model_config.json` for finer model configuration.
- If additional models downloaded into the docker models volume need to be used, then update the model chain and model config file in the camera settings accordingly

## Inspecting the output

The detections metadata published by the pipeline can be watched with MQTT client, e.g. MQTT Explorer. Run MQTT client on the port 1884 (such port was chosen to avoid conflict with SceneScape deployment that can be run at the same time) and watch for messages under `scenescape/data/camera/<camera-id>` topic.

The DLSPS configuration file generated along with the pipeine string in the `gst-launch-1.0` format string can be viewed in the `dlsps-config.json` file.

## Troubleshooting

It is assumed that the docker models volume is created with a default name `scenescape_vol-models`. It may be different if the user explicitly sets the `COMPOSE_PROJECT_NAME` variable. In case the volume is not found, please check which name it is created with.
