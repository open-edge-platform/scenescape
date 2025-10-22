# 3D Mapping Models REST API Service

This Docker container provides a Flask REST API interface for 3D reconstruction using two state-of-the-art models:

- **MapAnything**: Apache 2.0 licensed model for metric 3D reconstruction from images
- **VGGT**: Video-to-3D Gaussian Transformer for sparse view reconstruction

## Features

- 🌐 **Flask** based REST API with JSON responses
- 🔄 **Dual Model Support**: MapAnything and VGGT models
- 📸 **Multi-image Input**: Process multiple images simultaneously
- 🎯 **GLB Output**: Generate 3D models in GLB format
- 📊 **Camera Data**: Extract camera poses and intrinsics
- 🔧 **CPU/GPU Support**: Automatic device detection
- 🐳 **Containerized**: Ready-to-deploy Docker container

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

Returns information about available models and their status.

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
  "model_type": "mapanything", // or "vggt"
  "intrinsics": {
    // optional
    "fx": 500.0,
    "fy": 500.0,
    "cx": 320.0,
    "cy": 240.0
  },
  "output_format": "glb", // currently only "glb" supported
  "mesh_type": "mesh" // for VGGT: "mesh" or "pointcloud"
}
```

#### Response Format

```json
{
  "success": true,
  "glb_data": "base64_encoded_glb_file",
  "camera_poses": [
    {
      "rotation": [[...], [...], [...]],  // 3x3 rotation matrix
      "translation": [x, y, z]             // 3D translation vector
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

### Build the Container

```bash
cd mapping/
docker build -t mapping-models-api .
```

### Run API Service

```bash
# Run the API service (accessible on localhost:8000)
docker run -p 8000:8000 mapping-models-api api
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
    "model_type": "mapanything",
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

    print(f"Processing time: {result['processing_time']:.2f}s")
    print(f"Camera poses: {len(result['camera_poses'])}")
```

### Using the Included Client

```bash
# Check API health
python client_example.py --health-check

# Run reconstruction with default output (mesh)
python client_example.py --images image1.jpg image2.jpg --model mapanything --output result.glb
python client_example.py --images image1.jpg image2.jpg --model vggt --output result.glb

# Force both models to produce watertight meshes
python client_example.py --images image1.jpg image2.jpg --model mapanything --mesh-type mesh --output mesh.glb
python client_example.py --images image1.jpg image2.jpg --model vggt --mesh-type mesh --output mesh.glb

# Force both models to produce point cloud output
python client_example.py --images image1.jpg image2.jpg --model mapanything --mesh-type pointcloud --output points.glb
python client_example.py --images image1.jpg image2.jpg --model vggt --mesh-type pointcloud --output points.glb
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
    "model_type": "mapanything",
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

1. Install the model in both Python environments
2. Add model initialization in `api_service.py`
3. Implement inference function following the existing pattern
4. Update the API endpoint to support the new model type

### Configuration

Key configuration options in `api_service.py`:

- `device`: Automatic CPU/GPU detection
- Model loading paths and caching
- API timeout settings
- Memory management options

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

## License

This API service wrapper is provided under the same licenses as the underlying models:

- MapAnything components: Apache 2.0 License
- VGGT components: Academic/Research License (check original repository)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test with both models
5. Submit a pull request
