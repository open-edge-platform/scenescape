<!--
SPDX-License-Identifier: Apache-2.0
(C) 2026 Intel Corporation
-->

# Mapping Service - AI Agent Guide

## Service Overview

The **Mapping** service provides spatial mapping and localization capabilities for Intel® SceneScape using visual SLAM and neural mapping techniques. This experimental microservice enables 3D scene reconstruction, object localization, and map-based queries.

**Primary Purpose**: Generate 3D maps from camera feeds and provide spatial localization services for objects and cameras within reconstructed environments.

**Status**: Experimental—enabled via `make build-experimental` or `make build-all`

## Architecture & Components

### Core Modules

1. **`mapanything_service.py`**: Main mapping service API
   - FastAPI/Flask-based REST service
   - Handles map creation and query requests
   - Integrates with neural mapping models

2. **`mapanything_model.py`**: Neural mapping model interface
   - Wraps Map-Anything or similar visual SLAM models
   - Processes video frames to generate 3D maps
   - Handles feature extraction and matching

3. **`vggt_service.py`**: Visual Grounding and Geometry Transform service
   - Object localization within 3D maps
   - Transforms 2D detections to 3D coordinates
   - Query-based object search in map space

4. **`vggt_model.py`**: Visual grounding model wrapper
   - Language-vision models for object queries
   - Semantic understanding of scene elements

5. **`mesh_utils.py`**: 3D mesh processing utilities
   - Point cloud to mesh conversion
   - Mesh simplification and optimization
   - Export to standard formats (OBJ, PLY)

6. **`api_service_base.py`**: Base API framework
   - Shared API patterns
   - Authentication and error handling
   - Health check endpoints

### Image Preprocessing Pipeline

All input frames undergo automatic image enhancement before inference:

- **CLAHE (Contrast Limited Adaptive Histogram Equalization)**:
  - Applied in LAB color space to preserve color information
  - Enhances L-channel (lightness) only
  - Default parameters: `clip_limit=2.0`, `tile_grid_size=(8, 8)`
  - Implementation: `_applyCLAHE()` method in both `mapanything_model.py` and `vggt_model.py`
  - Purpose: Improves reconstruction quality for low-contrast or unevenly-lit scenes

### Dependencies

- **Map-Anything**: Neural SLAM model (vision-centric mapping)
- **PyTorch**: Deep learning framework
- **Open3D**: 3D data processing
- **FastAPI/Gunicorn**: Web service framework
- **OpenCV**: Computer vision utilities (including CLAHE preprocessing)
- **Scene Common**: REST/MQTT clients, geometry utilities

## Communication Patterns

### REST API

**Base URL**: `http://mapping:8080/api/v1/`

**Key Endpoints**:

- `POST /maps/create`: Create new map from video stream
- `GET /maps/{map_id}`: Retrieve map metadata
- `POST /maps/{map_id}/localize`: Localize object in map
- `POST /maps/{map_id}/query`: Query objects by description
- `GET /maps/{map_id}/mesh`: Download 3D mesh
- `GET /health`: Health check

**Authentication**: TLS client certificates (mutual TLS)

### MQTT Integration (Future)

- Currently REST-only
- Future: Subscribe to detector streams for continuous mapping
- Potential topics: `mapping/request`, `mapping/result/<map_id>`

### Data Flow

```
Video Frames → Mapping Service → Neural SLAM → 3D Map (Point Cloud/Mesh)
                    ↓
Object Query → Visual Grounding → 3D Coordinates → Scene Controller
```

## Development Workflows

### Building the Service

```bash
# From root directory (experimental build)
make mapping                            # Build image
make rebuild-mapping                    # Clean + rebuild
make build-experimental                 # Build mapping + cluster_analytics
make build-all                          # All services including experimental
```

### Testing

```bash
# Unit tests
make -C tests mapping-unit

# Functional tests (requires running containers)
SUPASS=<password> make setup_tests
make -C tests mapping-functional

# Manual API testing
curl -X POST http://localhost:8080/api/v1/maps/create \
  -H "Content-Type: application/json" \
  -d '{"video_url": "rtsp://camera1/stream"}'
```

### Running Locally

```bash
# Start with docker-compose (use experimental compose file or override)
docker compose up -d mapping

# View logs
docker compose logs mapping -f

# Execute commands in container
docker compose exec mapping bash

# Check installed packages
docker compose exec mapping pip freeze
```

## Key Configuration

### Environment Variables

- `MODEL_PATH`: Path to neural mapping model weights
- `DEVICE`: `cpu`, `cuda`, or `xpu` (Intel GPU)
- `GUNICORN_WORKERS`: Number of worker processes
- `LOG_LEVEL`: `DEBUG`, `INFO`, `WARNING`, `ERROR`
- `MAX_MAP_SIZE`: Maximum map size in MB

### Configuration Files

- `requirements_api.txt`: Python dependencies (API service)
- `requirements.txt`: Additional model dependencies
- `Dockerfile`: Container build with model installation
- `config/`: Model-specific configuration (thresholds, parameters)

### Model Installation

Mapping models (Map-Anything, etc.) are large and may require:

1. Pre-download of weights to volume
2. Model conversion for OpenVINO acceleration
3. Configuration of inference device (CPU/GPU)

## Code Patterns

### Creating a New Map

```python
from mapanything_service import MappingService

service = MappingService(model_path="/models/map-anything")

# Create map from video
map_id = service.create_map(
    video_source="rtsp://camera1/stream",
    duration_seconds=30,
    frame_skip=5
)

# Get map metadata
map_info = service.get_map(map_id)
print(f"Map created with {map_info['num_points']} points")
```

### Localizing Object in Map

```python
# Query object location
result = service.localize_object(
    map_id=map_id,
    query="red car",
    confidence_threshold=0.7
)

# Result contains 3D coordinates
if result['found']:
    x, y, z = result['position']
    print(f"Object located at ({x}, {y}, {z})")
```

### Exporting Mesh

```python
from mesh_utils import export_mesh

# Convert point cloud to mesh
mesh = service.get_mesh(map_id)

# Export to file
export_mesh(mesh, output_path="/maps/scene.obj", format="obj")
```

## Common Tasks

### Adding New Mapping Model

1. Create model wrapper class in `src/` (e.g., `new_slam_model.py`)
2. Implement standard interface: `create_map()`, `localize()`, `get_mesh()`
3. Add model dependencies to `requirements_api.txt`
4. Update `mapanything_service.py` to support new model type
5. Add configuration in `config/`
6. Document model-specific requirements

### Optimizing Mapping Performance

1. **Frame Skip**: Process fewer frames for faster mapping
2. **Resolution**: Reduce input resolution for speed vs. quality
3. **Batching**: Process frames in batches for better GPU utilization

### Debugging Mapping Failures

1. Check video source accessibility
2. Verify model weights loaded correctly
3. Inspect frame preprocessing (resolution, format)
   - **Note**: All frames undergo automatic CLAHE (Contrast Limited Adaptive Histogram Equalization) preprocessing to enhance contrast before inference
4. Enable verbose logging: `LOG_LEVEL=DEBUG`
5. Visualize intermediate outputs (feature matches, point clouds)

### Integrating with Scene Controller

```python
# After creating map, update Scene Controller with camera poses
from scene_common.rest_client import RESTClient

rest_client = RESTClient(
    url="https://scene:50001",
    client_cert="/secrets/certs/client.crt",
    root_cert="/secrets/certs/ca.crt"
)

# Send camera calibration from SLAM
camera_pose = map_info['camera_poses']['camera1']
rest_client.post(
    f"/cameras/{camera_id}/calibration",
    data=camera_pose
)
```

## Integration Points

### Scene Controller

- Mapping service can provide camera calibration (alternative to AprilTag)
- Sends 3D object locations to Scene Controller for tracking
- May receive object detection results for map refinement

### Auto Calibration

- Complementary approach: AprilTag vs. SLAM-based calibration
- Mapping provides more flexible calibration without markers
- Can use Auto Calibration results as initialization

### Manager Web UI

- Future: Web UI for map visualization
- Upload video files for offline mapping
- Browse and query existing maps

## File Structure

```
mapping/
├── Dockerfile                          # Container build
├── Makefile                            # Build rules
├── requirements_api.txt                # API service dependencies
├── requirements.txt                    # Additional model dependencies
├── 0001-Run-it-on-CPU.patch           # CPU optimization patch
├── src/
│   ├── mapanything_service.py         # Main mapping API
│   ├── mapanything_model.py           # Neural mapping model
│   ├── vggt_service.py                # Visual grounding API
│   ├── vggt_model.py                  # Grounding model wrapper
│   ├── mesh_utils.py                  # 3D processing utilities
│   └── api_service_base.py            # Base API framework
├── docs/
│   └── user-guide/                    # Documentation
├── tests/
│   └── test_mapping.py                # Unit tests
└── tools/
    └── map_converter.py               # Map format conversion
```

## Troubleshooting

### Common Issues

1. **Model loading fails**
   - Check `MODEL_PATH` environment variable
   - Verify model weights downloaded: `ls -lh /models/`
   - Check disk space for large models
   - Review Dockerfile for correct model installation steps

2. **Out of memory errors**
   - Reduce input resolution
   - Decrease number of frames processed
   - Lower batch size
   - Use CPU instead of GPU for smaller memory footprint

3. **Poor map quality**
   - Increase number of input frames
   - Ensure good camera movement (not too fast)
   - Check lighting conditions
   - Verify camera calibration quality

4. **API timeouts**
   - Mapping is compute-intensive—increase timeout limits
   - Process shorter video segments
   - Use background processing with status polling

### Logs & Diagnostics

```bash
# Service logs
docker compose logs mapping --tail 100

# Model loading diagnostics
docker compose exec mapping python -c "import torch; print(torch.cuda.is_available())"

# Check disk usage (models can be large)
docker compose exec mapping df -h

# Memory usage
docker stats mapping
```

## Performance Considerations

### Hardware Recommendations

- **CPU**: 8+ cores for reasonable performance
- **RAM**: 16GB+ (models and point clouds are memory-intensive)
- **Storage**: 50GB+ for models and generated maps

### Optimization Strategies

1. **Model Quantization**: Convert to INT8 for faster inference
2. **OpenVINO**: Use OpenVINO runtime for Intel hardware
3. **Caching**: Cache intermediate results (features, matches)
4. **Incremental Mapping**: Update maps incrementally vs. full reconstruction
5. **Level of Detail**: Generate multiple LOD versions for different use cases

## Testing Checklist

When modifying the service, verify:

- [ ] Unit tests pass: `make -C tests mapping-unit`
- [ ] API endpoints return correct status codes
- [ ] Model loads successfully on target device (CPU/GPU)
- [ ] Map creation completes without errors
- [ ] Generated meshes are valid (no holes, correct topology)
- [ ] Localization queries return reasonable results
- [ ] Memory usage stays within limits
- [ ] Service recovers from model errors gracefully

## Research & Experimental Features

As an experimental service, mapping includes:

- **Neural Radiance Fields (NeRF)**: Potential future integration
- **Semantic Mapping**: Object-level understanding in maps
- **Multi-Camera SLAM**: Fusion of multiple camera streams
- **Map Merging**: Combine maps from different sessions

## Related Documentation

- [Mapping Overview](docs/user-guide/overview.md): High-level introduction
- [Map-Anything Model](https://github.com/...): Upstream model documentation
- [Scene Common](../scene_common/): Shared geometry utilities
- [Testing Guide](../.github/instructions/testing.md): Test creation patterns
- [Python Conventions](../.github/instructions/python.md): Python coding standards
