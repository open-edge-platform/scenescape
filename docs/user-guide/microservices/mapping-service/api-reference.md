# Mapping Service API Reference

## API Endpoints

> **Security note:** Mapping service endpoints currently do not enforce endpoint-level
> authentication or authorization. Deploy behind trusted network boundaries and reverse
> proxy controls, and use TLS for transport protection.

### Health Check

```bash
GET /health
```

Returns service status and model availability.

### List Models

```bash
GET /models
```

Returns information about the model in this container and its status.

### 3D Reconstruction

```bash
POST /reconstruction
```

Perform 3D reconstruction from images and/or video.

#### Request Format

**Multipart Form Data (Required)**:

The API accepts `Content-Type: multipart/form-data` to upload image and/or video files:

```bash
POST /reconstruction
Content-Type: multipart/form-data

Form fields:
- images: Image files (can specify multiple)
- video: Video file (optional)
- output_format: "glb" or "json" (default: "glb")
- mesh_type: "mesh" or "pointcloud" (default: "mesh")
- use_keyframes: "true" or "false" (for video, default: true)
```

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

## Using the API

### Example with Python Client

```python
import base64
import requests
from pathlib import Path

# Prepare multipart request
files = []
handles = []
for image_path in ["image1.jpg", "image2.jpg"]:
  path = Path(image_path)
  handle = path.open("rb")
  handles.append(handle)
  files.append(("images", (path.name, handle, "image/jpeg")))

data = {
  "output_format": "glb",
  "mesh_type": "mesh",
}

try:
try:
  # Send request through the Apache reverse proxy used in the full stack deployment
  response = requests.post("https://localhost/api/v1/mapping/reconstruction", data=data, files=files, verify=False)
  result = response.json()

  if result["success"]:
    # Save GLB file
    glb_data = base64.b64decode(result["glb_data"])
    with open("output.glb", "wb") as f:
      f.write(glb_data)

    print(f"Model used: {result['model']}")
    print(f"Processing time: {result['processing_time']:.2f}s")
    print(f"Camera poses: {len(result['camera_poses'])}")
finally:
  for handle in handles:
    handle.close()
```

### Using the Included Client

```bash
# Check API health (model-agnostic)
python client_example.py --health-check --insecure

# Specify output type
python client_example.py --images image1.jpg image2.jpg --mesh-type mesh --output mesh.glb --insecure
python client_example.py --images image1.jpg image2.jpg --mesh-type pointcloud --output points.glb --insecure
```

### Using curl

```bash
# Health check
curl https://localhost:8444/v1/health --insecure

# Startup progress (poll initialization state)
while true; do
  curl -ks https://localhost:8444/v1/health | jq '{status, ready, initialization}'
  sleep 2
done

# List models
curl https://localhost:8444/v1/models --insecure

# Reconstruction with images (using multipart/form-data - recommended)
curl -X POST "https://localhost:8444/v1/reconstruction" \
  -F "images=@image1.jpg" \
  -F "images=@image2.jpg" \
  -F "output_format=glb" \
  -F "mesh_type=mesh" \
  --insecure

# Reconstruction with video
curl -X POST "https://localhost:8444/v1/reconstruction" \
  -F "video=@video.mp4" \
  -F "output_format=glb" \
  -F "mesh_type=mesh" \
  -F "use_keyframes=true" \
  --insecure

# Reconstruction with both images and video
curl -X POST "https://localhost:8444/v1/reconstruction" \
  -F "images=@image1.jpg" \
  -F "images=@image2.jpg" \
  -F "video=@video.mp4" \
  -F "output_format=glb" \
  -F "mesh_type=mesh" \
  --insecure

# Save GLB output to file (requires jq for JSON parsing)
curl -X POST "https://localhost:8444/v1/reconstruction" \
  -F "images=@image1.jpg" \
  -F "images=@image2.jpg" \
  -F "output_format=glb" \
  -F "mesh_type=mesh" \
  --insecure | jq -r '.glb_data' | base64 -d > output.glb
```

## Swagger Plugin

```{eval-rst}
.. swagger-plugin:: ./_assets/mapping-api.yaml
```
