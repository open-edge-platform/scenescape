<!--
SPDX-License-Identifier: Apache-2.0
(C) 2026 Intel Corporation
-->

# Cluster Analytics Service - AI Agent Guide

## Service Overview

The **Cluster Analytics** service provides advanced object clustering, tracking, and behavioral analysis capabilities for Intel® SceneScape. It identifies spatial clusters of objects, tracks their evolution over time, analyzes geometric patterns, and classifies movement behaviors.

**Primary Purpose**: Transform individual object detections into meaningful group behaviors by identifying clusters, tracking their lifecycle, detecting geometric patterns, and analyzing movement dynamics.

**Status**: Experimental—enabled via `make build-experimental` or `make build-all`

## Architecture & Components

### Core Modules

1. **`cluster_analytics.py`**: Main service controller
   - MQTT message handling
   - DBSCAN clustering algorithm implementation
   - Cluster lifecycle management (new, active, inactive, merged, split)
   - REST API for cluster queries
   - Integration with Scene Controller

2. **`cluster_analytics_tracker.py`**: Cluster tracking engine
   - Persistent cluster tracking across frames
   - State machine for cluster lifecycle
   - Cluster matching based on centroid proximity
   - Merge/split detection
   - Historical data management

3. **`cluster_analytics_context.py`**: Service configuration and state
   - Configuration loading from JSON
   - Category-specific DBSCAN parameters
   - Tracking thresholds and timeouts
   - Runtime state management

### Key Features

**1. DBSCAN Clustering**

- Density-based spatial clustering with configurable `eps` and `min_samples`
- Category-specific parameters (e.g., different thresholds for people vs. vehicles)
- Handles noise and outliers automatically

**2. Cluster Tracking**

- Unique cluster IDs maintained across frames
- State-based lifecycle: `new` → `active` → `inactive` (or `merged`/`split`)
- Centroid-based matching with configurable distance threshold
- Maximum unreliable time before cluster marked inactive

**3. Shape Detection**

- ML-based geometric pattern recognition
- Supported shapes: `circle`, `rectangle`, `line`, `irregular`
- Shape confidence scoring
- Shape evolution tracking over time

**4. Velocity Analysis**

- Movement pattern classification for clusters
- Patterns: `stationary`, `coordinated`, `converging`, `diverging`, `chaotic`
- Velocity vector computation from centroid movement
- Acceleration and direction change detection

### Dependencies

- **Scene Common**: MQTT/REST clients, geometry utilities, schema validation
- **NumPy/SciPy**: Numerical computations, spatial algorithms
- **scikit-learn**: DBSCAN implementation
- **Scene Controller**: Receives object detections, sends cluster results

## Communication Patterns

### MQTT Topics

**Subscribes**:

- `detector/<camera_id>`: Object detection messages from Scene Controller
- `cluster/request`: Explicit cluster analysis requests

**Publishes**:

- `cluster/result/<scene_id>`: Cluster analysis results with geometries and velocities
- `cluster/status`: Service status and diagnostics

### Message Format

**Input (Object Detections)**:

```json
{
  "frame_id": 12345,
  "timestamp": 1704902400.0,
  "objects": [
    {
      "object_id": "obj_001",
      "category": "person",
      "position": { "x": 10.5, "y": 5.2, "z": 0.0 },
      "confidence": 0.95
    }
  ]
}
```

**Output (Cluster Results)**:

```json
{
  "timestamp": 1704902400.0,
  "clusters": [
    {
      "cluster_id": "cluster_001",
      "category": "person",
      "state": "active",
      "centroid": { "x": 10.0, "y": 5.0, "z": 0.0 },
      "object_count": 5,
      "shape": "circle",
      "shape_confidence": 0.85,
      "velocity_pattern": "stationary",
      "bounding_box": { "x": 0.5, "y": 0.5, "width": 0.1, "height": 0.2 }
    }
  ]
}
```

## Development Workflows

### Building the Service

```bash
# From root directory
make cluster_analytics                  # Build image
make rebuild-cluster_analytics          # Clean + rebuild
make build-experimental                 # Build experimental services
make build-all                          # All services including experimental
```

### Testing

```bash
# Unit tests
make -C tests cluster-analytics-unit

# Functional tests (requires running containers)
SUPASS=<password> make setup_tests
make -C tests cluster-analytics-functional

# Specific test module
pytest tests/sscape_tests/cluster_analytics/test_tracker.py -v
```

### Running Locally

```bash
# Start with docker-compose
docker compose up -d cluster-analytics

# View logs
docker compose logs cluster-analytics -f

# Debug mode with verbose logging
docker compose up cluster-analytics -e LOG_LEVEL=DEBUG
```

## Key Configuration

### Environment Variables

- `MQTT_BROKER`: MQTT broker address (default: `mosquitto:8883`)
- `SCENE_CONTROLLER_URL`: REST endpoint for Scene Controller
- `CONFIG_FILE`: Path to configuration JSON
- `LOG_LEVEL`: `DEBUG`, `INFO`, `WARNING`, `ERROR`

### Configuration File Format

```json
{
  "clustering": {
    "default": {
      "eps": 2.0,
      "min_samples": 3
    },
    "person": {
      "eps": 1.5,
      "min_samples": 3
    },
    "vehicle": {
      "eps": 3.0,
      "min_samples": 2
    }
  },
  "tracking": {
    "max_distance": 5.0,
    "max_unreliable_time": 3.0,
    "min_frames_for_shape": 10
  },
  "shape_detection": {
    "enabled": true,
    "confidence_threshold": 0.7
  },
  "velocity_analysis": {
    "enabled": true,
    "stationary_threshold": 0.1,
    "coordinated_threshold": 0.3
  }
}
```

## Code Patterns

### Running Cluster Analysis

```python
from cluster_analytics import ClusterAnalytics
from cluster_analytics_context import ClusterAnalyticsContext

# Initialize service
config = ClusterAnalyticsContext(config_file="config/cluster_config.json")
service = ClusterAnalytics(
    mqtt_broker="mosquitto:8883",
    context=config
)

# Start listening for object detections
service.start()
```

### Custom Clustering

```python
from sklearn.cluster import DBSCAN
import numpy as np

# Extract object positions
positions = np.array([[obj.x, obj.y] for obj in objects])

# Run DBSCAN
clustering = DBSCAN(eps=2.0, min_samples=3)
labels = clustering.fit_predict(positions)

# Group objects by cluster
clusters = {}
for obj, label in zip(objects, labels):
    if label == -1:
        continue  # Noise point
    if label not in clusters:
        clusters[label] = []
    clusters[label].append(obj)
```

### Tracking Clusters Across Frames

```python
from cluster_analytics_tracker import ClusterTracker

tracker = ClusterTracker(max_distance=5.0, max_unreliable_time=3.0)

# Update with new clusters from current frame
current_clusters = [...]  # From DBSCAN
tracked_clusters = tracker.update(current_clusters, timestamp)

# Get active clusters
active = [c for c in tracked_clusters if c.state == "active"]

# Detect state changes
for cluster in tracked_clusters:
    if cluster.state == "split":
        print(f"Cluster {cluster.id} split into {cluster.split_into}")
    elif cluster.state == "merged":
        print(f"Cluster {cluster.id} merged from {cluster.merged_from}")
```

### Shape Detection

```python
from cluster_analytics import detect_shape

# Detect shape from cluster points
shape, confidence = detect_shape(cluster_points)

# Shape types: 'circle', 'rectangle', 'line', 'irregular'
if shape == "circle" and confidence > 0.8:
    print(f"High confidence circular cluster detected")
```

## Common Tasks

### Adding New Velocity Pattern

1. Edit `cluster_analytics.py` → `analyze_velocity()` function
2. Define new pattern logic (e.g., "orbiting", "oscillating")
3. Add pattern to enum/constants
4. Update documentation and schema
5. Add unit tests for new pattern

### Tuning Clustering Parameters

1. Edit configuration file or database
2. Test with sample data: `pytest tests/sscape_tests/cluster_analytics/test_clustering.py`
3. Visualize clusters to verify quality
4. Category-specific tuning (people vs. vehicles need different params)

**Tips**:

- `eps`: Controls maximum distance between cluster members (larger = bigger clusters)
- `min_samples`: Minimum objects to form cluster (larger = stricter clustering)
- Start conservative (small eps, higher min_samples) and relax as needed

### Debugging Cluster Tracking Issues

1. Enable debug logging: `LOG_LEVEL=DEBUG`
2. Log cluster states and transitions
3. Visualize cluster centroids over time
4. Check `max_unreliable_time` threshold (may be too aggressive)
5. Verify object ID consistency from detector

### Integrating Shape Detection Model

```python
# Replace heuristic shape detection with ML model
import torch
from shape_model import ShapeClassifier

model = ShapeClassifier.load("/models/shape_detector.pt")

def detect_shape_ml(cluster_points):
    # Convert to tensor
    points_tensor = torch.tensor(cluster_points, dtype=torch.float32)

    # Predict shape
    with torch.no_grad():
        shape_logits = model(points_tensor)
        shape_idx = torch.argmax(shape_logits)
        confidence = torch.softmax(shape_logits, dim=0)[shape_idx].item()

    shapes = ["circle", "rectangle", "line", "irregular"]
    return shapes[shape_idx], confidence
```

## Integration Points

### Scene Controller

- **Input**: Receives object detections via MQTT
- **Output**: Sends cluster analysis results back to Scene Controller
- **Flow**: Scene Controller tracks individual objects → Cluster Analytics groups them → Results feed back for scene understanding

### Manager Web UI

- Future: Visualization of cluster analytics
- Cluster heatmaps over time
- Shape and velocity pattern dashboards
- Configuration UI for DBSCAN parameters

### Mapping Service

- Potential integration: Use cluster patterns to identify landmarks
- Crowd density mapping
- Traffic flow analysis from vehicle clusters

## File Structure

```
cluster_analytics/
├── Dockerfile                          # Container build
├── Makefile                            # Build rules
├── README.md                           # Overview documentation
├── requirements-runtime.txt            # Python dependencies
├── requirements-build.txt              # Build-time dependencies
├── src/
│   ├── cluster_analytics.py           # Main service controller
│   ├── cluster_analytics_tracker.py   # Cluster tracking engine
│   └── cluster_analytics_context.py   # Configuration management
├── config/
│   └── cluster_config.json            # Default configuration
├── docs/
│   └── user-guide/
│       ├── overview.md                # Architecture documentation
│       ├── get-started.md             # Quick start guide
│       └── How-to-build-source.md     # Build instructions
└── tools/
    └── visualize_clusters.py          # Visualization utilities
```

## Troubleshooting

### Common Issues

1. **No clusters detected**
   - Check `eps` parameter (may be too small)
   - Verify `min_samples` not too high
   - Ensure objects actually close enough spatially
   - Debug: Log object positions to verify data

2. **Too many small clusters**
   - Increase `eps` to merge nearby objects
   - Decrease `min_samples` if appropriate
   - Check for noise in object positions

3. **Cluster IDs changing frequently**
   - Increase `max_distance` threshold in tracker
   - Extend `max_unreliable_time` to allow gaps
   - Verify object detection quality (jitter in positions)

4. **Shape detection inaccurate**
   - Increase `min_frames_for_shape` (need more data)
   - Check cluster size (too few points = unreliable shape)
   - Verify object positions are accurate

### Logs & Diagnostics

```bash
# Service logs
docker compose logs cluster-analytics --tail 100

# MQTT message debugging
docker compose exec mosquitto mosquitto_sub -t 'cluster/#' -v

# Performance monitoring
docker stats cluster-analytics

# Interactive debugging
docker compose exec cluster-analytics python -m pdb src/cluster_analytics.py
```

## Performance Considerations

### Optimization Strategies

1. **Spatial Indexing**: Use KD-tree for faster neighbor searches (already in DBSCAN)
2. **Frame Skipping**: Process every N frames instead of all frames
3. **Cluster Pruning**: Remove inactive clusters from tracking after timeout
4. **Incremental Updates**: Update clusters incrementally vs. full recomputation

### Scalability Limits

- **Object Count**: DBSCAN scales ~O(n log n) with spatial index
- **Cluster Count**: Tracking overhead grows linearly with active clusters
- **Historical Data**: Limit history depth to prevent memory bloat

## Testing Checklist

When modifying the service, verify:

- [ ] Unit tests pass: `make -C tests cluster-analytics-unit`
- [ ] DBSCAN produces expected clusters with test data
- [ ] Cluster tracking maintains IDs across frames
- [ ] State transitions (new → active → inactive) work correctly
- [ ] Merge/split detection functions properly
- [ ] Shape detection returns reasonable results
- [ ] Velocity patterns classified correctly
- [ ] MQTT messages validate against schema
- [ ] Service recovers from MQTT broker restart

## Research & Experimental Features

As an experimental service, cluster analytics includes:

- **Hierarchical Clustering**: Multi-level cluster hierarchy (clusters of clusters)
- **Temporal Pattern Mining**: Identify recurring cluster patterns over time
- **Anomaly Detection**: Flag unusual cluster behaviors
- **Predictive Tracking**: Forecast cluster movement
- **Social Force Models**: Model crowd dynamics using physics-based simulation

## Related Documentation

- [Overview](docs/user-guide/overview.md): Comprehensive feature and algorithm documentation
- [Get Started](docs/user-guide/get-started.md): Step-by-step usage guide
- [Build Instructions](docs/user-guide/How-to-build-source.md): Deployment guide
- [Scene Common](../scene_common/): Shared geometry and tracking utilities
- [Testing Guide](../.github/instructions/testing.md): Test creation patterns
- [Python Conventions](../.github/instructions/python.md): Python coding standards
