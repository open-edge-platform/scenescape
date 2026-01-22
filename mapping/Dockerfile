# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# =========================
# STAGE 1: MODEL BUILDER STAGE
# =========================
FROM scenescape-common-base AS mapping-builder

ENV DEBIAN_FRONTEND=noninteractive
ARG MODEL_TYPE=mapanything
ENV MODEL_TYPE=${MODEL_TYPE}

WORKDIR /tmp

# Copy the patch files
COPY mapping/0001-Run-it-on-CPU.patch /tmp/
COPY mapping/mapanything-version-fix.patch /tmp/

# Clone and prepare only the selected model
RUN if [ "$MODEL_TYPE" = "mapanything" ]; then \
        git clone https://github.com/facebookresearch/map-anything.git ./map-anything && \
        cd ./map-anything && git checkout b84b28f && git apply /tmp/mapanything-version-fix.patch; \
    elif [ "$MODEL_TYPE" = "vggt" ]; then \
        git clone https://github.com/facebookresearch/vggt.git ./vggt && \
        cd ./vggt && git checkout 44b3afb && git apply /tmp/0001-Run-it-on-CPU.patch; \
    else \
        echo "Invalid MODEL_TYPE: $MODEL_TYPE. Must be 'mapanything' or 'vggt'" && exit 1; \
    fi

# =========================
# STAGE 2: RUNTIME STAGE
# =========================
FROM python:3.11-slim-bookworm AS mapping-runtime

# Label image with description and metadata
LABEL org.opencontainers.image.description="Intel® SceneScape's 3D Mapping Service"
LABEL org.opencontainers.image.vendor="Intel Corporation"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/open-edge-platform/scenescape"
LABEL org.opencontainers.image.documentation="https://github.com/open-edge-platform/scenescape/blob/main/mapping/docs/user-guide/overview.md"

ARG USER_ID=1001
ARG GROUP_ID=1001
ARG MODEL_TYPE=mapanything
ENV MODEL_TYPE=${MODEL_TYPE}
ENV DEBIAN_FRONTEND=noninteractive
ENV WSUSER=scenescape
ENV SCENESCAPE_HOME=/home/$WSUSER/SceneScape

# Install system dependencies, create user, and setup directories in one layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libglib2.0-0 \
    libgl1-mesa-dri \
    libgl1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    # Create user
    && groupadd -g $GROUP_ID $WSUSER \
    && useradd -u $USER_ID -g $GROUP_ID -m -s /bin/bash $WSUSER \
    && usermod -a -G video,users $WSUSER \
    && chmod a+rX /home/$WSUSER \
    # Create directories
    && mkdir -p /workspace/model_weights $SCENESCAPE_HOME/outputs /workspace/.cache/torch /workspace/.cache/huggingface \
    && chmod -R 1777 /workspace

# Copy service files and requirements
COPY mapping/src $SCENESCAPE_HOME/
COPY mapping/requirements_api.txt $SCENESCAPE_HOME/
COPY mapping/tools/*.py /usr/local/bin/

# Copy compiled packages from builder
COPY --chown=$WSUSER:$WSUSER --from=mapping-builder \
    /usr/local/lib/python3.11/site-packages/fast_geometry \
    /usr/local/lib/python3.11/site-packages/fast_geometry
COPY --chown=$WSUSER:$WSUSER --from=mapping-builder \
    /usr/local/lib/python3.11/site-packages/scene_common \
    /usr/local/lib/python3.11/site-packages/scene_common

# Copy the selected model directory based on MODEL_TYPE
COPY --from=mapping-builder /tmp/ /tmp/models/
RUN if [ "$MODEL_TYPE" = "mapanything" ]; then \
        mv /tmp/models/map-anything /workspace/map-anything && rm -rf /tmp/models/vggt; \
    elif [ "$MODEL_TYPE" = "vggt" ]; then \
        mv /tmp/models/vggt /workspace/vggt && rm -rf /tmp/models/map-anything; \
    fi && \
    rm -rf /tmp/models

# Install all Python dependencies in one layer
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r $SCENESCAPE_HOME/requirements_api.txt && \
    if [ "$MODEL_TYPE" = "mapanything" ]; then \
        cd /workspace/map-anything && \
        pip install --no-cache-dir torch==2.9.1 torchvision==0.24.1 torchaudio==2.9.1 --extra-index-url https://download.pytorch.org/whl/cpu && \
        pip install --no-cache-dir -e .; \
    elif [ "$MODEL_TYPE" = "vggt" ]; then \
        cd /workspace/vggt && \
        pip install --no-cache-dir torch==2.3.1 torchvision==0.18.1 --extra-index-url https://download.pytorch.org/whl/cpu && \
        pip install --no-cache-dir -r requirements.txt -r requirements_demo.txt && \
        pip install --no-cache-dir -e .; \
    fi && \
    rm -rf /usr/local/lib/python3.11/site-packages/torch/test \
           /usr/local/lib/python3.11/site-packages/torch/share \
           /usr/local/lib/python3.11/site-packages/torchvision/test 2>/dev/null || true && \
    chown -R $WSUSER:$WSUSER $SCENESCAPE_HOME /workspace

# Create startup script
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

if [ "$DEV_MODE" = "true" ] || [ "$DEV_MODE" = "1" ] || [ "$DEVELOPMENT" = "true" ]; then
    echo "Starting in DEVELOPMENT mode with ${MODEL_TYPE} model..."
    exec python ${MODEL_TYPE}_service.py --dev-mode
else
    echo "Starting in PRODUCTION mode with TLS and ${MODEL_TYPE} model..."
    [ -d "/run/secrets/certs" ] || echo "WARNING: TLS certificates directory not found at /run/secrets/certs"
    exec python ${MODEL_TYPE}_service.py
fi
EOF
RUN chmod +x /usr/local/bin/startup.sh

WORKDIR $SCENESCAPE_HOME
USER $WSUSER
EXPOSE 8444

ENTRYPOINT ["/usr/local/bin/startup.sh"]

# =========================
# STAGE 3: TEST STAGE
# =========================
FROM mapping-runtime AS mapping-test

USER root

# Install test dependencies and copy test files
COPY mapping/tests/requirements-test.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements-test.txt \
    && rm /tmp/requirements-test.txt

COPY --chown=$WSUSER:$WSUSER mapping/tests $SCENESCAPE_HOME/tests

USER $WSUSER

CMD ["python", "-m", "pytest", "/home/scenescape/SceneScape/tests", "-v"]
