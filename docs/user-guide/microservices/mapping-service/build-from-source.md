# How to Build from Source

## Overview

The Scenescape mapping service supports build-time selection of the underlying 3D reconstruction model: **MapAnything** or **VGGT**. This approach ensures only the chosen model and its dependencies are included, minimizing image size and avoiding dependency conflicts.

Each build produces a container image with a single model. The API and runtime are identical, but the model is fixed at build time.

## Directory Structure

- `src/` — Service and model code (entry points: `mapanything_service.py`, `vggt_service.py`)
- `tools/` — Utilities for downloading models and assets
- `tests/` — Unit tests
- `Dockerfile` — Multi-stage build with model selection
- `Makefile` — Build targets for each model
- `requirements_api.txt` — API dependencies (model dependencies handled separately)

## Build Instructions

### Prerequisites

- Docker
- Make
- Internet access (for model downloads)

### Build Steps

- **Clone the Repository**:
  Clone the repository.

  ```bash
  git clone https://github.com/open-edge-platform/scenescape.git -b main
  ```

  Note: Adjust the repo link appropriately in case of forked repo.

- **Navigate to the Directory**:

  ```bash
  cd scenescape
  ```

- **Build mapping**:

  ```bash
  export MODEL_TYPE=mapanything # or MODEL_TYPE=vggt
  ```

  ```bash
  make mapping
  ```

### How It Works

- The `MODEL_TYPE` variable controls which model is included (`mapanything` or `vggt`).
- The Dockerfile clones both model repos, but only installs and configures the selected one.
- Entry points (`mapanything_service.py` or `vggt_service.py`) are set up for each model.
- Model weights are downloaded at runtime. Volume mounts ensure that the downloaded weights are persistent and do not require repeated downloads.

## Testing

See `tests/README.md` for detailed testing instructions.

## API Documentation

See `docs/mapping-api.yaml` for REST API details. The `/reconstruction` endpoint uses the model selected at build time.

### Running the Service

```bash
docker run -d \
    --name mapping \
    --network scenescape \
    --hostname mapping.scenescape.intel.com \
    -v vol-mapping-model-weights:/workspace/model_weights \
    -v vol-mapping-torch-cache:/workspace/.cache/torch \
    -v vol-mapping-hf-cache:/workspace/.cache/huggingface \
    intel/scenescape-mapping-${MODEL_TYPE:-mapanything}
```

This command sets up the container with the correct user, network, hostname, ports, and persistent volumes for model weights and caches.

### API Usage

```json
{
  "images": [{ "data": "base64..." }],
  "output_format": "glb",
  "mesh_type": "mesh"
}
```

Example response:

```json
{
  "success": true,
  "glb_data": "...",
  "camera_poses": [],
  "intrinsics": [],
  "message": "complete"
}
```

## Validation

### Health Check

```bash
curl https://localhost:8444/v1/health
```

Example response:

```json
{
  "success": true,
  "status": "healthy",
  "ready": true,
  "model": "mapanything",
  "model_loaded": true,
  "device": "cpu",
  "initialization": {
    "state": "ready",
    "stage": "model_loaded",
    "progress": 100.0,
    "message": "model loaded",
    "error": null
  }
}
```

During startup, this endpoint may return HTTP `202` with:

- `status: "degraded"`
- `ready: false`
- `initialization.state: "starting"`

If startup fails permanently, this endpoint returns HTTP `503` with:

- `status: "unhealthy"`
- `ready: false`
- `initialization.state: "failed"`

You can poll startup progress without reading logs:

```bash
while true; do
  curl -ks https://localhost:8444/v1/health | jq '.status, .ready, .initialization'
  sleep 2
done
```

### Model Information

```bash
curl https://localhost:8444/v1/models
```

Response shows single model details:

```json
{
  "model": "mapanything",
  "model_info": {
    "name": "mapanything",
    "description": "Universal Feed-Forward Metric 3D Reconstruction",
    "loaded": true,
    "native_output": "pointcloud",
    "supported_outputs": ["pointcloud", "mesh"]
  },
  "camera_pose_format": {}
}
```
