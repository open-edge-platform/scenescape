<!--
SPDX-License-Identifier: Apache-2.0
(C) 2026 Intel Corporation
-->

# Auto Camera Calibration Service - AI Agent Guide

## Service Overview

The **Auto Camera Calibration** service (formerly `camcalibration`) computes camera intrinsics and extrinsics from sensor feeds using AprilTag markers or markerless calibration techniques. This microservice is critical for establishing accurate spatial awareness in SceneScape's multimodal sensor fusion framework.

**Primary Purpose**: Automatically calibrate cameras to provide accurate world-coordinate transformations for object tracking and scene understanding.

## Architecture & Components

### Core Modules

1. **`atag_camera_calibration.py`**: AprilTag-based calibration engine
   - Detects AprilTag markers in video frames
   - Computes camera intrinsics (focal length, distortion) and extrinsics (rotation, translation)
   - Publishes calibration results via MQTT

2. **`markerless_camera_calibration.py`**: Markerless calibration using visual features
   - Alternative calibration method without physical markers
   - Uses feature detection and matching across frames

3. **`auto_camera_calibration_controller.py`**: Main service controller
   - Orchestrates calibration workflows
   - Manages MQTT communication with Scene Controller
   - Handles REST API requests

4. **`auto_camera_calibration_api.py`**: REST API endpoints
   - `/calibrate`: Trigger calibration for specific camera
   - `/status`: Check calibration status
   - Health check endpoints

5. **`auto_camera_calibration_model.py`**: Data models and validation
   - Calibration request/response structures
   - Camera parameter models

6. **`reloc/`**: Relocalization support
   - Camera pose estimation refinement
   - Handles camera movement detection

### Dependencies

- **Scene Common**: Geometry utilities, MQTT/REST clients, schema validation
- **OpenCV**: Computer vision operations
- **NumPy/SciPy**: Numerical computations
- **AprilTag library**: Marker detection (for AprilTag mode)

## Communication Patterns

### MQTT Topics

**Subscribes**:

- `calibration/request/<camera_id>`: Calibration requests from Manager/Controller
- `detector/<camera_id>`: Object detection frames (when using detected objects)

**Publishes**:

- `calibration/result/<camera_id>`: Completed calibration parameters
- `calibration/status/<camera_id>`: Progress updates

### REST API

- **Base URL**: `http://autocalibration:5000/api/v1/`
- **Authentication**: TLS mutual auth (client certificates)
- **Health**: `/health` endpoint for liveness/readiness probes

## Development Workflows

### Building the Service

```bash
# From root directory
make autocalibration                    # Build image
make rebuild-autocalibration            # Clean + rebuild

# Build with dependencies
make build-core                         # Includes autocalibration
```

### Testing

```bash
# Unit tests
make -C tests autocalibration-unit

# Functional tests (requires running containers)
SUPASS=<password> make setup_tests
make -C tests autocalibration-functional
```

### Running Locally

```bash
# Start with docker-compose
docker compose up -d autocalibration

# View logs
docker compose logs autocalibration -f

# Execute commands in container
docker compose exec autocalibration bash
```

## Key Configuration

### Environment Variables

- `MQTT_BROKER`: MQTT broker address (default: `mosquitto:8883`)
- `SCENE_CONTROLLER_URL`: REST endpoint for Scene Controller
- `CALIBRATION_MODE`: `apriltag` or `markerless`
- `LOG_LEVEL`: `DEBUG`, `INFO`, `WARNING`, `ERROR`

### Configuration Files

- `requirements-runtime.txt`: Python dependencies
- `Dockerfile`: Container build instructions
- `config/`: Calibration algorithm parameters (tag sizes, detection thresholds)

## Code Patterns

### Starting a Calibration

```python
from auto_camera_calibration_controller import AutoCalibrationController

controller = AutoCalibrationController(
    mqtt_broker="mosquitto:8883",
    rest_url="https://scene:50001",
    config_file="config/calibration.json"
)

# Process MQTT calibration request
controller.handle_calibration_request(camera_id, frame_buffer)
```

### Publishing Results

```python
from scene_common.mqtt import PubSub

pubsub = PubSub(mqtt_auth, client_cert, root_cert, mqtt_broker)
calibration_result = {
    "camera_id": camera_id,
    "intrinsics": {"fx": 800, "fy": 800, "cx": 640, "cy": 360},
    "extrinsics": {"rotation": [...], "translation": [...]}
}
pubsub.publish(f"calibration/result/{camera_id}", json.dumps(calibration_result))
```

## Common Tasks

### Adding New Calibration Method

1. Create new module in `src/` (e.g., `new_calibration.py`)
2. Implement calibration algorithm following existing patterns
3. Update `auto_camera_calibration_controller.py` to support new mode
4. Add configuration schema in `config/`
5. Add unit tests in `tests/sscape_tests/autocalibration/`

### Modifying API Endpoints

1. Edit `src/auto_camera_calibration_api.py`
2. Update OpenAPI spec in `docs/user-guide/api-docs/autocalibration-api.yaml`
3. Rebuild image: `make rebuild-autocalibration`
4. Test with curl/Postman against running container

### Debugging Calibration Issues

1. Enable debug logging: `LOG_LEVEL=DEBUG` in docker-compose
2. Check MQTT messages: `docker compose exec mosquitto mosquitto_sub -t 'calibration/#'`
3. Inspect frames: Save detection images to volume for manual review
4. Verify AprilTag detection: Check tag sizes, lighting, camera resolution

## Integration Points

### Scene Controller

- Receives calibration results via MQTT
- Uses camera parameters for world-coordinate transformations
- Triggers recalibration when camera movement detected

### Manager Web UI

- Provides UI for triggering calibration
- Displays calibration status and results
- Stores calibration history in PostgreSQL

### DL Streamer Pipeline

- May provide video frames for calibration
- Not directly integrated—uses MQTT as intermediary

## File Structure

```
autocalibration/
├── Dockerfile                          # Container build
├── Makefile                            # Build rules
├── requirements-runtime.txt            # Python deps
├── src/
│   ├── atag_camera_calibration.py     # AprilTag calibration
│   ├── markerless_camera_calibration.py
│   ├── auto_camera_calibration_controller.py  # Main controller
│   ├── auto_camera_calibration_api.py         # REST endpoints
│   ├── auto_camera_calibration_model.py       # Data models
│   └── reloc/                         # Relocalization
├── docs/
│   └── user-guide/                    # Documentation
└── tools/                             # Utility scripts
```

## Troubleshooting

### Common Issues

1. **Calibration fails with "No tags detected"**
   - Check AprilTag visibility in frame
   - Verify tag family matches configuration
   - Increase exposure/lighting

2. **MQTT connection timeout**
   - Verify mosquitto service is running
   - Check TLS certificates in `manager/secrets/certs/`
   - Ensure network connectivity

3. **Inaccurate calibration results**
   - Use more calibration frames (increase sample count)
   - Ensure tags cover entire field of view
   - Check for lens distortion correction

### Logs & Diagnostics

```bash
# Service logs
docker compose logs autocalibration --tail 100

# MQTT traffic
docker compose exec mosquitto mosquitto_sub -t '#' -v

# Container health
docker compose ps autocalibration
```

## Testing Checklist

When modifying the service, verify:

- [ ] Unit tests pass: `make -C tests autocalibration-unit`
- [ ] Functional tests pass (with containers running)
- [ ] AprilTag detection works with sample data
- [ ] MQTT messages validated against schema
- [ ] API endpoints return correct status codes
- [ ] Calibration results match expected accuracy (reprojection error < 1.0)
- [ ] Service recovers from MQTT broker restart

## Related Documentation

- [User Guide](docs/user-guide/overview.md): High-level overview
- [API Reference](docs/user-guide/api-docs/autocalibration-api.yaml): REST API spec
- [Scene Common](../scene_common/): Shared library documentation
- [Testing Guide](../.github/instructions/testing.md): Test creation patterns
