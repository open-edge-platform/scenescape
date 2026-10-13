# Analytics Event Payload Reference

This article provides a reference for the analytics event payload structure used by the
Cluster Analytics service.

## MQTT Topics and Data Flow

### Input Topics

- **Topic**: `scenescape/regulated/scene/{scene_id}`
- **Purpose**: Receives object detection data from Scenescape scenes
- **Format**: JSON with objects array and scene metadata
- **Contains**: Scene name, timestamp, object detections with world coordinates

### Output Topics

- **Topic**: `scenescape/analytics/clusters/{scene_id}`
- **Purpose**: Publishes cluster analysis results
- **QoS**: 1 (at least once delivery)
- **Optimized Structure**: Contains only cluster data without redundant scene metadata

### Topic Structure Changes

**Recent Optimization**: Scene identification is now derived from topic structure rather than payload content:

- **Scene ID**: Extracted from topic path (`{scene_id}` component)
- **Scene Name**: Retrieved from DATA_REGULATED topic
- **Cluster Data**: Published to ANALYTICS_CLUSTERS contains only analysis results

## Output Data Structure

The Cluster Analytics service publishes optimized cluster metadata in batch format.

> **Note:** Scene identification is extracted from topic structure, not payload content.

### Cluster Batch Format

```json
{
  "scene_id": "3bc091c7-e449-46a0-9540-29c499bca18c",
  "scene_name": "Retail",
  "timestamp": "2025-10-21T09:16:41.377Z",
  "clusters": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "category": "person",
      "objects_count": 8,
      "center_of_mass": {
        "x": 4.291512867202579,
        "y": 4.934464049998539
      },
      "shape_analysis": {
        "shape": "circle",
        "size": {
          "radius": 0.38788961696255303,
          "diameter": 0.7757792339251061,
          "area": 0.4726788625738194,
          "circumference": 2.437182342106631
        }
      },
      "velocity_analysis": {
        "movement_type": "chaotic",
        "average_velocity": [-0.19217192568910546, -0.0763952946379476, 0.0],
        "velocity_magnitude": 0.20680012104899237,
        "movement_direction_degrees": -158.32038869788497,
        "velocity_coherence": 0.0
      },
      "object_ids": [
        "69de7c1c-21da-45bc-ae45-2f1d3d16d5b2",
        "5baec5fa-c961-4dc0-a254-f1f614292619",
        "bf1923d8-ac12-4042-9e76-9b57b351efcb",
        "e6333708-3793-4e44-9b29-e1b7e0e7977c",
        "d9b6d6a9-d390-47a4-a9b8-95af121103ca",
        "9be324af-c0a5-4495-bae6-33d251e88366",
        "166ba387-9b4e-406d-b236-a30bb274a800",
        "71a1b1f6-8e14-4a22-a656-011fa4405c43"
      ],
      "dbscan_params": {
        "eps": 0.5,
        "min_samples": 3,
        "category": "person"
      },
      "tracking": {
        "tracking_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "first_seen": 1729501599.234,
        "last_seen": 1729501601.734
      }
    }
  ],
  "summary": {
    "categories": ["person"],
    "total_objects": 8
  }
}
```

## Field Descriptions

### Batch-Level Fields

| Field                   | Type    | Description                                    |
| ----------------------- | ------- | ---------------------------------------------- |
| `scene_id`              | String  | Unique scene identifier (UUID)                 |
| `scene_name`            | String  | Human-readable scene name                      |
| `timestamp`             | String  | ISO 8601 timestamp when clusters were detected |
| `clusters`              | Array   | Array of individual cluster objects            |
| `summary.categories`    | Array   | List of object categories that formed clusters |
| `summary.total_objects` | Integer | Total objects across all clusters              |

### Individual Cluster Fields

| Field           | Type    | Description                                       |
| --------------- | ------- | ------------------------------------------------- |
| `id`            | String  | Unique persistent cluster UUID                    |
| `category`      | String  | Object detection category (person, vehicle, etc.) |
| `objects_count` | Integer | Number of objects forming the cluster             |
| `object_ids`    | Array   | List of object UUIDs that form this cluster       |
| `dbscan_params` | Object  | DBSCAN parameters used for this cluster           |
| `tracking`      | Object  | Temporal tracking metadata (see below)            |

### Spatial Information

| Field              | Type  | Description                                          |
| ------------------ | ----- | ---------------------------------------------------- |
| `cluster_center.x` | Float | X coordinate of cluster centroid (world coordinates) |
| `cluster_center.y` | Float | Y coordinate of cluster centroid (world coordinates) |

### Shape Analysis

| Field                  | Type   | Description                                                     |
| ---------------------- | ------ | --------------------------------------------------------------- |
| `shape_analysis.shape` | String | Detected shape type: `circle`, `rectangle`, `line`, `irregular` |
| `shape_analysis.size`  | Object | Shape-specific measurements (varies by shape type)              |

#### Shape-Specific Size Fields

**Circle:**

- `radius` - Circle radius in meters
- `diameter` - Circle diameter in meters
- `area` - Circle area in square meters
- `circumference` - Circle circumference in meters

**Rectangle:**

- `width` - Rectangle width in meters
- `height` - Rectangle height in meters
- `area` - Rectangle area in square meters
- `perimeter` - Rectangle perimeter in meters
- `corner_points` - Array of [x,y] corner coordinates

**Line:**

- `length` - Line length in meters
- `endpoints` - Array of two [x,y] endpoint coordinates
- `width_spread` - Standard deviation of perpendicular distances

**Irregular:**

- `bounding_width` - Bounding box width in meters
- `bounding_height` - Bounding box height in meters
- `bounding_area` - Bounding box area in square meters
- `point_spread` - Standard deviation of distances from centroid

### Velocity Analysis

| Field                        | Type         | Description                                 |
| ---------------------------- | ------------ | ------------------------------------------- |
| `movement_type`              | String       | Classified movement pattern                 |
| `average_velocity`           | Array[Float] | [vx, vy, vz] average velocity vector in m/s |
| `velocity_magnitude`         | Float        | Average speed magnitude in m/s              |
| `movement_direction_degrees` | Float        | Movement direction in degrees (-180 to 180) |
| `velocity_coherence`         | Float        | Movement synchronization measure (0-1)      |

### Tracking Metadata

| Field                  | Type   | Description                            |
| ---------------------- | ------ | -------------------------------------- |
| `tracking.tracking_id` | String | Persistent cluster UUID (same as `id`) |
| `tracking.first_seen`  | Float  | Unix timestamp of first detection      |
| `tracking.last_seen`   | Float  | Unix timestamp of last detection       |

### Movement Pattern Classifications

| Pattern                | Description             | Criteria                                     |
| ---------------------- | ----------------------- | -------------------------------------------- |
| `stationary`           | Minimal movement        | Average speed < 0.1 m/s                      |
| `coordinated_parallel` | Synchronized movement   | Velocity coherence > 0.3                     |
| `converging`           | Moving toward center    | >60% objects moving toward cluster center    |
| `diverging`            | Moving away from center | >60% objects moving away from cluster center |
| `loosely_coordinated`  | Some coordination       | Velocity coherence 0.2-0.3                   |
| `chaotic`              | Random movement         | Low velocity coherence, mixed directions     |

### Administrative Fields

| Field                       | Type          | Description                                             |
| --------------------------- | ------------- | ------------------------------------------------------- |
| `object_ids`                | Array[String] | List of individual object IDs in the cluster            |
| `dbscan_params.eps`         | Float         | DBSCAN epsilon parameter used for this category         |
| `dbscan_params.min_samples` | Integer       | DBSCAN minimum samples parameter used for this category |
| `dbscan_params.category`    | String        | Object category for which parameters were optimized     |

## Additional Resources

- [Cluster Analytics How It Works](./how-it-works.md)
- [DBSCAN Noise Points](./dbscan-noise-points.md)
