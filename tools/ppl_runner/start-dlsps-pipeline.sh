#!/bin/bash

CAMERA_SETTINGS_FILE=$1
PROFILE=$2

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    echo "Usage: $0 <CAMERA_SETTINGS_FILE> [PROFILE]"
    echo "Supported profiles: [ rtsp ]"
    exit 1
fi

DLSPS_CONFIG_FILE="./dlsps_config.json"
PPL_GENERATOR_IMAGE="scenescape-manager:2025.2-rc1"
VOLUME_PREFIX=scenescape
ROOT_DIR=$(git rev-parse --show-toplevel)
SECRETS_DIR=${ROOT_DIR}/manager/secrets
OUTPUT_DIR=./output
GID=$(id -g)

convert_cam_settings_to_dlsps_config() {
    local ppl_generator_image="$1"
    local camera_settings_file="$2"
    local dlsps_config_file="$3"

    docker run --rm \
        -e PYTHONPATH=/home/scenescape/SceneScape/ \
        --entrypoint python \
        -v ./:/workspace \
        -v ${VOLUME_PREFIX}_vol-models:/models \
        -w /workspace \
        "$ppl_generator_image" \
        /workspace/cam-settings-2-dlsps-config.py \
        --camera-settings /workspace/"$camera_settings_file" \
        --config_folder /models/model_configs \
        --output_path "$dlsps_config_file"
}

convert_cam_settings_to_dlsps_config "$PPL_GENERATOR_IMAGE" "$CAMERA_SETTINGS_FILE" "$DLSPS_CONFIG_FILE"

append_var_to_env() {
    local var_name="$1"
    local var_value="${!var_name}"
    echo "${var_name}=${var_value}" >> .env
}

echo '' > .env
append_var_to_env DLSPS_CONFIG_FILE
append_var_to_env ROOT_DIR
append_var_to_env SECRETS_DIR
append_var_to_env OUTPUT_DIR
append_var_to_env UID
append_var_to_env GID
append_var_to_env PROFILE

if [ -n "$PROFILE" ]; then
    ADDITIONAL_DOCKER_COMPOSE_ARGS="--profile $PROFILE"
else
    ADDITIONAL_DOCKER_COMPOSE_ARGS=""
fi

docker compose -f docker-compose-ppl.yaml $ADDITIONAL_DOCKER_COMPOSE_ARGS up -d

# TODO: add option to run with RTSP input
# TODO: add option to run debug pipeline w/o Python scripts or with pure DLS and dump metadata
