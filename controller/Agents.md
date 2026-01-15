<!--
SPDX-License-Identifier: Apache-2.0
(C) 2026 Intel Corporation
-->

# Scene Controller Service - AI Agent Guide

## Service Overview

The **Scene Controller** is the central runtime state management service for Intel® SceneScape. It maintains real-time tracking of objects, cameras, and scenes through MQTT-based sensor fusion, coordinate transformations, and multi-object tracking algorithms. This is the core orchestrator that integrates all other services.

**Primary Purpose**: Maintain real-time scene state by fusing multimodal sensor data, tracking objects across cameras, managing coordinate transformations, and providing unified scene understanding to other services.

**Critical Insight**: Scene Controller stores **runtime state only**—no video data or persistent metadata. Manager handles persistence; Controller handles real-time processing.

## Architecture & Components

### Core Modules

1. **`scene_controller.py`**: Main service controller
   - MQTT message processing and validation
   - Scene lifecycle management
   - Object tracking coordination
   - REST API server
   - gRPC service endpoints
   - Schema validation for incoming messages

2. **`scene.py`**: Scene state management
   - Scene object representation
   - Camera registry and transformations
   - Floor plan and coordinate system management
   - Object collection management
   - Scene configuration (tracking params, coordinate frames)

3. **`tracking.py`**: Multi-object tracking engine
   - Object association across frames
   - Track lifecycle management (new, tracked, lost)
   - Re-identification (ReID) support
   - Kalman filtering for state estimation
   - Maximum unreliable time tracking

4. **`moving_object.py`**: Object representation
   - Position, velocity, acceleration tracking
   - Bounding box management
   - Category and confidence tracking
   - Object metadata (attributes, ReID features)
   - Coordinate transformations

5. **`cache_manager.py`**: State caching and optimization
   - LRU caching for frequently accessed data
   - Scene state snapshots
   - Performance optimization for queries

6. **`child_scene_controller.py`**: Hierarchical scene support
   - Parent-child scene relationships
   - Coordinate frame transformations between scenes
   - Object handoff between scenes

7. **`reid.py`**: Re-identification module
   - Feature vector management
   - Object matching across cameras
   - Identity consistency maintenance

8. **`vdms_adapter.py`**: VDMS integration (optional)
   - Vector database storage for ReID features
   - Historical query support
   - Metadata persistence

9. **`data_source.py`**: Data source abstraction
   - Camera feed management
   - RTSP stream handling
   - Frame synchronization

10. **`detections_builder.py`**: Detection message processing
    - Parse incoming detector messages
    - Coordinate transformations (image → world)
    - Detection validation and filtering

11. **`observability/`**: Metrics and tracing
    - OpenTelemetry instrumentation
    - Performance monitoring
    - Latency tracking for MQTT handlers

### Dependencies

- **Scene Common**: MQTT/REST clients, geometry (Point, BoundingBox, CoordinateFrame), schema validation
- **Fast Geometry**: C++ extension for high-performance spatial calculations
- **gRPC**: Remote procedure calls for service-to-service communication
- **NumPy**: Numerical operations for tracking
- **OpenCV**: Computer vision utilities (optional, for visualization)

## Communication Patterns

### MQTT Topics

**Subscribes**:

- `detector/<camera_id>`: Object detection messages (JSON schema validation)
- `singleton`: Single-object detections (special case for non-standard detectors)
- `calibration/result/<camera_id>`: Camera calibration updates from Auto Calibration
- `cluster/result/<scene_id>`: Cluster analysis results from Cluster Analytics

**Publishes**:

- `tracking/result/<scene_id>`: Tracked object updates with world coordinates
- `scene/status/<scene_id>`: Scene state changes
- `object/<object_id>/update`: Individual object state updates

### REST API

**Base URL**: `https://scene:50001/api/v1/`

**Key Endpoints**:

- `GET /scenes/`: List all scenes
- `POST /scenes/`: Create new scene
- `GET /scenes/{scene_id}`: Get scene details
- `PUT /scenes/{scene_id}`: Update scene configuration
- `DELETE /scenes/{scene_id}`: Delete scene
- `GET /scenes/{scene_id}/objects`: Query tracked objects
- `POST /scenes/{scene_id}/cameras`: Add camera to scene
- `PUT /scenes/{scene_id}/cameras/{camera_id}`: Update camera calibration
- `GET /health`: Health check

**Authentication**: TLS mutual auth (client certificates)

### gRPC Service

- Complementary to REST for service-to-service calls
- Defined in `proto/` files (if exists)
- Higher performance for frequent operations

## Development Workflows

### Building the Service

```bash
# From root directory
make controller                         # Build image (alias: scene)
make rebuild-controller                 # Clean + rebuild
make build-core                         # Build all core services
```

### Testing

```bash
# Unit tests
make -C tests controller-unit
make -C tests geometry-unit             # Test fast_geometry

# Functional tests (requires running containers)
SUPASS=<password> make setup_tests
make -C tests controller-functional

# Specific test module
pytest tests/sscape_tests/controller/test_tracking.py -v
```

### Running Locally

```bash
# Start with docker-compose
docker compose up -d scene

# View logs
docker compose logs scene -f

# Debug with verbose logging
docker compose up scene -e LOG_LEVEL=DEBUG

# Interactive shell
docker compose exec scene bash
```

## Key Configuration

### Environment Variables

- `MQTT_BROKER`: MQTT broker address (default: `mosquitto:8883`)
- `REST_PORT`: REST API port (default: `50001`)
- `GRPC_PORT`: gRPC service port (default: `50051`)
- `LOG_LEVEL`: `DEBUG`, `INFO`, `WARNING`, `ERROR`
- `SCHEMA_FILE`: Path to JSON schema definitions
- `TRACKER_CONFIG`: Path to tracker configuration JSON
- `CONTROLLER_ENABLE_METRICS`: Enable OpenTelemetry metrics (true/false)
- `CONTROLLER_ENABLE_TRACING`: Enable OpenTelemetry tracing (true/false)

### Configuration Files

1. **`config/schema/`**: JSON schemas for message validation
   - `detector.json`: Detector message schema
   - `singleton.json`: Singleton detection schema
   - `calibration.json`: Calibration result schema

2. **Tracker Configuration** (example):

```json
{
  "max_unreliable_time": 2.0,
  "association_threshold": 0.5,
  "min_confidence": 0.5,
  "enable_reid": true,
  "kalman_filter": {
    "process_noise": 0.1,
    "measurement_noise": 0.1
  }
}
```

## Code Patterns

### Initializing Scene Controller

```python
from controller.scene_controller import SceneController

controller = SceneController(
    mqtt_broker="mosquitto:8883",
    rest_url="https://scene:50001",
    schema_file="config/schema/detector.json",
    tracker_config="config/tracker.json"
)

# Start MQTT listening and REST API
controller.start()
```

### Processing Detector Messages

```python
from controller.detections_builder import DetectionsBuilder

# Parse detector message
detections = DetectionsBuilder.from_mqtt_message(
    message_payload,
    camera_id,
    scene
)

# Transform to world coordinates
world_detections = []
for det in detections:
    world_pos = camera.transform_to_world(det.position_image)
    det.position_world = world_pos
    world_detections.append(det)
```

### Object Tracking

```python
from controller.tracking import Tracker

tracker = Tracker(
    max_unreliable_time=2.0,
    association_threshold=0.5
)

# Update tracker with new detections
tracked_objects = tracker.update(detections, timestamp)

# Get active tracks
active = [obj for obj in tracked_objects if obj.is_active()]

# Handle lost tracks
for obj in tracked_objects:
    if obj.state == "lost":
        print(f"Object {obj.id} lost at {obj.last_seen}")
```

### Coordinate Transformations

```python
from scene_common.geometry import Point, CoordinateFrame

# Define camera coordinate frame
camera_frame = CoordinateFrame(
    origin=Point(0, 0, 3),          # Camera position in world
    rotation=rotation_matrix,        # Camera orientation
    parent=scene.world_frame
)

# Transform image point to world
image_point = Point(320, 240, 0)    # Pixel coordinates
world_point = camera_frame.transform_to(image_point, scene.world_frame)
```

### Schema Validation

```python
from scene_common.schema import SchemaValidation

# Load schema
validator = SchemaValidation("config/schema/detector.json")

# Validate incoming message
is_valid, errors = validator.validate(message_data)
if not is_valid:
    print(f"Validation errors: {errors}")
    return

# Process valid message
process_detection(message_data)
```

## Common Tasks

### Adding New Object Type

1. Update detector schema: `config/schema/detector.json` (add category)
2. Update `moving_object.py` if special handling needed
3. Configure tracking parameters for new category in tracker config
4. Add tests: `tests/sscape_tests/controller/test_new_category.py`
5. Update documentation

### Implementing Custom Tracker

```python
# Create new tracker module
from controller.tracking import Tracker

class CustomTracker(Tracker):
    def associate_detections(self, detections, tracks):
        # Custom association logic (e.g., Hungarian algorithm)
        associations = {}
        for det in detections:
            best_match = self.find_best_match(det, tracks)
            if best_match:
                associations[det.id] = best_match.id
        return associations

    def update_track(self, track, detection):
        # Custom state update (e.g., different motion model)
        track.position = detection.position
        track.velocity = self.compute_velocity(track, detection)
        track.last_seen = detection.timestamp
```

### Debugging Tracking Issues

1. Enable observability: `CONTROLLER_ENABLE_METRICS=true`, `CONTROLLER_ENABLE_TRACING=true`
2. Log tracking events: `LOG_LEVEL=DEBUG`
3. Visualize tracks: Use visualization tools in `controller/tools/`
4. Check association thresholds: May be too strict/loose
5. Verify camera calibration: Inaccurate calibration → bad world coordinates

### Modifying REST API

```python
# In scene_controller.py, add new endpoint
from flask import Flask, jsonify, request

@app.route('/api/v1/scenes/<scene_id>/export', methods=['GET'])
def export_scene(scene_id):
    scene = controller.get_scene(scene_id)
    if not scene:
        return jsonify({"error": "Scene not found"}), 404

    export_data = {
        "scene_id": scene.id,
        "cameras": [cam.to_dict() for cam in scene.cameras],
        "objects": [obj.to_dict() for obj in scene.objects]
    }
    return jsonify(export_data), 200
```

## Integration Points

### Auto Calibration

- Receives camera calibration via MQTT: `calibration/result/<camera_id>`
- Updates camera intrinsics/extrinsics in scene
- Triggers coordinate frame recalculation
- May pause tracking during recalibration

### Manager Web UI

- Manager calls Scene Controller REST API for real-time data
- Scene Controller does NOT persist to database—Manager does
- Flow: User creates scene in Manager → Manager calls Scene Controller API → Scene Controller initializes runtime state

### Cluster Analytics

- Receives cluster results via MQTT: `cluster/result/<scene_id>`
- Integrates cluster information with object tracking
- May adjust tracking based on cluster membership

### DL Streamer Pipeline

- DL Streamer publishes detections to MQTT
- Scene Controller subscribes and processes
- No direct communication—MQTT as intermediary

### Mapping Service

- Potential: Scene Controller provides object positions for mapping
- Mapping service provides camera poses for calibration
- Future integration point

## File Structure

```
controller/
├── Dockerfile                          # Container build
├── Makefile                            # Build rules
├── requirements-runtime.txt            # Python dependencies
├── requirements-buildtime.txt          # Build-time dependencies
├── src/
│   ├── controller/
│   │   ├── scene_controller.py        # Main controller
│   │   ├── scene.py                   # Scene state
│   │   ├── tracking.py                # Tracking engine
│   │   ├── moving_object.py           # Object representation
│   │   ├── cache_manager.py           # State caching
│   │   ├── child_scene_controller.py  # Hierarchical scenes
│   │   ├── reid.py                    # Re-identification
│   │   ├── vdms_adapter.py            # VDMS integration
│   │   ├── data_source.py             # Camera feeds
│   │   ├── detections_builder.py      # Detection parsing
│   │   ├── time_chunking.py           # Temporal processing
│   │   ├── uuid_manager.py            # ID generation
│   │   └── observability/             # Metrics/tracing
│   ├── robot_vision/                  # Robot-specific extensions
│   ├── schema/                        # JSON schemas
│   └── setup.py                       # Package setup
├── config/
│   ├── schema/                        # Message schemas
│   └── tracker.json                   # Tracker configuration
├── docs/
│   └── user-guide/
│       ├── overview.md                # Architecture docs
│       ├── get-started.md             # Quick start
│       ├── How-to-build-source.md     # Build instructions
│       └── api-docs/
│           └── scene-controller-api.yaml  # OpenAPI spec
└── tools/                             # Utilities (visualization, etc.)
```

## Troubleshooting

### Common Issues

1. **Objects not tracking across frames**
   - Check `max_unreliable_time` (may be too short)
   - Verify `association_threshold` (may be too strict)
   - Ensure camera calibration accurate
   - Check detection consistency (IDs, timestamps)

2. **MQTT message validation failures**
   - Compare message format to schema: `config/schema/detector.json`
   - Check for missing required fields
   - Verify data types (numbers vs. strings)
   - Enable debug logging to see validation errors

3. **Coordinate transformation errors**
   - Verify camera calibration loaded correctly
   - Check coordinate frame definitions
   - Ensure parent-child frame relationships correct
   - Test transformations with known points

4. **Performance degradation with many objects**
   - Enable caching: Use `cache_manager.py`
   - Reduce tracking frequency (skip frames)
   - Prune lost tracks more aggressively
   - Consider spatial indexing for large scenes

### Logs & Diagnostics

```bash
# Service logs
docker compose logs scene --tail 100

# MQTT message inspection
docker compose exec mosquitto mosquitto_sub -t 'detector/#' -v

# Check REST API
curl -k https://localhost:50001/api/v1/scenes/

# Performance metrics (if enabled)
curl -k https://localhost:50001/metrics

# Container resource usage
docker stats scene
```

## Performance Considerations

### Optimization Strategies

1. **Fast Geometry**: Use C++ `fast_geometry` extension for spatial operations
2. **Caching**: Enable `cache_manager` for frequently accessed data
3. **Batch Processing**: Process multiple detections together
4. **Frame Skipping**: Track every N frames for less critical objects
5. **Spatial Indexing**: Use KD-tree for nearest neighbor searches
6. **Asynchronous I/O**: Non-blocking MQTT handlers

### Scalability Limits

- **Objects**: ~1000 concurrent objects per scene (hardware-dependent)
- **Cameras**: ~50 cameras per scene (MQTT bandwidth limited)
- **Scenes**: ~10 active scenes per controller instance
- **Message Rate**: ~1000 detection messages/second (depends on validation complexity)

### Hardware Recommendations

- **CPU**: 4+ cores (8+ for heavy tracking)
- **RAM**: 8GB minimum, 16GB recommended
- **Network**: Low latency to MQTT broker (<10ms)
- **Storage**: Minimal (no persistence)—mostly for logs

## Testing Checklist

When modifying the service, verify:

- [ ] Unit tests pass: `make -C tests controller-unit`
- [ ] Functional tests pass (with full docker-compose)
- [ ] MQTT messages validated correctly against schemas
- [ ] Object tracking maintains IDs across frames
- [ ] Coordinate transformations accurate (test with known points)
- [ ] REST API endpoints return correct status codes
- [ ] Performance metrics show acceptable latency (<100ms per message)
- [ ] Memory usage stable over time (no leaks)
- [ ] Service recovers from MQTT broker restart

## Observability

### Metrics (OpenTelemetry)

Enable with: `CONTROLLER_ENABLE_METRICS=true`

**Key Metrics**:

- `mqtt_message_processing_time`: Latency per message type
- `object_count`: Number of tracked objects per scene
- `tracking_associations`: Successful/failed associations
- `detection_rate`: Detections per second per camera

### Tracing (OpenTelemetry)

Enable with: `CONTROLLER_ENABLE_TRACING=true`

**Traced Operations**:

- MQTT message handling (end-to-end)
- Object tracking updates
- Coordinate transformations
- REST API requests

### Logging Best Practices

```python
import logging

logger = logging.getLogger(__name__)

# Use appropriate log levels
logger.debug(f"Processing detection: {det_id}")      # Verbose details
logger.info(f"Scene {scene_id} initialized")         # Important events
logger.warning(f"Low confidence detection: {conf}")  # Potential issues
logger.error(f"Tracking failed for object {obj_id}") # Errors
```

## Related Documentation

- [User Guide](docs/user-guide/overview.md): High-level architecture overview
- [API Reference](docs/user-guide/api-docs/scene-controller-api.yaml): OpenAPI specification
- [Scene Common](../scene_common/): Shared library documentation (geometry, MQTT, etc.)
- [Fast Geometry](../scene_common/fast_geometry/): C++ extension documentation
- [Testing Guide](../.github/instructions/testing.md): Test creation patterns
- [Python Conventions](../.github/instructions/python.md): Python coding standards
