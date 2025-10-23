# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# =========================
# STAGE 1: MODEL BUILDER STAGE
# =========================
FROM scenescape-common-base AS mapping-builder
ENV DEBIAN_FRONTEND=noninteractive
ARG CERTDOMAIN=scenescape.intel.com
ENV CERTDOMAIN=${CERTDOMAIN}

# Install system dependencies for ML models (these change less frequently)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    git \
    wget \
    curl \
    ffmpeg \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libglib2.0-0 \
    libgl1-mesa-dri \
    libgl1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy CPU patch for VGGT
COPY mapping/0001-Run-it-on-CPU.patch /tmp/

# Create directories and setup workspace
RUN mkdir -p /output /workspace/model_weights

# Clone and setup ML model repositories
WORKDIR /tmp
RUN git clone --depth=1 https://github.com/facebookresearch/map-anything.git ./map-anything && \
    git clone --depth=1 https://github.com/facebookresearch/vggt.git ./vggt

# Apply CPU patch to VGGT
WORKDIR /tmp/vggt
RUN git apply /tmp/0001-Run-it-on-CPU.patch

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
    python3 \
    python3-pip \
    python-is-python3 \
    ffmpeg \
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
RUN useradd -r -m -s /bin/bash $WSUSER && \
    usermod -a -G video,users $WSUSER && \
    chmod a+rX /home/$WSUSER

# Copy dependencies from builder stage
COPY --from=mapping-builder /tmp/map-anything $SCENESCAPE_HOME/map-anything
COPY --from=mapping-builder /tmp/vggt $SCENESCAPE_HOME/vggt

# Copy mapping service files
COPY mapping/src $SCENESCAPE_HOME/
COPY mapping/requirements_api.txt $SCENESCAPE_HOME/

# Install runtime Python dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r $SCENESCAPE_HOME/requirements_api.txt

# Install ML model packages in runtime stage
WORKDIR $SCENESCAPE_HOME/map-anything
RUN pip install --no-cache-dir torch==2.3.1 torchvision==0.18.1 --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -e .

WORKDIR $SCENESCAPE_HOME/vggt
RUN pip install --no-cache-dir -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements_demo.txt && \
    pip install --no-cache-dir -e .

# Copy on-demand model loader
COPY mapping/tools/ondemand_model_loader.py /usr/local/bin/download_models.py
RUN chmod +x /usr/local/bin/download_models.py

# Create directories and set permissions
RUN mkdir -p /workspace/model_weights $SCENESCAPE_HOME/outputs /home/$WSUSER/.cache && \
    chown -R $WSUSER:$WSUSER $SCENESCAPE_HOME /workspace/model_weights /home/$WSUSER/.cache

# Create startup script that ensures model directory permissions and downloads models
WORKDIR $SCENESCAPE_HOME
RUN echo '#!/bin/bash\n\
set -e\n\
chown -R $WSUSER:$WSUSER $SCENESCAPE_HOME /home/$WSUSER/.cache\n\
if [ "$SKIP_MODEL_DOWNLOAD" != "1" ]; then\n\
    echo "Checking 3D mapping models..."\n\
    python3 /usr/local/bin/download_models.py\n\
fi\n\
exec "$@"\n' > /usr/local/bin/startup.sh && chmod +x /usr/local/bin/startup.sh

# Create API service script
COPY <<'EOF' $SCENESCAPE_HOME/api_service_cmd
#!/bin/bash

# Enable job control and set up signal handling
set -e
set -m

# Function to handle shutdown
shutdown() {
    echo "Received shutdown signal, stopping API service..."
    # Kill any background processes
    jobs -p | xargs -r kill
    exit 0
}

# Set up signal handlers
trap shutdown SIGINT SIGTERM

echo "Starting 3D Mapping Models API Service..."

# Change to workspace directory
cd $SCENESCAPE_HOME

# Set Python to unbuffered mode for immediate log output
export PYTHONUNBUFFERED=1

# Start Flask service
echo "Starting Flask service on port 8000..."
echo "Press Ctrl+C to stop the service"

# Run Python in foreground with signal handling
exec python api_service.py
EOF

RUN chmod +x $SCENESCAPE_HOME/api_service_cmd

# Set working directory
WORKDIR $SCENESCAPE_HOME

# Expose port for Flask API service
EXPOSE 8000

# Set entrypoint (following autocalibration pattern)
ENTRYPOINT ["/usr/local/bin/startup.sh", "/home/scenescape/SceneScape/api_service_cmd"]

# =========================
# STAGE 3: TEST STAGE
# =========================
FROM mapping-runtime AS mapping-test

# Install test dependencies
RUN pip install --no-cache-dir pytest pytest-cov requests

# Copy test files
COPY mapping/tests $SCENESCAPE_HOME/tests

# Run tests by default
CMD ["python", "-m", "pytest", "/home/scenescape/SceneScape/tests", "-v"]
