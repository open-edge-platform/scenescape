# How to Build from Source

## Overview

The Intel® SceneScape mapping service supports build-time selection of the underlying 3D reconstruction model: **MapAnything** or **VGGT**. This approach ensures only the chosen model and its dependencies are included, minimizing image size and avoiding dependency conflicts.

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
  git clone https://github.com/open-edge-platform/scenescape.git
  ```

  Note: Adjust the repo link appropriately in case of forked repo.

- **Navigate to the Directory**:

  ```bash
  cd scenescape
  ```

- **Build mapping (default: mapanything)**:

  ```bash
  make mapping
  #or
  MODEL_TYPE=mapanything make mapping
  ```

  **Expected output:** Docker build completes successfully and produces the mapping service image with the `mapanything` model variant.

- **Build mapping (vggt)**:

  ```bash
  MODEL_TYPE=vggt make mapping
  ```

  **Expected output:** Docker build completes successfully and produces the mapping service image with the `vggt` model variant.

### Build Contract

| Contract Element    | Requirement                                                                        | Verification                                              |
| ------------------- | ---------------------------------------------------------------------------------- | --------------------------------------------------------- |
| Build input         | `MODEL_TYPE` must be either `mapanything` or `vggt`                                | Build command exits with code `0`                         |
| Build output        | One mapping container image with a single embedded model variant                   | Mapping image appears in local Docker image list.         |
| Invariant           | Runtime API surface remains the same regardless of selected model                  | Health and models endpoints are reachable and return JSON |
| Dependency behavior | Model weights are not baked in; they download at runtime and are cached on volumes | First run downloads weights; subsequent runs reuse cache  |

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
  -p 8444:8444 \
    -v vol-mapping-model-weights:/workspace/model_weights \
    -v vol-mapping-torch-cache:/workspace/.cache/torch \
    -v vol-mapping-hf-cache:/workspace/.cache/huggingface \
    scenescape-mapping
```

**Expected output:** Mapping service container starts in detached mode with persistent model/cache volumes mounted.

This command sets up the container with network, hostname, port exposure, and persistent volumes for model weights and caches.

### Runtime Contract

| Runtime Element     | Requirement                                                                    | Expected Behavior                                                          |
| ------------------- | ------------------------------------------------------------------------------ | -------------------------------------------------------------------------- |
| Container name      | `mapping`                                                                      | Container appears as running in `docker ps`                                |
| Network             | `scenescape`                                                                   | Service can communicate with other SceneScape services on the same network |
| API port            | `8444` exposed from container                                                  | Endpoints are reachable at `https://localhost:8444`                        |
| Model/cache volumes | `vol-mapping-model-weights`, `vol-mapping-torch-cache`, `vol-mapping-hf-cache` | First-run downloads persist and speed up subsequent starts                 |
| Model selection     | Fixed at build time                                                            | `/models` returns a single selected model                                  |

### API Usage

Canonical request format is `multipart/form-data` file upload:

```bash
curl -X POST "https://localhost:8444/reconstruction" \
  -F "images=@image1.jpg" \
  -F "images=@image2.jpg" \
  -F "output_format=glb" \
  -F "mesh_type=mesh" \
  --insecure
```

**Expected output:** Successful JSON response includes `success=true`, selected `model`, `glb_data`, `camera_poses`, and `intrinsics`.

The response will include which model was used:

```json
{
  "success": true,
  "model": "mapanything",
  "glb_data": "...",
  "camera_poses": [],
  "intrinsics": [],
  "message": "Successfully processed 2 images with mapanything"
}
```

## Validation

### Build Artifact Validation

```bash
docker images | grep scenescape-mapping
docker ps --filter name=mapping
```

**Expected output:** Mapping image is present locally and the `mapping` container is running.

### Health Check

```bash
curl https://localhost:8444/health
```

**Expected output:** JSON health response is returned with selected model and load status.

Response includes model information:

```json
{
  "status": "healthy",
  "model": "mapanything",
  "model_loaded": true,
  "device": "cpu"
}
```

### Model Information

```bash
curl https://localhost:8444/models
```

**Expected output:** JSON response returns details of the single model included in the container.

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
