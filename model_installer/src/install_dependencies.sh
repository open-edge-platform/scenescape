#!/bin/bash
# ==============================================================================
# Copyright (C) 2021-2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================
#
# This script installs all Python dependencies required for model downloading
# and processing. It should be run during Docker image build.

set -euo pipefail

. /etc/os-release

# Function to display text in a given color
echo_color() {
    local text="$1"
    local color="$2"
    local color_code=""

    # Determine the color code based on the color name
    case "$color" in
        black) color_code="\e[30m" ;;
        red) color_code="\e[31m" ;;
        green) color_code="\e[32m" ;;
        bred) color_code="\e[91m" ;;
        bgreen) color_code="\e[92m" ;;
        yellow) color_code="\e[33m" ;;
        blue) color_code="\e[34m" ;;
        magenta) color_code="\e[35m" ;;
        cyan) color_code="\e[36m" ;;
        white) color_code="\e[37m" ;;
        *) echo "Invalid color name"; return 1 ;;
    esac

    # Display the text in the chosen color
    echo -e "${color_code}${text}\e[0m"
}

# Function to handle errors
handle_error() {
    echo -e "\e[31mError occurred: $1\e[0m"
    exit 1
}

# Trap errors and call handle_error
trap 'handle_error "- line $LINENO"' ERR

if [ "$ID" == "fedora" ]; then
  export PYTHON_CREATE_VENV=/usr/bin/python3.10
  $PYTHON_CREATE_VENV -m ensurepip --upgrade || handle_error $LINENO
else
  export PYTHON_CREATE_VENV=python3
fi

echo_color "Installing dependencies for model processing..." "green"

# Set the name of the virtual environment directory for quantization
VENV_DIR_QUANT="$HOME/.virtualenvs/dlstreamer-quantization"

# Create a Python virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR_QUANT" ]; then
  echo "Creating virtual environment in $VENV_DIR_QUANT..."
  $PYTHON_CREATE_VENV -m venv "$VENV_DIR_QUANT" || handle_error $VENV_DIR_QUANT
fi

# Activate the virtual environment
echo "Activating virtual environment in $VENV_DIR_QUANT..."
source "$VENV_DIR_QUANT/bin/activate"

# Upgrade pip in the virtual environment
pip install --no-cache-dir --upgrade pip

# Install OpenVINO module with compatible numpy version for quantization
pip install --no-cache-dir "numpy<2.5.0,>=1.16.6" || handle_error $LINENO
pip install --no-cache-dir openvino==2025.3.0 || handle_error $LINENO

pip install --no-cache-dir onnx || handle_error $LINENO
pip install --no-cache-dir seaborn || handle_error $LINENO
# Install compatible NNCF version for OpenVINO 2025.3.0
pip install --no-cache-dir "nncf>=2.14.0,<3.0.0" || handle_error $LINENO

# Install ultralytics for quantization
pip install --no-cache-dir --upgrade --extra-index-url https://download.pytorch.org/whl/cpu "ultralytics==8.3.153" "numpy<2.5.0" || handle_error $LINENO

deactivate

# Set the name of the virtual environment directory for model processing
VENV_DIR="$HOME/.virtualenvs/dlstreamer"

# Create a Python virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment in $VENV_DIR..."
  $PYTHON_CREATE_VENV -m venv "$VENV_DIR" || handle_error $LINENO
fi

# Activate the virtual environment
echo "Activating virtual environment in $VENV_DIR..."
source "$VENV_DIR/bin/activate"

# Upgrade pip in the virtual environment
pip install --no-cache-dir --upgrade pip

# Install OpenVINO module with compatible numpy version
pip install --no-cache-dir "numpy<2.0.0,>=1.16.6" || handle_error $LINENO
pip install --no-cache-dir openvino==2024.6.0 || handle_error $LINENO
pip install --no-cache-dir openvino-dev==2024.6.0 || handle_error $LINENO

pip install --no-cache-dir onnx || handle_error $LINENO
pip install --no-cache-dir seaborn || handle_error $LINENO
# Install compatible NNCF version for OpenVINO 2024.6.0
pip install --no-cache-dir "nncf>=2.12.0,<2.14.0" || handle_error $LINENO

# Install ultralytics for model conversion
pip install --no-cache-dir --upgrade --extra-index-url https://download.pytorch.org/whl/cpu "ultralytics==8.3.153" "numpy<2.0.0" || handle_error $LINENO

# Install PyTorch dependencies for CLIP models
pip install --no-cache-dir --upgrade torch==2.8.0 torchaudio==2.8.0 torchvision==0.23.0 || handle_error $LINENO
pip install --no-cache-dir transformers || handle_error $LINENO
pip install --no-cache-dir pillow || handle_error $LINENO

deactivate

echo_color "Dependencies installation completed successfully!" "bgreen"
