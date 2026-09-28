# How It Works

## Architecture

### Data Flow Diagram

![Data Flow](../../_assets/microservices/microsvc-cluster-analytics-dataflow.svg "cluster analytics data flow")

### DBSCAN Clustering Configuration

#### User-Configurable Parameters

The `config.json` file allows customization of DBSCAN clustering parameters:

- **`eps`** - Maximum distance (in meters) between objects to be considered in the same cluster
- **`min_samples`** - Minimum number of objects required to form a cluster

These parameters can be configured globally (default) or per object category.

#### Configuration File Structure

The service uses a `config.json` file located in the `config/` directory:

```json
{
  "dbscan": {
    "default": {
      "eps": 1,
      "min_samples": 3
    },
    "category_specific": {
      "person": {
        "eps": 2,
        "min_samples": 2
      },
      "vehicle": {
        "eps": 4.0,
        "min_samples": 2
      },
      "bicycle": {
        "eps": 1.5,
        "min_samples": 2
      },
      "motorcycle": {
        "eps": 2.5,
        "min_samples": 2
      },
      "truck": {
        "eps": 5.0,
        "min_samples": 2
      },
      "bus": {
        "eps": 6.0,
        "min_samples": 2
      }
    }
  }
}
```

#### Parameter Descriptions

- **`default`**: Fallback parameters for object categories not explicitly configured
- **`category_specific`**: Per-category parameters optimized for different object types:
  - `person` - Optimized for people clustering (social distancing, queues)
  - `vehicle` - Optimized for vehicle parking, traffic clusters
  - `bicycle` - Optimized for bike racks, group riding
  - `motorcycle` - Moderate spacing for motorcycle clusters
  - `truck` - Large vehicle spacing requirements
  - `bus` - Bus stops, depot formations

### Shape Detection and Analysis

- **ML-based Shape Classification**: Detects geometric patterns using feature extraction
- **Size Calculations**: Provides precise measurements for each detected shape type
- **Supported Shapes**:
  - **Circle**: radius, diameter, area, circumference
  - **Rectangle**: width, height, area, perimeter, corner points
  - **Line**: length, endpoints, width spread
  - **Irregular**: bounding box dimensions, point spread

#### Shape Detection Logic

![Shape Detection Logic](../../_assets/microservices/microsvc-cluster-analytics-shape-det-logic.svg "shape detection logic")

### Velocity Analysis and Movement Patterns

- **Movement Classification**: 6 distinct movement patterns
- **Velocity Statistics**: Comprehensive speed and direction analysis
- **Pattern Types**:
  - `stationary` - Objects with minimal movement
  - `coordinated_parallel` - Synchronized movement in same direction
  - `converging` - Objects moving toward cluster center
  - `diverging` - Objects moving away from cluster center
  - `loosely_coordinated` - Some coordination but not highly synchronized
  - `chaotic` - Random or unpredictable movement patterns

#### Velocity Analysis Logic

![Velocity Analysis Logic](../../_assets/microservices/microsvc-cluster-analytics-velocity-logic.svg "velocity analysis logic")

## Category-Specific Clustering

The service optimizes DBSCAN parameters based on object categories, providing more accurate clustering for different object types.

### Benefits

- **Optimized Parameters**: Each object type uses clustering parameters optimized for its spatial characteristics
- **Better Accuracy**: Improved clustering accuracy by considering object-specific grouping behaviors
- **Automatic Selection**: Parameters are selected based on detected object category
- **Fallback Support**: Unknown categories use sensible default parameters

### Category Optimization Examples

| Category     | eps (meters) | min_samples | Rationale                                |
| ------------ | ------------ | ----------- | ---------------------------------------- |
| `person`     | 2.0          | 2           | Social distancing, queue formations      |
| `vehicle`    | 4.0          | 2           | Parking lots, traffic clusters           |
| `bicycle`    | 1.5          | 2           | Bike racks, tight group riding           |
| `motorcycle` | 2.5          | 2           | Moderate spacing for motorcycle clusters |
| `truck`      | 5.0          | 2           | Large vehicle spacing requirements       |
| `bus`        | 6.0          | 2           | Bus stops, depot formations              |
| `default`    | 1.0          | 3           | Fallback for unknown categories          |

### Usage in Analysis

The service automatically applies appropriate parameters when processing each object category, with user customizations taking precedence:

```python
# Dynamic parameter selection with user overrides
for category, objects in objects_by_category.items():
    # Get user-configured parameters for this scene and category
    dbscan_params = self.get_dbscan_params_for_category(category, scene_id)
    clustering = DBSCAN(eps=dbscan_params['eps'],
                       min_samples=dbscan_params['min_samples'])
```

### Cluster Tracking Algorithm

The service uses a lightweight greedy nearest-centroid matcher that assigns persistent UUIDs
to clusters across frames. There is no state machine or confidence scoring — clusters are
matched and published from the first frame.

#### Tracker Configuration Parameters

| Parameter               | Default | Description                                                               |
| ----------------------- | ------- | ------------------------------------------------------------------------- |
| `max_matching_distance` | 2.0 m   | Maximum centroid distance to match a new detection to an existing cluster |
| `expiry_seconds`        | 10.0 s  | Seconds after `last_seen` before a cluster UUID is dropped                |

#### Matching Algorithm

For each incoming frame, per object category:

1. Retrieve non-expired live clusters for the scene and category.
2. For each new DBSCAN detection, find the nearest unmatched live cluster centroid.
3. If the distance is within `max_matching_distance` (default 2.0 m), reuse that cluster's UUID.
4. If no live cluster is within range, assign a new UUID.
5. Discard clusters whose `last_seen` exceeds `expiry_seconds` (default 10.0 s).

```python
# Simplified greedy matching per category
for detection in new_detections:
    nearest = min(live_clusters, key=lambda c: distance(c.centroid, detection.centroid))
    if distance(nearest.centroid, detection.centroid) <= max_matching_distance:
        nearest.uuid  # reuse existing UUID
    else:
        str(uuid4())  # new UUID
```

#### UUID Persistence

Each cluster carries a UUID (`tracking_id`) that persists as long as the cluster keeps being matched within `max_matching_distance`. The UUID survives temporary noise or brief frame gaps up to `expiry_seconds`.

#### Cluster Expiry

A cluster is removed when `current_time - last_seen > expiry_seconds`. There is no archival or staged removal — clusters are either live or gone.

## Additional Resources

- [Cluster Analytics Payload Reference](./analytics-payload-reference.md)
- [DBSCAN Noise Points](./dbscan-noise-points.md)
