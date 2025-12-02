#!/bin/bash

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -e

# INPUT CONFIGURATION
if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    echo "Usage: $0 <CAMERA_SETTINGS_FILE> [PROFILE]"
    echo "Supported profiles: [ rtsp ]"
    echo "Set environment variable DUMP_DLS_METADATA=true to enable metadata dumping in DLStreamer format."
    exit 1
fi

CAMERA_SETTINGS_FILE=$1
PROFILE=$2
if [ "$DUMP_DLS_METADATA" != "true" ]; then
    DUMP_DLS_METADATA=false
fi

# CONSTANTS
DLSPS_CONFIG_FILE="./dlsps_config.json"
VOLUME_PREFIX=scenescape
OUTPUT_DIR=./output
DLS_METADATA_OUTPUT_FILE=dls_metadata.jsonl
SCENESCAPE_METADATA_FILE=scenescape_metadata.jsonl

# VARIABLES
ROOT_DIR=$(git rev-parse --show-toplevel)
SECRETS_DIR=${ROOT_DIR}/manager/secrets
TOOLS_DIR=${ROOT_DIR}/tools
PPL_GENERATOR_IMAGE_TAG=$(cat ${ROOT_DIR}/version.txt | tr -d ' \n')
PPL_GENERATOR_IMAGE="scenescape-manager:${PPL_GENERATOR_IMAGE_TAG}"
GID=$(id -g)
CAMERA_ID=$(jq -r '.sensor_id' "$CAMERA_SETTINGS_FILE")

# HELPER FUNCTIONS
append_var_to_env() {
    local var_name="$1"
    local var_value="${!var_name}"
    echo "${var_name}=${var_value}" >> .env
}

convert_cam_settings_to_dlsps_config() {
    local ppl_generator_image="$1"
    local camera_settings_file="$2"
    local dlsps_config_file="$3"
    local dump_dls_metadata_flag="$4"
    metadata_option="$(if [ "$dump_dls_metadata_flag" = true ]; then echo "--dump-dls-metadata"; fi)"

    docker run --rm \
        -e PYTHONPATH=/home/scenescape/SceneScape/ \
        -e METADATA_OUTPUT_FILE=/home/pipeline-server/output/${DLS_METADATA_OUTPUT_FILE} \
        --entrypoint python \
        -v ./:/workspace \
        -v ${VOLUME_PREFIX}_vol-models:/models \
        -w /workspace \
        "$ppl_generator_image" \
        /workspace/cam-settings-to-dlsps-config.py \
        --camera-settings /workspace/"$camera_settings_file" \
        --config_folder /models/model_configs \
        --output_path "$dlsps_config_file" \
        ${metadata_option}
}

# PREPARE OUTPUT
mkdir -p "$OUTPUT_DIR"
if [ "$DUMP_DLS_METADATA" == "true" ]; then
    rm -rf "$OUTPUT_DIR/$DLS_METADATA_OUTPUT_FILE"
fi

# CONVERT CAMERA SETTINGS TO DLSPS CONFIG
convert_cam_settings_to_dlsps_config "$PPL_GENERATOR_IMAGE" "$CAMERA_SETTINGS_FILE" "$DLSPS_CONFIG_FILE" "$DUMP_DLS_METADATA"

# CONFIGURE DOCKER COMPOSE
echo '' > .env
append_var_to_env DLSPS_CONFIG_FILE
append_var_to_env ROOT_DIR
append_var_to_env SECRETS_DIR
append_var_to_env TOOLS_DIR
append_var_to_env OUTPUT_DIR
append_var_to_env UID
append_var_to_env GID
append_var_to_env PROFILE
append_var_to_env SCENESCAPE_METADATA_FILE
append_var_to_env CAMERA_ID

if [ -n "$PROFILE" ]; then
    ADDITIONAL_DOCKER_COMPOSE_ARGS="--profile $PROFILE"
else
    ADDITIONAL_DOCKER_COMPOSE_ARGS=""
fi

# RUN DOCKER COMPOSE
docker compose -f docker-compose-ppl.yaml $ADDITIONAL_DOCKER_COMPOSE_ARGS up -d
