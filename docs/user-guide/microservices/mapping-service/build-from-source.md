# Build Mapping Service from Source

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

  > **Note:** Adjust the repo link appropriately in case of forked repo.

- **Navigate to the Directory**:

  ```bash
  cd scenescape
  ```

- **Build mapping**:

  <!--hide_directive ::::{tab-set} hide_directive-->
  <!--hide_directive :::{tab-item} hide_directive--> **MapAnything**
  <!--hide_directive :sync: mapanything hide_directive-->

  ```bash
  export MODEL_TYPE=mapanything
  ```

  <!--hide_directive ::: hide_directive-->
  <!--hide_directive :::{tab-item} hide_directive--> **VGGT**
  <!--hide_directive :sync: vggt hide_directive-->

  ```bash
  export MODEL_TYPE=vggt
  ```

  <!--hide_directive
  :::
  ::::
  hide_directive-->

  ```bash
  make mapping
  ```

  This produces a single image tagged `intel/scenescape-mapping:<version>` containing the selected model.

- **Build all variants** (optional):

  ```bash
  make -C mapping build-all
  ```

  This builds both models and produces the same tags as the published images on Docker Hub:

  | Tag                                              | Model                 |
  | ------------------------------------------------ | --------------------- |
  | `intel/scenescape-mapping:<version>-mapanything` | MapAnything           |
  | `intel/scenescape-mapping:<version>-vggt`        | VGGT                  |
  | `intel/scenescape-mapping:<version>`, `:latest`  | MapAnything (default) |

  Individual variants can also be built with `make -C mapping build-mapanything` or `make -C mapping build-vggt`.

> **Note:** The root `make build-all` builds only the default MapAnything variant. To deploy VGGT, build it with `make -C mapping build-all` (or `build-vggt`), or pull the `<version>-vggt` image from Docker Hub, and point your deployment at that tag. See [Deploy on Docker](../../how-to-guides/deployment/deploy-docker.md#select-the-mapping-model) and [Deploy on Kubernetes](../../how-to-guides/deployment/deploy-kubernetes.md#select-the-mapping-model).

#### How It Works

- The `MODEL_TYPE` variable controls which model is included (`mapanything` or `vggt`).
- The Dockerfile clones both model repos, but only installs and configures the selected one.
- Entry points (`mapanything_service.py` or `vggt_service.py`) are set up for each model.
- Model weights are downloaded at runtime. Volume mounts ensure that the downloaded weights are persistent and do not require repeated downloads.

## Testing

See `tests/README.md` for detailed testing instructions.

## API Documentation

See [API Reference](./api-reference.md) for REST API details. The `/reconstruction` endpoint uses the model selected at build time.

### Running the Service

```bash
docker run -d \
    --name mapping \
    --network scenescape \
    --hostname mapping.scenescape.intel.com \
    -v vol-mapping-model-weights:/workspace/model_weights \
    -v vol-mapping-torch-cache:/workspace/.cache/torch \
    -v vol-mapping-hf-cache:/workspace/.cache/huggingface \
    intel/scenescape-mapping
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

The response shows single model details. For example:

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
