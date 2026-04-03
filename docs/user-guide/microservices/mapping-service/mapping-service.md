<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/scenescape/tree/main/mapping/docs">
     GitHub
  </a>
</div>
hide_directive-->

# Mapping Service

This Docker container provides a Flask REST API interface for 3D reconstruction with build-time
model selection, enabling generation of meshes and camera parameters from captured frames.
Each container is built with one of two state-of-the-art models:

- **MapAnything**: Universal Feed-Forward Metric 3D Reconstruction
- **VGGT**: Visual Geometry Grounded Transformer for sparse view reconstruction

## Features

- **Flask** based REST API with JSON responses
- **Build-Time Model Selection**: Single model per container, no dependency conflicts
- **Multi-image Input**: Process multiple images simultaneously
- **GLB Output**: Generate 3D models in GLB format
- **Camera Data**: Extract camera poses and intrinsics
- **Image Enhancement**: Automatic CLAHE preprocessing for improved contrast
- **Containerized**: Model-specific containers for clean deployment

## SceneScape Integration

The following diagram shows the dataflow between the Intel® SceneScape Web UI, database, MQTT
broker, and the Mapping Service.

> **Note:** The diagram is currently best viewed in light color mode.

```mermaid
sequenceDiagram
    SceneScape Web UI ->>+Database: "Query camera info"
    SceneScape Web UI ->>+MQTT Broker: "Get latest frame for each camera"
    SceneScape Web UI ->>+Mapping Service: "REST API call to /reconstruction endpoint with camera frames"
    Mapping Service ->>+SceneScape Web UI: "Output: GLB & Camera Poses"
    SceneScape Web UI ->>+Database: "Update scene map & camera poses"
```

## API Endpoints

### Health Check

```text
GET /health
```

**Expected output:** Endpoint path for health check is defined.

Returns service status and model availability.

### List Models

```text
GET /models
```

**Expected output:** Endpoint path for model information is defined.

Returns information about the model in this container and its status.

### 3D Reconstruction

```text
POST /reconstruction
```

**Expected output:** Endpoint path for reconstruction requests is defined.

Perform 3D reconstruction from images and/or video.

#### Request Format

**Multipart Form Data (Required)**

The API accepts `Content-Type: multipart/form-data` to upload image and/or video files:

```text
POST /reconstruction
Content-Type: multipart/form-data

Form fields:
- images: Image files (can specify multiple)
- video: Video file (optional)
- output_format: "glb" or "json" (default: "glb")
- mesh_type: "mesh" or "pointcloud" (default: "mesh")
- use_keyframes: "true" or "false" (for video, default: true)
```

**Expected output:** Required multipart request format and accepted form fields are defined.

**Notes:**

- You can provide images only, video only, or both together
- All inputs are processed as individual frames
- The API only accepts multipart/form-data format with actual file uploads
- JSON payloads with base64-encoded images are NOT supported
- `model_type` is no longer needed - the model is determined at build time

#### Response Format

```json
{
  "success": true,
  "model": "mapanything", // indicates which model was used
  "glb_data": "base64_encoded_glb_file",
  "camera_poses": [
    {
      "rotation": [0, 0, 0, 0], // quaternion rotation [x, y, z, w]
      "translation": [0, 0, 0] // 3D translation vector [x, y, z]
    }
  ],
  "intrinsics": [
    [
      [0, 0, 0],
      [0, 0, 0],
      [0, 0, 1]
    ] // 3x3 intrinsics matrix [[fx, 0, cx], [0, fy, cy], [0, 0, 1]]
  ],
  "processing_time": 15.23,
  "message": "Success message"
}
```

## Building and Running

Check out [How to Build from Source](./build-from-source.md) for instructions on building
the service from source and running it.

## Using the API

### Example with Python Client

```python
import base64
import requests

# For production deployments, replace verify=False with the path to the
# SceneScape CA certificate (e.g., verify="/path/to/scenescape-ca.crt").
# verify=False disables TLS certificate verification and should only be
# used locally with the default self-signed certificate during development.
with open("image1.jpg", "rb") as image1, open("image2.jpg", "rb") as image2:
  files = [
    ("images", ("image1.jpg", image1, "image/jpeg")),
    ("images", ("image2.jpg", image2, "image/jpeg")),
  ]
  data = {
    "output_format": "glb",
    "mesh_type": "mesh",
  }

  response = requests.post(
    "https://localhost:8444/reconstruction",
    files=files,
    data=data,
    verify=False,
  )

response.raise_for_status()
result = response.json()

if result.get("success"):
  glb_data = base64.b64decode(result["glb_data"])
  with open("output.glb", "wb") as output_file:
    output_file.write(glb_data)

  print(f"Model used: {result['model']}")
  print(f"Processing time: {result['processing_time']:.2f}s")
  print(f"Camera poses: {len(result['camera_poses'])}")
```

### Using the Included Client

```bash
# Check API health (model-agnostic)
python client_example.py --health-check --insecure

# Specify output type
python client_example.py --images image1.jpg image2.jpg --mesh-type mesh --output mesh.glb --insecure
python client_example.py --images image1.jpg image2.jpg --mesh-type pointcloud --output points.glb --insecure
```

**Expected output:** Health status is returned and reconstruction output files are generated for the selected mesh type.

### Using curl

```bash
# Health check
curl https://localhost:8444/health --insecure

# List models
curl https://localhost:8444/models --insecure

# Reconstruction with images (using multipart/form-data - recommended)
curl -X POST "https://localhost:8444/reconstruction" \
  -F "images=@image1.jpg" \
  -F "images=@image2.jpg" \
  -F "output_format=glb" \
  -F "mesh_type=mesh" \
  --insecure

# Reconstruction with video
curl -X POST "https://localhost:8444/reconstruction" \
  -F "video=@video.mp4" \
  -F "output_format=glb" \
  -F "mesh_type=mesh" \
  -F "use_keyframes=true" \
  --insecure

# Reconstruction with both images and video
curl -X POST "https://localhost:8444/reconstruction" \
  -F "images=@image1.jpg" \
  -F "images=@image2.jpg" \
  -F "video=@video.mp4" \
  -F "output_format=glb" \
  -F "mesh_type=mesh" \
  --insecure

# Save GLB output to file (requires jq for JSON parsing)
curl -X POST "https://localhost:8444/reconstruction" \
  -F "images=@image1.jpg" \
  -F "images=@image2.jpg" \
  -F "output_format=glb" \
  -F "mesh_type=mesh" \
  --insecure | jq -r '.glb_data' | base64 -d > output.glb
```

**Expected output:** Health/model endpoints return JSON responses and reconstruction requests return GLB data (optionally saved to `output.glb`).

## Model Comparison

| Feature               | MapAnything           | VGGT                                                                           |
| --------------------- | --------------------- | ------------------------------------------------------------------------------ |
| **License**           | Apache 2.0            | [VGGT License](https://github.com/facebookresearch/vggt/blob/main/LICENSE.txt) |
| **Input**             | Multiple images       | Multiple images/video frames                                                   |
| **Strength**          | Metric reconstruction | Sparse view reconstruction                                                     |
| **Speed**             | Fast                  | Moderate                                                                       |
| **Memory**            | Lower                 | Higher                                                                         |
| **Quality**           | High for dense views  | High for sparse views                                                          |
| **Native Output**     | Watertight mesh       | Point cloud                                                                    |
| **Supported Outputs** | Mesh, Point cloud     | Point cloud, Mesh                                                              |

## Development

### Adding Custom Models

To add support for additional models:

1. Create a new model class following the `ReconstructionModel` interface
2. Create a model-specific service file (e.g., `mymodel_service.py`)
3. Add model installation steps to the Dockerfile
4. Update the Makefile to support the new model type
5. Add build-time model selection logic

## Minimum Hardware Requirements

- **CPU**: 12th Gen or newer Intel® Core™ processors (i5 or higher), or 2nd Gen or newer Intel®
  Xeon® processors
- **RAM**:
  - MapAnything: 8GB minimum (4GB for model + overhead)
  - VGGT: 16GB minimum (8GB for model + overhead, more for high resolution images)
- **Storage**: 12GB free space for Docker images and models

## Performance Notes

- **First Run**: Initial model download may take several minutes
- **Memory Requirements**:
  - MapAnything: ~4GB RAM
  - VGGT: ~8GB RAM (more for high resolution)
- **Processing Time**: Varies by image count and resolution

## Best Practices

- **Image Preprocessing**: All input images automatically undergo Contrast Limited Adaptive
  Histogram Equalization (CLAHE) to enhance contrast and improve reconstruction quality,
  particularly for low-contrast or unevenly-lit scenes.
- **VGGT** pointcloud output scale is orders of magnitude smaller than the actual scene. The
  scale of the output mesh generated by **Map Anything** is closer to the actual scene than
  **VGGT**.
- The output mesh generated by **VGGT** version of the service has several issues currently.
  All of these issues will be addressed in the next Intel® SceneScape release:
  - It is not aligned with the original point cloud
  - The resolution of the texture is not sharp.
  - Pointcloud to mesh conversion takes many multiples of time taken by inference that
    generates the pointcloud.
- The service has not been tested with cameras which have distortion. Expect the reconstruction
  to perform poorly if your cameras show visual distortion.
- The reconstruction does not distinguish between static and dynamic objects. If the camera
  frames contain objects like persons, vehicles etc., the reconstruction will include those
  objects as well. For best results, call the service when the camera frames do not contain
  objects that should not be included in the mesh.

## Supporting Resources

- [Build from Source](./build-from-source.md): Build the service from source and run it.
- [API Reference](./api-docs/mapping-api.yaml): Comprehensive reference for the Mapping service
  REST API endpoints.

<!--hide_directive
:::{toctree}
:hidden:

./build-from-source.md

:::
hide_directive-->
