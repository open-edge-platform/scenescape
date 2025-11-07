#!/bin/bash

CAMERA_SETTINGS_FILE=$1
DLSPS_CONFIG_FILE="./dlsps_config.json"
DOCKER_IMAGE="scenescape-manager:2025.2-rc1"

docker run --rm \
       -e PYTHONPATH=/home/scenescape/SceneScape/ \
       --entrypoint python \
       -v ./:/workspace \
       -v scenescape_vol-models:/models \
       -w /workspace \
       $DOCKER_IMAGE \
       /workspace/cam-settings-2-dlsps-config.py \
       --camera-settings /workspace/$CAMERA_SETTINGS_FILE \
       --config_folder /models/model_configs \
       --output_path $DLSPS_CONFIG_FILE

append_var_to_env() {
    local var_name="$1"
    local var_value="${!var_name}"
    echo "${var_name}=${var_value}" >> .env
}

append_var_to_env DLSPS_CONFIG_FILE

# TODO: create the rest of variables in .env
# TODO: run docker compose
# TODO: add option to run debug pipeline with DLS
