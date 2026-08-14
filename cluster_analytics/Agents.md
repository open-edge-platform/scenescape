<!--
SPDX-License-Identifier: Apache-2.0
(C) 2026 Intel Corporation
-->

# Cluster Analytics Service - AI Agent Guide

## Service Overview

The **Cluster Analytics** service provides advanced object clustering, tracking, and behavioral analysis capabilities for Scenescape. It identifies spatial clusters of objects, tracks their evolution over time, analyzes geometric patterns, and classifies movement behaviors.

**Primary Purpose**: Transform individual object detections into meaningful group behaviors by identifying clusters, tracking their lifecycle, detecting geometric patterns, and analyzing movement dynamics.

**Status**: Production—build via `make cluster_analytics` or `make build-all`

## Architecture & Components

### Core Modules

1. **`cluster_analytics.py`**: CLI entrypoint
   - Parses CLI arguments (`--broker`, `--brokerauth`, `--cert`, `--rootcert`, `--webui`, `--webui-port`, `--webui-certfile`, `--webui-keyfile`)
   - Instantiates `ClusterAnalyticsContext` and calls `loop_forever()`
   - No clustering logic lives here

2. **`cluster_analytics_context.py`**: Service context and clustering engine
   - Loads `config.json` via `ClusterAnalyticsConfig`
   - Manages MQTT connection (subscribe / publish)
   - Runs DBSCAN per object category per frame
   - Integrates with `ClusterTracker` for UUID persistence
   - Exposes per-scene DBSCAN parameter override API for WebUI / future REST API
   - Optionally starts the WebUI thread

3. **`cluster_analytics_tracker.py`**: Greedy centroid tracker
   - `TrackedCluster` dataclass: `uuid`, `category`, `centroid`, `objects_count`, `shape_analysis`, `velocity_analysis`, `object_ids`, `dbscan_params`, `first_seen`, `last_seen`
   - `ClusterTracker(max_matching_distance=2.0, expiry_seconds=10.0)`
   - `tracker.update(scene_id, raw_detections, timestamp)` — greedy nearest-centroid matching per category
   - `tracker.get_clusters(scene_id)` — returns non-expired `TrackedCluster` list
   - No state machine, no confidence scoring, no scipy dependency

4. **`tools/webui/web_ui.py`**: Optional Flask+SocketIO WebUI
   - Enabled via `--webui` CLI flag
   - Real-time cluster visualization on HTTPS port 9443
   - Calls context methods to read/write per-scene DBSCAN overrides

### Key Features

**1. DBSCAN Clustering**

- Density-based spatial clustering with configurable `eps` and `min_samples`
- Category-specific parameters (e.g., different thresholds for people vs. vehicles)
- Handles noise and outliers automatically

**2. Cluster Tracking**

- Greedy nearest-centroid matching per category per frame
- Persistent UUIDs reused as long as centroid stays within `max_matching_distance`
- Clusters dropped after `expiry_seconds` without a match
- No state machine or confidence scoring

**3. Shape Detection**

- ML-based geometric pattern recognition
- Supported shapes: `circle`, `rectangle`, `line`, `irregular`
- Shape confidence scoring
- Shape evolution tracking over time

**4. Velocity Analysis**

- Movement pattern classification: `stationary`, `coordinated_parallel`, `converging`, `diverging`, `loosely_coordinated`, `chaotic`
- Average velocity vector, magnitude, direction, and coherence score computed per cluster

### Dependencies

- **Scene Common**: MQTT (`PubSub`), logging, geometry utilities
- **NumPy**: Numerical computations (no SciPy required)
- **scikit-learn**: DBSCAN implementation

## Communication Patterns

### MQTT Topics

**Subscribes**:

- `scenescape/regulated/scene/+` (`DATA_REGULATED`) — object detection data for all scenes

**Publishes**:

- `scenescape/analytics/clusters/{scene_id}` (`ANALYTICS_CLUSTERS`) — cluster analysis results

### Message Format

**Input** (`DATA_REGULATED`):

```json
{
  "name": "Retail",
  "timestamp": "2025-10-21T09:16:41.377Z",
  "objects": [
    {
      "id": "69de7c1c-21da-45bc-ae45-2f1d3d16d5b2",
      "category": "person",
      "translation": [10.5, 5.2, 0.0],
      "velocity": [0.1, -0.05, 0.0]
    }
  ]
}
```

**Output** (`ANALYTICS_CLUSTERS`):

```json
{
  "scene_id": "3bc091c7-e449-46a0-9540-29c499bca18c",
  "scene_name": "Retail",
  "timestamp": "2025-10-21T09:16:41.377Z",
  "clusters": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "category": "person",
      "objects_count": 5,
      "center_of_mass": { "x": 10.0, "y": 5.0 },
      "shape_analysis": { "shape": "circle", "size": { "radius": 0.4 } },
      "velocity_analysis": {
        "movement_type": "stationary",
        "average_velocity": [0.0, 0.0, 0.0],
        "velocity_magnitude": 0.0,
        "movement_direction_degrees": 0.0,
        "velocity_coherence": 0.0
      },
      "object_ids": ["69de7c1c-..."],
      "dbscan_params": { "eps": 2.0, "min_samples": 2, "category": "person" },
      "tracking": {
        "tracking_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "first_seen": 1729501599.234,
        "last_seen": 1729501601.734
      }
    }
  ],
  "summary": {
    "categories": ["person"],
    "total_objects": 5
  }
}
```

## Development Workflows

### Building the Service

```bash
# From root directory
make cluster_analytics                  # Build production image
make rebuild-cluster_analytics          # Clean + rebuild
make build-all                          # All services
# Demo image (WebUI included, for development/demo only)
make -C cluster_analytics build-demo
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

### CLI Arguments

| Argument           | Description                               |
| ------------------ | ----------------------------------------- |
| `--broker`         | MQTT broker hostname                      |
| `--brokerauth`     | Path to broker auth file                  |
| `--cert`           | Path to client certificate                |
| `--rootcert`       | Path to CA certificate                    |
| `--webui`          | Enable WebUI server (disabled by default) |
| `--webui-port`     | WebUI HTTPS port (default: 9443)          |
| `--webui-certfile` | TLS certificate for WebUI                 |
| `--webui-keyfile`  | TLS private key for WebUI                 |

### Configuration File Format

Located at `/app/config/config.json` in the container:

```json
{
  "dbscan": {
    "default": {
      "eps": 1,
      "min_samples": 3
    },
    "category_specific": {
      "person": { "eps": 2, "min_samples": 2 },
      "vehicle": { "eps": 4.0, "min_samples": 2 },
      "bicycle": { "eps": 1.5, "min_samples": 2 },
      "truck": { "eps": 5.0, "min_samples": 2 },
      "bus": { "eps": 6.0, "min_samples": 2 }
    }
  }
}
```

`default` is the fallback for any category not listed in `category_specific`.

## Code Patterns

### Instantiating the Context

```python
from cluster_analytics_context import ClusterAnalyticsContext

# Context wires MQTT + tracker + optional WebUI
context = ClusterAnalyticsContext(
    broker="broker.scenescape.intel.com",
    broker_auth="/run/secrets/controller.auth",
    cert=None,
    root_cert="/run/secrets/certs/scenescape-ca.pem",
    enable_webui=False,
)
context.loop_forever()  # Blocks; starts MQTT loop
```

### Using the Tracker Directly

```python
from cluster_analytics_tracker import ClusterTracker
import time

tracker = ClusterTracker(max_matching_distance=2.0, expiry_seconds=10.0)

# raw_detections: list of dicts from analyze_object_clusters()
tracker.update(scene_id="scene-abc", raw_detections=raw, timestamp=time.time())

for cluster in tracker.get_clusters("scene-abc"):
    print(cluster.uuid, cluster.category, cluster.centroid)
```

### Reading / Writing Per-Scene DBSCAN Overrides

```python
# Read effective params (user override → category config → default)
params = context.get_dbscan_params_for_category("person", scene_id="scene-abc")

# Read config-only defaults (ignores user overrides)
defaults = context.get_default_dbscan_params_for_category("person")

# Set per-scene override (e.g., from WebUI or future REST API)
context.set_user_dbscan_params_for_category("person", eps=3.0, min_samples=2, scene_id="scene-abc")

# Reset per-scene override back to config defaults
context.reset_user_dbscan_params_for_category("person", scene_id="scene-abc")
```

### Running DBSCAN Manually

```python
from sklearn.cluster import DBSCAN
import numpy as np

positions = np.array([[obj['translation'][0], obj['translation'][1]] for obj in objects])
clustering = DBSCAN(eps=2.0, min_samples=2).fit(positions)
# Labels: -1 = noise, 0..N = cluster index
for label in set(clustering.labels_) - {-1}:
    members = [obj for obj, lbl in zip(objects, clustering.labels_) if lbl == label]
```

## Common Tasks

### Adding a New Velocity Pattern

1. Edit `cluster_analytics_context.py` → `classify_movement_pattern()`
2. Add new pattern logic with a unique return string
3. Update tests in `tests/sscape_tests/cluster_analytics/test_velocity.py`

### Tuning DBSCAN Parameters

1. Edit `cluster_analytics/config/config.json`
2. Run unit tests: `pytest tests/sscape_tests/cluster_analytics/test_clustering.py -p no:django`
3. Rebuild image and verify with component tests

**Guidelines**:

- `eps`: Max distance between cluster members (larger = bigger clusters)
- `min_samples`: Minimum objects to form a cluster (larger = stricter)
- Per-category overrides apply automatically; `default` is the fallback

### Changing Tracker Sensitivity

Edit `ClusterTracker` instantiation in `cluster_analytics_context.py`:

```python
self.cluster_tracker = ClusterTracker(
    max_matching_distance=2.0,  # metres — increase if clusters drift between frames
    expiry_seconds=10.0         # seconds — increase to keep clusters alive during gaps
)
```

### Debugging Cluster Tracking Issues

1. Enable debug logging in the container: add `LOG_LEVEL=DEBUG` env var
2. Watch MQTT output: `mosquitto_sub -t 'scenescape/analytics/clusters/+' -v`
3. Check `max_matching_distance` (too small = new UUID every frame)
4. Check `expiry_seconds` (too small = clusters disappear between bursts)

5. Enable debug logging: `LOG_LEVEL=DEBUG`
6. Log cluster states and transitions
7. Visualize cluster centroids over time

## Integration Points

### Data Flow

```
Scene Controller
    → MQTT DATA_REGULATED (scenescape/regulated/scene/{id})
        → ClusterAnalyticsContext.process_scene_analytics()
            → analyze_object_clusters()  [DBSCAN per category]
            → ClusterTracker.update()    [UUID persistence]
            → _publishTrackedClusters()  [MQTT ANALYTICS_CLUSTERS]
```

### WebUI

- Flask+SocketIO server on HTTPS port 9443 (enabled with `--webui`)
- Real-time visualization of objects and clusters
- Per-scene DBSCAN parameter controls backed by `set_user_dbscan_params_for_category()`
- **Requires the demo image**: the production image does not include WebUI dependencies.
  Build with `make build-demo` in `cluster_analytics/`, then use `scenescape-cluster-analytics-demo` in docker-compose.

### Future REST API

- Per-scene DBSCAN override methods (`set_user_dbscan_params_for_category` etc.) are preserved for future REST API exposure

## File Structure

```
cluster_analytics/
├── Dockerfile
├── Makefile
├── README.md
├── Agents.md
├── requirements-runtime.txt
├── requirements-build.txt
├── src/
│   ├── cluster_analytics.py           # CLI entrypoint
│   ├── cluster_analytics_tracker.py   # Greedy centroid tracker
│   └── cluster_analytics_context.py   # DBSCAN + MQTT + config
├── config/
│   └── config.json                    # Default DBSCAN parameters
├── tests/
│   └── service/                       # Component tests (Docker)
│       ├── conftest.py
│       ├── test_clustering_pipeline.py
│       └── docker-compose.yaml
└── tools/
    └── webui/                         # Optional Flask+SocketIO WebUI
        ├── web_ui.py
        ├── templates/
        └── static/
```

Unit tests live outside the service directory at `tests/sscape_tests/cluster_analytics/`.

## Troubleshooting

### Common Issues

1. **No clusters detected**
   - Check `eps` in `config.json` (may be too small for the scene scale)
   - Verify `min_samples` is not higher than the typical group size
   - Check that objects have valid `translation` coordinates

2. **Too many small clusters**
   - Increase `eps` in `config.json` for the relevant category
   - Lower `min_samples` if appropriate

3. **Cluster UUID changes every frame**
   - Increase `max_matching_distance` in `ClusterTracker` instantiation
   - Cluster centroid may be jumping beyond the matching threshold

4. **Clusters disappear between frames**
   - Increase `expiry_seconds` in `ClusterTracker` instantiation
   - Check object detection rate vs. `expiry_seconds`

### Logs & Diagnostics

```bash
# Service logs
docker compose logs cluster-analytics --tail 100

# Watch MQTT cluster output
mosquitto_sub -t 'scenescape/analytics/clusters/+' -v

# Watch MQTT input
mosquitto_sub -t 'scenescape/regulated/scene/+' -v

# Performance monitoring
docker stats cluster-analytics
```

## Performance Considerations

### Optimization Notes

- DBSCAN scales O(n log n) with the sklearn implementation
- Tracker overhead is O(n) per category per frame (greedy linear scan)
- No historical data retained in tracker — memory footprint is bounded by active live clusters

## Testing Checklist

When modifying the service, verify:

- [ ] Unit tests pass: `make run_unit_tests`
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

- [Overview](../docs/user-guide/microservices/cluster-analytics/cluster-analytics.md): Comprehensive feature and algorithm documentation
- [Get Started](../docs/user-guide/microservices/cluster-analytics/get-started.md): Step-by-step usage guide
- [Build Instructions](../docs/user-guide/microservices/cluster-analytics/get-started/build-from-source.md): Deployment guide
- [Scene Common](../scene_common/): Shared geometry and tracking utilities
- [Testing Guide](../.github/skills/testing/SKILL.md): Test creation patterns
- [Python Conventions](../.github/skills/python/SKILL.md): Python coding standards
