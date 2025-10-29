# Build-Time Model Selection for Mapping Service

## Overview

The mapping service has been modified to use build-time model selection instead of runtime model selection. This eliminates dependency conflicts and reduces image size by only installing the chosen model.

## Changes Made

### 1. Model-Specific Service Files
- `api_service_base.py` - Base API service with no model parameter required
- `vggt_service.py` - VGGT-specific service entry point
- `mapanything_service.py` - MapAnything-specific service entry point

### 2. Dockerfile Modifications
- Added `MODEL_TYPE` build argument
- Conditional installation of only the selected model
- Uses existing `requirements_api.txt` for API dependencies
- Model-specific dependencies installed via `pip install -e .` from git repos
- Clean up of unused model directories to save space
- Model-specific service script selection

### 3. API Changes
- **BREAKING CHANGE**: Removed `model_type` parameter from `/reconstruct` endpoint
- The model is now determined at build time, not runtime
- API responses include `model` field to indicate which model was used

### 4. Makefile Updates
- Added `MODEL_TYPE` variable (defaults to `mapanything`)
- New build targets: `build-vggt`, `build-mapanything`, `build-all`
- Modified `common.mk` to support extra build arguments

### 5. Simplified Dependency Management
- Uses existing `requirements_api.txt` for Flask API dependencies
- Model-specific dependencies come from their respective git repositories
- No redundant requirements files needed

## Usage

### Building Model-Specific Images

#### Default (MapAnything)
```bash
cd mapping/
make
# or explicitly
make build-mapanything
```

#### VGGT Model
```bash
cd mapping/
make build-vggt
```

#### Build Both Models
```bash
cd mapping/
make build-all
```

#### Custom Image Names
```bash
# Build VGGT with custom name
make MODEL_TYPE=vggt IMAGE="my-vggt-service"

# Build MapAnything with custom name  
make MODEL_TYPE=mapanything IMAGE="my-mapanything-service"
```

### Running the Service

The service will automatically start with the correct model based on what was built:

```bash
# Run MapAnything image
docker run -p 8000:8000 scenescape-mapping-mapanything:latest

# Run VGGT image
docker run -p 8000:8000 scenescape-mapping-vggt:latest
```

### API Usage

#### Before (Runtime Model Selection)
```json
{
    "model_type": "vggt",
    "images": [{"data": "base64..."}],
    "output_format": "glb",
    "mesh_type": "mesh"
}
```

#### After (Build-Time Model Selection)
```json
{
    "images": [{"data": "base64..."}],
    "output_format": "glb", 
    "mesh_type": "mesh"
}
```

The response will include which model was used:
```json
{
    "success": true,
    "model": "vggt",
    "glb_data": "...",
    "camera_poses": [...],
    "intrinsics": [...],
    "message": "Successfully processed 2 images with vggt"
}
```

## Benefits

1. **No Dependency Conflicts**: Each image only contains one model's dependencies
2. **Smaller Images**: Unused models and dependencies are not included
3. **Cleaner API**: No need to specify model type at runtime
4. **Better Security**: Reduced attack surface with fewer dependencies
5. **Easier Deployment**: Clear separation of model variants

## Migration Guide

### For API Clients
- Remove `model_type` parameter from requests to `/reconstruct`
- Check the `model` field in responses to know which model was used
- Use appropriate image tag for desired model

### For Deployment
- Choose which model image to deploy based on requirements
- Update deployment configs to use model-specific image names
- Consider deploying both models as separate services if needed

## Validation

### Health Check
```bash
curl http://localhost:8000/health
```

Response includes model information:
```json
{
    "status": "healthy",
    "model": "vggt",
    "model_loaded": true,
    "device": "cpu"
}
```

### Model Information
```bash
curl http://localhost:8000/models
```

Response shows single model details:
```json
{
    "model": "vggt",
    "model_info": {
        "name": "vggt",
        "description": "VGGT - Visual Geometry Grounded Transformer...",
        "loaded": true,
        "native_output": "pointcloud",
        "supported_outputs": ["pointcloud", "mesh"]
    },
    "camera_pose_format": {...}
}
```