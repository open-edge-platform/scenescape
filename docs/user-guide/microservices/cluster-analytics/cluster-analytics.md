<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/scenescape/tree/release-2026.2.0/cluster_analytics">
     GitHub
  </a>
  <a class="icon_document" href="https://github.com/open-edge-platform/scenescape/blob/release-2026.2.0/cluster_analytics/README.md">
     Readme
  </a>
</div>
hide_directive-->

# Cluster Analytics Service

The Cluster Analytics service provides advanced object clustering and movement analysis capabilities for Scenescape using DBSCAN (Density-Based Spatial Clustering of Applications with Noise) algorithm combined with geometric shape detection and velocity pattern classification.

This service processes real-time object detection data from Scenescape scenes, applies machine learning-based clustering algorithms, and provides comprehensive analytics including:

- **Spatial Clustering**: Groups objects by proximity using DBSCAN algorithm with user-configurable parameters
- **Cluster Tracking**: Tracks clusters across frames with persistent UUIDs via greedy nearest-centroid matching
- **Shape Analysis**: Detects geometric patterns (circle, rectangle, line, irregular) with size measurements
- **Velocity Analysis**: Classifies movement patterns and tracks cluster dynamics

## Deployment

### Docker Deployment (Recommended)

The cluster analytics service is included in the extended Scenescape demo docker-compose stack:

```bash
SUPASS=admin123 make
SUPASS=admin123 make demo-all
```

### Build from Source

Alternatively, see how to [Build from Source](./get-started/build-from-source.md).

## Architecture

### Data Flow Diagram

![Data Flow](../../_assets/microservices/microsvc-cluster-analytics-dataflow.svg "cluster analytics data flow")

### **DBSCAN Clustering Configuration**

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

### **Cluster Tracking System**

The service uses a lightweight greedy nearest-centroid matcher that assigns persistent UUIDs to clusters across frames. There is no state machine or confidence scoring — clusters are matched and published from the first frame.

#### Tracker Configuration Parameters

| Parameter               | Default | Description                                                               |
| ----------------------- | ------- | ------------------------------------------------------------------------- |
| `max_matching_distance` | 2.0 m   | Maximum centroid distance to match a new detection to an existing cluster |
| `expiry_seconds`        | 10.0 s  | Seconds after `last_seen` before a cluster UUID is dropped                |

#### Matching Algorithm

For each frame, per category:

1. Compare each new detection centroid against all live clusters of the same category
2. Greedily assign the nearest cluster within `max_matching_distance` and reuse its UUID
3. Unmatched detections receive a new UUID
4. Clusters not updated within `expiry_seconds` are discarded

## **WebUI Features and Real-time Visualization**

The integrated WebUI provides a comprehensive interface for cluster analysis monitoring and configuration:

### **Interactive Visualization**

- **Real-time Canvas**: Live updating visualization of objects and clusters
- **Pan and Zoom**: Navigate through scene data with mouse controls
- **Object Display**: Individual objects colored by cluster assignment
- **Cluster Shapes**: Visual representation of detected cluster geometries
- **Movement Vectors**: Optional display of cluster movement with adjustable scaling
- **Auto-fit**: Automatic view adjustment to focus on current scene data

### **Dynamic Parameter Configuration**

- **Per-Category Controls**: Independent parameter adjustment for each object category
- **Real-time Updates**: Changes apply immediately with automatic re-clustering
- **Scene-Specific Settings**: Each scene maintains its own parameter configuration
- **Reset to Defaults**: Quick restoration of default parameters per category
- **Visual Feedback**: Immediate visualization of parameter change effects

### **Scene Management**

- **Multi-Scene Support**: Switch between available scenes dynamically
- **Auto-Discovery**: Scenes are automatically discovered from MQTT traffic
- **Current Data Focus**: Always displays current state without historic accumulation
- **Object Count Display**: Real-time object and cluster statistics

### **Advanced Controls**

- **Refresh Rate**: Configurable from real-time to custom intervals
- **Movement Vector Scaling**: Adjustable visualization scale for velocity vectors
- **Connection Status**: Live MQTT connection monitoring
- **Parameter Validation**: Intelligent validation based on actual scene data

### **Insufficient Points Handling**

- **Individual Object Coloring**: Objects are colored by category when clusters cannot be formed
- **Clear Messaging**: Visual indication when clustering is not possible
- **Dynamic Thresholds**: Uses user-configured min_samples rather than global defaults

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

The Cluster Analytics service publishes optimized cluster metadata in batch format. **Note**: Scene identification is extracted from topic structure, not payload content.

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

## Production Data Analysis

### Real Deployment Performance

Based on actual production deployment on `broker.scenescape.intel.com`:

- **Active Scenes**: "Queuing" (`302cf49a-97ec-402d-a324-c5077b280b7b`), "Retail" (`3bc091c7-e449-46a0-9540-29c499bca18c`)
- **Object Volume**: 62 person objects per frame in busy queuing scenarios
- **Cluster Formation**: Typically 2 clusters formed (42-43 objects in main cluster, 4 objects in secondary cluster)
- **Noise Points**: 15-17 unclustered objects (24-27% noise ratio)
- **Shape Patterns**: 100% circle formations observed in production
- **Movement Types**: Mix of "chaotic" (main clusters) and "stationary" (small clusters)

### Performance Characteristics

- **Processing Speed**: Real-time analysis of 60+ objects per frame
- **Network Connectivity**: Reliable MQTT connectivity to production broker
- **Shape Detection**: Consistent circle detection with radius measurements 0.16-0.87 meters
- **Velocity Analysis**: Accurate movement classification with coherence measurements

## Usage Examples

### Real-time Monitoring

Subscribe to the ANALYTICS_CLUSTERS topic to receive live cluster updates:

```bash
mosquitto_sub -h broker.scenescape.intel.com -t "scenescape/analytics/clusters/+" -v
```

### Processing Cluster Data

Example Python code to process cluster metadata with tracking information:

```python
import json
import paho.mqtt.client as mqtt

def on_message(client, userdata, message):
    try:
        cluster_batch = json.loads(message.payload.decode())

        scene_name = cluster_batch['scene_name']
        scene_id = cluster_batch['scene_id']
        total_clusters = len(cluster_batch['clusters'])

        print(f"\n=== Scene: {scene_name} ({scene_id}) ===")
        print(f"Total Clusters: {total_clusters}")

        # Process individual clusters
        for cluster in cluster_batch['clusters']:
            cluster_id = cluster['id']
            category = cluster['category']
            object_count = cluster['objects_count']

            # Tracking information
            tracking = cluster['tracking']
            first_seen = tracking['first_seen']
            last_seen = tracking['last_seen']

            print(f"\n--- Cluster {cluster_id[:8]}... ---")
            print(f"  Category: {category}")
            print(f"  Objects: {object_count}")
            print(f"  First seen: {first_seen}")
            print(f"  Last seen: {last_seen}")

            # Movement and shape analysis
            movement_type = cluster['velocity_analysis']['movement_type']
            shape = cluster['shape_analysis']['shape']

            print(f"  Movement: {movement_type}")
            print(f"  Shape: {shape}")

            # Shape-specific measurements
            if shape == "circle":
                radius = cluster['shape_analysis']['size']['radius']
                print(f"  Circle radius: {radius:.2f}m")
            elif shape == "rectangle":
                width = cluster['shape_analysis']['size']['width']
                height = cluster['shape_analysis']['size']['height']
                print(f"  Rectangle: {width:.2f}m x {height:.2f}m")

    except Exception as e:
        print(f"Error processing cluster data: {e}")
        import traceback
        traceback.print_exc()

client = mqtt.Client()
client.on_message = on_message
client.connect("broker.scenescape.intel.com", 1883, 60)
client.subscribe("scenescape/analytics/clusters/+")
client.loop_forever()
```

## **Cluster Tracking Algorithm**

### Overview

The Cluster Analytics service uses a greedy nearest-centroid matcher to maintain persistent cluster identities across video frames. Clusters are matched and published from the first frame — no warmup or state-machine confidence build-up is required.

### Matching Algorithm

For each incoming frame, per object category:

1. Retrieve all live clusters for the scene and category
2. For each new DBSCAN detection, find the nearest live cluster centroid
3. If the distance is within `max_matching_distance` (default 2.0 m), reuse that cluster's UUID
4. If no live cluster is within range, assign a new UUID
5. Live clusters not matched within `expiry_seconds` (default 10.0 s) are discarded

```python
# Simplified greedy matching per category
for detection in new_detections:
    nearest = min(live_clusters, key=lambda c: distance(c.centroid, detection.centroid))
    if distance(nearest.centroid, detection.centroid) <= max_matching_distance:
        nearest.uuid  # reuse existing UUID
    else:
        str(uuid4())  # new UUID
```

### UUID Persistence

Each cluster carries a UUID (`tracking_id`) that persists as long as the cluster keeps being matched within `max_matching_distance`. The UUID survives temporary noise or brief frame gaps up to `expiry_seconds`.

### Cluster Expiry

A cluster is removed when `current_time - last_seen > expiry_seconds`. There is no archival or staged removal — clusters are either live or gone.

## DBSCAN Noise Point Explanation

In the DBSCAN clustering algorithm, **noise points** are objects that do not belong to any cluster. Understanding noise points is important for interpreting analytics results in the Cluster Analytics microservice.

### DBSCAN Algorithm Overview

DBSCAN (Density-Based Spatial Clustering of Applications with Noise) classifies each data point as one of:

- **Core points**: Have at least `min_samples` neighbors within `eps` distance.
- **Border points**: Are within `eps` distance of a core point but do not have enough neighbors to be core points themselves.
- **Noise points**: Are neither core nor border points—these are isolated from other points.

### Noise Points in Cluster Analytics

In this service, noise points are objects that:

- Are farther than the configured `eps` distance (e.g., 1.5 meters) from any other object of the same category.
- Do not have enough nearby neighbors to form a cluster (fewer than `min_samples`).

**Example Scenarios:**

- **Queuing Scene**:
  - 5 people detected.
  - 3 people stand close together (within 1.5m): form 1 cluster.
  - 2 people stand alone, each more than 1.5m from others: these are noise points.
- **Retail Scene**:
  - 4 people detected.
  - 2 people are near each other: form 1 cluster.
  - 2 people are isolated: noise points.

### Code Representation

In DBSCAN output, objects labeled with `-1` are noise points. These represent people or objects that are spatially isolated and do not form meaningful groups with others of the same category.

### Why Noise Points Matter

Identifying noise points helps distinguish between:

- **Clustered behavior**: People or objects grouping together.
- **Individual behavior**: People or objects standing alone or isolated.

This distinction is valuable for analytics, enabling insights into both group dynamics and solitary activity within a scene.

### Logging Benefits

- **Reduced Log Volume**: Eliminates verbose JSON serialization in production
- **Performance**: Avoids expensive string formatting when not needed
- **Operational**: Clear cluster summaries for monitoring and alerting
- **Debugging**: Full metadata available when debug logging is enabled

## Contributing

When contributing to the Cluster Analytics service:

1. **Algorithm Improvements**: Enhance clustering accuracy or add new shape detection patterns
2. **Performance Optimization**: Optimize processing speed for high-volume scenarios
3. **New Movement Patterns**: Add additional velocity analysis classifications
4. **Testing**: Include unit tests for clustering and shape detection algorithms

## License

This project is licensed under the Apache 2.0 License. See the LICENSE file for details.

<!--hide_directive
:::{toctree}
:hidden:

get-started.md

:::
hide_directive-->
