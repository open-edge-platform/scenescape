# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# =========================
# STAGE 1: MODEL BUILDER STAGE  
# =========================
FROM scenescape-common-base AS mapping-builder
ENV DEBIAN_FRONTEND=noninteractive
ARG CERTDOMAIN=scenescape.intel.com
ENV CERTDOMAIN=${CERTDOMAIN}
ARG MODEL_TYPE=mapanything
ENV MODEL_TYPE=${MODEL_TYPE}
RUN echo "MODEL_TYPE is set to: $MODEL_TYPE"

WORKDIR /tmp

# Copy the patch file for VGGT
COPY mapping/0001-Run-it-on-CPU.patch /tmp/

# Clone both models but only checkout/patch the selected one
# This ensures the COPY in runtime stage doesn't fail
RUN echo "Building for model: $MODEL_TYPE" && \
    git clone https://github.com/facebookresearch/map-anything.git ./map-anything && \
    git clone https://github.com/facebookresearch/vggt.git ./vggt && \
    if [ "$MODEL_TYPE" = "mapanything" ]; then \
        echo "Preparing MapAnything model..." && \
        cd ./map-anything && git checkout 44cbc5a && cd ..; \
    elif [ "$MODEL_TYPE" = "vggt" ]; then \
        echo "Preparing VGGT model..." && \
        cd ./vggt && git checkout 44b3afb && git apply /tmp/0001-Run-it-on-CPU.patch && cd ..; \
    else \
        echo "Invalid MODEL_TYPE: $MODEL_TYPE. Must be 'mapanything' or 'vggt'" && exit 1; \
    fi

# =========================
# STAGE 2: RUNTIME STAGE
# =========================
FROM ubuntu:22.04 AS mapping-runtime

# Label image with description and metadata
LABEL org.opencontainers.image.description="Intel® SceneScape's 3D Mapping Service"
LABEL org.opencontainers.image.vendor="Intel Corporation"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/open-edge-platform/scenescape"
LABEL org.opencontainers.image.documentation="https://github.com/open-edge-platform/scenescape/blob/main/mapping/docs/user-guide/overview.md"

ARG USER_ID=1001
ARG GROUP_ID=1001
ARG CERTDOMAIN=scenescape.intel.com
ENV CERTDOMAIN=${CERTDOMAIN}
ENV DEBIAN_FRONTEND=noninteractive
ENV WSUSER=scenescape
ENV SCENESCAPE_HOME=/home/$WSUSER/SceneScape

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    python3 \
    python3-pip \
    python-is-python3 \
    git \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libglib2.0-0 \
    libgl1-mesa-dri \
    libgl1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Add user (following SceneScape pattern)
RUN groupadd -g $GROUP_ID $WSUSER && \
    useradd -u $USER_ID -g $GROUP_ID -m -s /bin/bash $WSUSER && \
    usermod -a -G video,users $WSUSER && \
    chmod a+rX /home/$WSUSER

# Copy mapping service files
COPY mapping/src $SCENESCAPE_HOME/
COPY mapping/requirements_api.txt $SCENESCAPE_HOME/

# Install base Python dependencies (API requirements only)
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r $SCENESCAPE_HOME/requirements_api.txt

COPY --from=mapping-builder /usr/local/lib/python3.10/dist-packages/fast_geometry /usr/local/lib/python3.10/dist-packages/fast_geometry
COPY --from=mapping-builder /usr/local/lib/python3.10/dist-packages/scene_common /usr/local/lib/python3.10/dist-packages/scene_common

# Conditionally copy dependencies from builder stage based on model type
ARG MODEL_TYPE
ENV MODEL_TYPE=${MODEL_TYPE}

# Create a script to conditionally copy and install the model
RUN mkdir -p /workspace && \
    if [ "$MODEL_TYPE" = "mapanything" ]; then \
        echo "Will install MapAnything model..."; \
    elif [ "$MODEL_TYPE" = "vggt" ]; then \
        echo "Will install VGGT model..."; \
    fi

# We need to copy both because Docker COPY doesn't support conditional copy
# But we'll only install the selected one
COPY --from=mapping-builder /tmp/ /workspace/

# Install only the selected model and clean up
RUN if [ "$MODEL_TYPE" = "mapanything" ]; then \
        echo "Installing MapAnything model..." && \
        cd /workspace/map-anything && \
        pip install --no-cache-dir torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cpu && \
        pip install --no-cache-dir -e . && \
        cd / && rm -rf /workspace/vggt /workspace/mapping; \
    elif [ "$MODEL_TYPE" = "vggt" ]; then \
        echo "Installing VGGT model..." && \
        cd /workspace/vggt && \
        pip install --no-cache-dir torch==2.3.1 torchvision==0.18.1 torchaudio --extra-index-url https://download.pytorch.org/whl/cpu && \
        pip install --no-cache-dir -r requirements.txt && \
        pip install --no-cache-dir -r requirements_demo.txt && \
        pip install --no-cache-dir -e . && \
        cd / && rm -rf /workspace/map-anything /workspace/mapping; \
    fi

# Copy on-demand model loader and dependencies
COPY mapping/tools/*.py /usr/local/bin/

# Create directories and set permissions
RUN mkdir -p /workspace/model_weights $SCENESCAPE_HOME/outputs /workspace/.cache/torch /workspace/.cache/huggingface && \
    chown -R $WSUSER:$WSUSER $SCENESCAPE_HOME /workspace && \
    chmod -R 1777 /workspace

# Create startup script that ensures model directory permissions and downloads models
WORKDIR $SCENESCAPE_HOME
RUN cat <<'EOF' > /usr/local/bin/startup.sh
#!/bin/bash
set -e

# Set cache environment variables to use user directory
export TORCH_HOME=/workspace/.cache/torch
export HF_HOME=/workspace/.cache/huggingface
export TRANSFORMERS_CACHE=/workspace/.cache/huggingface

if [ "$SKIP_MODEL_DOWNLOAD" != "1" ]; then
    echo "Checking 3D mapping models..."
    python3 /usr/local/bin/ondemand_model_loader.py
fi

# Check if development mode is enabled via environment variable
if [ "$DEV_MODE" = "true" ] || [ "$DEV_MODE" = "1" ] || [ "$DEVELOPMENT" = "true" ]; then
    echo "Starting in DEVELOPMENT mode with ${MODEL_TYPE} model..."
    exec python ${MODEL_TYPE}_service.py --dev-mode
else
    echo "Starting in PRODUCTION mode with TLS and ${MODEL_TYPE} model..."
    # Ensure certificate directory exists and has proper permissions
    if [ -d "/run/secrets/certs" ]; then
        echo "TLS certificates directory found"
    else
        echo "WARNING: TLS certificates directory not found at /run/secrets/certs"
        echo "Make sure to mount certificates for production use"
    fi
    exec python ${MODEL_TYPE}_service.py
fi
EOF
RUN chmod +x /usr/local/bin/startup.sh

# Set working directory
WORKDIR $SCENESCAPE_HOME

# Switch to scenescape user
USER $WSUSER

# Expose port for Flask API service
EXPOSE 8444

# Set entrypoint (following autocalibration pattern)
ENTRYPOINT ["/usr/local/bin/startup.sh"]

# =========================
# STAGE 3: TEST STAGE
# =========================
FROM mapping-runtime AS mapping-test

USER root

# Copy test requirements and install test dependencies
COPY mapping/tests/requirements-test.txt /tmp/requirements-test.txt
RUN pip install --no-cache-dir -r /tmp/requirements-test.txt && \
    rm /tmp/requirements-test.txt

# Copy test files
COPY mapping/tests $SCENESCAPE_HOME/tests

# Ensure test directory has proper permissions
RUN chown -R $WSUSER:$WSUSER $SCENESCAPE_HOME/tests

USER $WSUSER

# Run tests by default
CMD ["python", "-m", "pytest", "/home/scenescape/SceneScape/tests", "-v"]
