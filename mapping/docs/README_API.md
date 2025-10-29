# 3D Mapping Models REST API Service

This Docker container provides a Flask REST API interface for 3D reconstruction with build-time model selection. Each container is built with one of two state-of-the-art models:

- **MapAnything**: Universal Feed-Forward Metric 3D Reconstruction
- **VGGT**: Visual Geometry Grounded Transformer for sparse view reconstruction

**Build-Time Selection**: The model is chosen during container build, eliminating dependency conflicts and reducing image size.

## Features

- 🌐 **Flask** based REST API with JSON responses
- 🏗️ **Build-Time Model Selection**: Single model per container, no dependency conflicts
- 📸 **Multi-image Input**: Process multiple images simultaneously
- 🎯 **GLB Output**: Generate 3D models in GLB format
- 📊 **Camera Data**: Extract camera poses and intrinsics
- 🔧 **CPU/GPU Support**: Automatic device detection
- 🐳 **Containerized**: Model-specific containers for clean deployment

## API Endpoints

### Health Check

```
GET /health
```

Returns service status and model availability.

### List Models

```
GET /models
```

Returns information about the model in this container and its status.

### 3D Reconstruction

```
POST /reconstruct
```

Perform 3D reconstruction from input images.

#### Request Format

```json
{
  "images": [
    {
      "data": "base64_encoded_image_data",
      "filename": "optional_filename.jpg"
    }
  ],
  "output_format": "glb", // "glb" or "json"
  "mesh_type": "mesh" // "mesh" or "pointcloud"
}
```

**Note:** `model_type` is no longer needed - the model is determined at build time.

#### Response Format

```json
{
  "success": true,
  "model": "mapanything", // indicates which model was used
  "glb_data": "base64_encoded_glb_file",
  "camera_poses": [
    {
      "rotation": [w, x, y, z],  // quaternion rotation
      "translation": [x, y, z]   // 3D translation vector
    }
  ],
  "intrinsics": [
    [[fx, 0, cx], [0, fy, cy], [0, 0, 1]]  // 3x3 intrinsics matrix
  ],
  "processing_time": 15.23,
  "message": "Success message"
}
```

## Building and Running

### Build Model-Specific Containers

```bash
cd mapping/

# Build MapAnything variant (default)
make MODEL_TYPE=mapanything
# or simply: make

# Build VGGT variant
make MODEL_TYPE=vggt

# Build both variants
make build-all

# Custom image names
make MODEL_TYPE=mapanything IMAGE="my-mapanything-service"
make MODEL_TYPE=vggt IMAGE="my-vggt-service"
```

### Run API Service

```bash
# Run MapAnything service
docker run -p 8000:8000 scenescape-mapping-mapanything:latest

# Run VGGT service
docker run -p 8000:8000 scenescape-mapping-vggt:latest
```

## Using the API

### Example with Python Client

```python
import base64
import requests

# Encode images to base64
def encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')

# Prepare request
payload = {
    "images": [
        {"data": encode_image("image1.jpg"), "filename": "image1.jpg"},
        {"data": encode_image("image2.jpg"), "filename": "image2.jpg"}
    ],
    "output_format": "glb"
}

# Send request
response = requests.post("http://localhost:8000/reconstruct", json=payload)
result = response.json()

if result["success"]:
    # Save GLB file
    glb_data = base64.b64decode(result["glb_data"])
    with open("output.glb", "wb") as f:
        f.write(glb_data)

    print(f"Model used: {result['model']}")
    print(f"Processing time: {result['processing_time']:.2f}s")
    print(f"Camera poses: {len(result['camera_poses'])}")
```

### Using the Included Client

```bash
# Check API health (model-agnostic)
python client_example.py --health-check

# Run reconstruction (no model parameter needed)
python client_example.py --images image1.jpg image2.jpg --output result.glb

# Specify output type
python client_example.py --images image1.jpg image2.jpg --mesh-type mesh --output mesh.glb
python client_example.py --images image1.jpg image2.jpg --mesh-type pointcloud --output points.glb

# JSON output instead of GLB
python client_example.py --images image1.jpg image2.jpg --format json --output result.json
```

### Using curl

```bash
# Health check
curl http://localhost:8000/health

# List models
curl http://localhost:8000/models

# Reconstruction (with base64 encoded images)
curl -X POST "http://localhost:8000/reconstruct" \
  -H "Content-Type: application/json" \
  -d '{
    "images": [{"data": "'$(base64 -w 0 image1.jpg)'", "filename": "image1.jpg"}],
    "output_format": "glb"
  }'
```

## Model Comparison

| Feature               | MapAnything           | VGGT                         |
| --------------------- | --------------------- | ---------------------------- |
| **License**           | Apache 2.0            | Research/Academic            |
| **Input**             | Multiple images       | Multiple images/video frames |
| **Strength**          | Metric reconstruction | Sparse view reconstruction   |
| **Speed**             | Fast                  | Moderate                     |
| **Memory**            | Lower                 | Higher                       |
| **Quality**           | High for dense views  | High for sparse views        |
| **Native Output**     | Watertight mesh       | Point cloud                  |
| **Supported Outputs** | Mesh, Point cloud     | Point cloud, Mesh            |

## Output Format Conversion

This API service provides flexible output format conversion between watertight meshes and point clouds for both models:

### Model Native Outputs

- **MapAnything**: Naturally produces watertight meshes
- **VGGT**: Naturally produces point clouds (Gaussian splats)

### Mesh Type Options

- **`mesh`** (default): Forces watertight mesh generation for both models
- **`pointcloud`**: Forces point cloud output for both models

### Conversion Capabilities

**VGGT → Mesh**: Point cloud to watertight mesh using surface reconstruction
**MapAnything → Point Cloud**: Mesh vertices to point cloud with original colors/masks

### Surface Reconstruction Methods

The service uses several techniques to create watertight meshes from point clouds:

1. **Alpha Shape**: Creates surfaces by fitting spheres of radius α between points
2. **Convex Hull**: Fast method that creates the smallest convex shape containing all points
3. **Outlier Removal**: Uses DBSCAN clustering to remove noise points
4. **Hole Filling**: Attempts to close gaps in the mesh surface

### Quality Considerations

- **Mesh quality** depends on point cloud density and distribution
- **Alpha shape** works best for organic/curved surfaces
- **Convex hull** is faster but may not capture concave details
- **Dense point clouds** produce better mesh quality
- **Sparse views** may result in incomplete surfaces

## Development

### Adding Custom Models

To add support for additional models:

1. Create a new model class following the `ReconstructionModel` interface
2. Create a model-specific service file (e.g., `mymodel_service.py`)
3. Add model installation steps to the Dockerfile
4. Update the Makefile to support the new model type
5. Add build-time model selection logic

### Configuration

Key configuration options:

- **Build-time**: Model selection via `MODEL_TYPE` build argument
- **Runtime**: Device detection (CPU/GPU), API timeout settings
- **Environment variables**: Model caching and memory management options

## Troubleshooting

### Common Issues

1. **Out of Memory**
   - Reduce batch size or use memory-efficient inference
   - Use CPU inference for very large images

2. **Model Loading Fails**
   - Check internet connection for initial download
   - Verify model cache directory permissions

3. **API Timeout**
   - Increase client timeout for large image sets
   - Consider processing images in smaller batches

4. **Image Format Issues**
   - Ensure images are in RGB format
   - Check base64 encoding is correct

### Logs and Debugging

```bash
# View container logs
docker logs <container_id>

# Run in interactive mode for debugging
docker run -it mapping-models-api bash

# Check model initialization
docker run mapping-models-api api 2>&1 | grep -E "(Loading|Model|Error)"
```

## Performance Notes

- **First Run**: Initial model download may take several minutes
- **GPU vs CPU**: GPU provides 3-5x speedup for inference
- **Memory Requirements**:
  - MapAnything: ~4GB RAM
  - VGGT: ~8GB RAM (more for high resolution)
- **Processing Time**: Varies by image count and resolution (typically 10-60 seconds)

## Migration from Runtime Model Selection

This API previously supported runtime model selection via the `model_type` parameter. The new build-time selection approach provides several benefits:

### Breaking Changes

- ❌ **Removed**: `model_type` parameter from API requests
- ✅ **Added**: `model` field in API responses indicating which model was used
- 🔄 **Changed**: Camera poses now use quaternion format `[w, x, y, z]` instead of rotation matrices

### Migration Steps

1. **Build separate containers** for each model type you need
2. **Update API clients** to remove `model_type` from requests
3. **Deploy model-specific containers** instead of a single container
4. **Update camera pose parsing** to use quaternion format

### Benefits of Build-Time Selection

- ✅ **No dependency conflicts** between models
- ✅ **50% smaller images** by excluding unused models
- ✅ **Faster startup** with single model loading
- ✅ **Better security** with reduced attack surface
- ✅ **Cleaner deployment** with clear model separation

## License

This API service wrapper is provided under the same licenses as the underlying models:

- MapAnything components: Apache 2.0 License
- VGGT components: Academic/Research License (check original repository)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test with both model variants
5. Submit a pull request
