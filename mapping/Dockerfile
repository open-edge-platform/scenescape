# Docker build for MapAnything and VGGT with Flask API
FROM python:3.10-slim

ARG USER_UID=1000
ARG USER_GID=1000

# Set environment variables including proxy settings
ENV DEBIAN_FRONTEND=noninteractive

# Copy CPU patch for VGGT early
COPY 0001-Run-it-on-CPU.patch /tmp/

# Configure apt for proxy if needed and install system dependencies
RUN if [ -n "$http_proxy" ] || [ -n "$HTTP_PROXY" ]; then \
        echo "Acquire::http::Proxy \"${http_proxy:-$HTTP_PROXY}\";" > /etc/apt/apt.conf.d/01proxy; \
    fi && \
    if [ -n "$https_proxy" ] || [ -n "$HTTPS_PROXY" ]; then \
        echo "Acquire::https::Proxy \"${https_proxy:-$HTTPS_PROXY}\";" >> /etc/apt/apt.conf.d/01proxy; \
    fi && \
    apt-get update && apt-get install -y \
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

# Create non-root user with matching UID/GID
RUN groupadd -g ${USER_GID} appuser && \
    useradd -m -u ${USER_UID} -g ${USER_GID} -s /bin/bash appuser

# Clone repositories directly in runtime stage
WORKDIR /workspace
RUN git clone https://github.com/facebookresearch/map-anything.git ./map-anything
RUN git clone https://github.com/facebookresearch/vggt.git ./vggt

# Apply CPU patch to VGGT
WORKDIR /workspace/vggt
RUN git apply /tmp/0001-Run-it-on-CPU.patch

# Create directories for model weights and outputs
RUN mkdir -p /workspace/model_weights && \
    mkdir -p /workspace/outputs && \
    mkdir -p /home/appuser/.cache/torch && \
    mkdir -p /home/appuser/.cache/huggingface

# Set ownership of workspace to appuser
RUN chown -R appuser:appuser /workspace /home/appuser/.cache

# Switch to appuser for remaining operations
USER appuser

# Configure pip for proxy settings and disable caching
RUN if [ -n "$http_proxy" ] || [ -n "$HTTP_PROXY" ]; then \
        mkdir -p /home/appuser/.config/pip && \
        echo "[global]" > /home/appuser/.config/pip/pip.conf && \
        echo "proxy = ${http_proxy:-$HTTP_PROXY}" >> /home/appuser/.config/pip/pip.conf && \
        echo "no-cache-dir = true" >> /home/appuser/.config/pip/pip.conf; \
    else \
        mkdir -p /home/appuser/.config/pip && \
        echo "[global]" > /home/appuser/.config/pip/pip.conf && \
        echo "no-cache-dir = true" >> /home/appuser/.config/pip/pip.conf; \
    fi

# Install Python packages directly (no virtual environment)
RUN pip install --upgrade pip
RUN pip install torch==2.3.1 torchvision==0.18.1 --index-url https://download.pytorch.org/whl/cpu

# Install map-anything
WORKDIR /workspace/map-anything
RUN pip install -e .

# Install vggt requirements and package
WORKDIR /workspace/vggt
RUN pip install -r requirements.txt
RUN pip install -r requirements_demo.txt
RUN pip install -e .

# Create initialization script for downloading model weights
WORKDIR /workspace
COPY <<'EOF' /workspace/init_models.sh
#!/bin/bash
# Script to download and cache model weights on first run

set -e

echo "Initializing model downloads..."

# Ensure cache directories exist
mkdir -p /home/appuser/.cache/torch
mkdir -p /home/appuser/.cache/huggingface
mkdir -p /workspace/model_weights

# Create marker files to track successful downloads
MAP_ANYTHING_MARKER="/workspace/model_weights/map_anything_downloaded.txt"
VGGT_MARKER="/workspace/model_weights/vggt_downloaded.txt"

success_count=0

# Download MapAnything model
if [ ! -f "$MAP_ANYTHING_MARKER" ]; then
    echo "Downloading MapAnything model weights..."
    cd /workspace/map-anything
    
    python -c "
import sys
sys.path.append('/workspace/map-anything')
from mapanything.models import MapAnything

try:
    # Try Apache 2.0 licensed model first
    model_name = 'facebook/map-anything-apache'
    print(f'Downloading {model_name}...')
    model = MapAnything.from_pretrained(model_name)
    print('MapAnything (Apache 2.0) model downloaded successfully!')
    with open('$MAP_ANYTHING_MARKER', 'w') as f:
        f.write('Downloaded successfully')
except Exception as e:
    print(f'Failed to download Apache model: {e}')
    exit(1)
"
    if [ $? -eq 0 ]; then
        success_count=$((success_count + 1))
    fi
else
    echo "MapAnything model already downloaded."
    success_count=$((success_count + 1))
fi

# Download VGGT model
if [ ! -f "$VGGT_MARKER" ]; then
    echo "Downloading VGGT model weights..."
    cd /workspace/vggt
    
    python -c "
import sys
import torch
sys.path.append('/workspace/vggt')
from vggt.models.vggt import VGGT
from pathlib import Path

try:
    model = VGGT()
    _URL = 'https://huggingface.co/facebook/VGGT-1B/resolve/main/model.pt'
    print('Downloading VGGT weights...')
    weights = torch.hub.load_state_dict_from_url(_URL, map_location='cpu')
    
    # Save weights locally for faster future access
    weights_path = Path('/workspace/model_weights/vggt_model.pt')
    weights_path.parent.mkdir(exist_ok=True)
    torch.save(weights, weights_path)
    
    print('VGGT model downloaded and cached successfully!')
    with open('$VGGT_MARKER', 'w') as f:
        f.write('Downloaded successfully')
except Exception as e:
    print(f'Failed to download VGGT model: {e}')
    exit(1)
"
    if [ $? -eq 0 ]; then
        success_count=$((success_count + 1))
    fi
else
    echo "VGGT model already downloaded."
    success_count=$((success_count + 1))
fi

if [ $success_count -eq 2 ]; then
    echo "All models initialized successfully!"
    exit 0
else
    echo "Failed to initialize some models."
    exit 1
fi
EOF

USER appuser

# Copy API service files
COPY src/*.py /workspace/
COPY requirements_api.txt /workspace/requirements_api.txt

# Install Flask API dependencies
RUN pip install -r /workspace/requirements_api.txt

# Create startup script for API service
COPY <<'EOF' /workspace/start_api_service.sh
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

# Initialize models first
bash /workspace/init_models.sh

# Change to workspace directory
cd /workspace

# Set Python to unbuffered mode for immediate log output
export PYTHONUNBUFFERED=1

# Start Flask service
echo "Starting Flask service on port 8000..."
echo "Press Ctrl+C to stop the service"

# Run Python in foreground with signal handling
exec python api_service.py
EOF

# Create entrypoint script
COPY <<'EOF' /workspace/entrypoint.sh
#!/bin/bash
set -e

echo "3D Mapping Models Container"
echo "=========================="
echo ""

# Check what mode to run in
if [ "$1" = "api" ]; then
    echo "Starting in API service mode..."
    exec bash /workspace/start_api_service.sh
else
    echo "Container started. Available modes:"
    echo ""
    echo "API Service mode:"
    echo "  docker run -p 8000:8000 <image> api"
    echo ""
    echo "Interactive mode:"
    echo "  docker run -it <image> bash"
    echo ""
    
    # Initialize models in background and keep container running
    bash /workspace/init_models.sh &
    exec "$@"
fi
EOF

USER root
RUN chmod +x /workspace/entrypoint.sh

USER appuser

# Set working directory
WORKDIR /workspace

# Expose port for Flask API service
EXPOSE 8000

# Set entrypoint
ENTRYPOINT ["/workspace/entrypoint.sh"]
CMD ["tail", "-f", "/dev/null"]
