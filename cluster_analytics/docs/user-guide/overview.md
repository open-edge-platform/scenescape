# Cluster Analytics Microservice - Intel® SceneScape

The Cluster Analytics microservice provides advanced object clustering and movement analysis capabilities for Intel® SceneScape using DBSCAN (Density-Based Spatial Clustering of Applications with Noise) algorithm combined with geometric shape detection and velocity pattern classification.

## Overview

This service processes real-time object detection data from SceneScape scenes, applies machine learning-based clustering algorithms, and publishes comprehensive analytics metadata including:

- **Spatial Clustering**: Groups objects by proximity using DBSCAN algorithm
- **Shape Analysis**: Detects geometric patterns (circle, rectangle, line, irregular) with size measurements
- **Velocity Analysis**: Classifies movement patterns and provides velocity statistics
- **Real-time Publishing**: Streams results via MQTT to `ANALYTICS_CLUSTERS` topic

## Features

### 🔍 DBSCAN Clustering

- **Configurable Parameters**:
  - `eps=1.5m` (default) - Maximum distance between objects to be considered in same cluster
  - `min_samples=3` (default) - Minimum objects required to form a cluster
- **World Coordinate System**: Uses translation coordinates for accurate spatial analysis
- **Category-based Clustering**: Analyzes objects grouped by detection category (person, vehicle, etc.)

#### Configuration Parameters

Category-specific DBSCAN parameters are automatically selected based on object type for optimal clustering:

```python
# Category-Specific DBSCAN Parameters
CATEGORY_DBSCAN_PARAMS = {
  'person': {
    'eps': 0.5,        # People clustering distance (social distancing, queues)
    'min_samples': 3   # Minimum 3 people for meaningful cluster
  },
  'vehicle': {
    'eps': 4.0,        # Vehicle clustering distance (parking, traffic jams)
    'min_samples': 2   # Even 2 vehicles can form significant cluster (convoy, parking)
  },
  'bicycle': {
    'eps': 1.5,        # Bicycles cluster more tightly (bike racks, group riding)
    'min_samples': 2   # 2 bicycles can form a cluster
  },
  'motorcycle': {
    'eps': 2.5,        # Motorcycles have moderate clustering distance
    'min_samples': 2   # 2 motorcycles can form a cluster
  },
  'truck': {
    'eps': 5.0,        # Trucks need large clustering distance due to size
    'min_samples': 2   # 2 trucks can form a significant cluster
  },
  'bus': {
    'eps': 6.0,        # Buses need very large clustering distance
    'min_samples': 2   # 2 buses form significant cluster (bus stops, depots)
  }
}

# Default parameters for unknown categories
DEFAULT_DBSCAN_EPS = 1.5
DEFAULT_DBSCAN_MIN_SAMPLES = 3
```

### 📐 Shape Detection & Analysis

- **ML-based Shape Classification**: Detects geometric patterns using feature extraction
- **Size Calculations**: Provides precise measurements for each detected shape type
- **Supported Shapes**:
  - **Circle**: radius, diameter, area, circumference
  - **Rectangle**: width, height, area, perimeter, corner points
  - **Line**: length, endpoints, width spread
  - **Irregular**: bounding box dimensions, point spread

#### Configuration Parameters

```python
# Shape Detection Thresholds
SHAPE_VARIANCE_THRESHOLD = 0.5              # Circle vs rectangle classification
QUADRANT_ANGLE = np.pi / 2                  # 90 degrees - rectangle corner detection
ANGLE_DISTRIBUTION_THRESHOLD = 0.5          # Uniform angle distribution in circles
LINEAR_FORMATION_AREA_THRESHOLD = 0.5       # Area threshold for line detection

# Movement Analysis Thresholds
ALIGNMENT_THRESHOLD = 0.5                   # Movement alignment detection
CONVERGENCE_DIVERGENCE_RATIO_THRESHOLD = 0.6 # Convergence/divergence detection
```

#### Shape Detection Logic

```mermaid
flowchart TD
    A[Cluster Points Input] --> B{Sufficient Points?}
    B -->|< 3 points| C[Insufficient Points]
    B -->|≥ 3 points| D[Calculate Features]

    D --> E[Extract Distance & Angle Features]
    E --> F[Calculate Centroid]
    F --> G[Measure Distance Variance]

    G --> H{Distance Variance < 0.5?}
    H -->|Yes| I[Circle Formation]
    H -->|No| J{Exactly 4 Points?}

    J -->|Yes| K[Check Quadrant Distribution]
    K --> L{≥ 3 Quadrants?}
    L -->|Yes| M[Rectangle Formation]
    L -->|No| N[Continue Analysis]

    J -->|No| O{≥ 5 Points?}
    O -->|Yes| P[Analyze Angle Distribution]
    P --> Q{Uniform Distribution?}
    Q -->|Yes| R[Large Circle Formation]
    Q -->|No| S[Check Linear Formation]

    S --> T{Low Triangle Areas?}
    T -->|Yes| U[Line Formation]
    T -->|No| V[Irregular Shape]

    O -->|No| N
    N --> S

    %% Shape calculations
    I --> I1[Calculate: radius, diameter, area, circumference]
    M --> M1[Calculate: width, height, area, perimeter, corners]
    R --> R1[Calculate: radius, diameter, area, circumference]
    U --> U1[Calculate: length, endpoints, width spread]
    V --> V1[Calculate: bounding box, point spread]
```

### 🏃 Velocity Analysis & Movement Patterns

- **Movement Classification**: 6 distinct movement patterns
- **Velocity Statistics**: Comprehensive speed and direction analysis
- **Pattern Types**:
  - `stationary` - Objects with minimal movement
  - `coordinated_parallel` - Synchronized movement in same direction
  - `converging` - Objects moving toward cluster center
  - `diverging` - Objects moving away from cluster center
  - `loosely_coordinated` - Some coordination but not highly synchronized
  - `chaotic` - Random or unpredictable movement patterns

#### Configuration Parameters

```python
# Velocity Analysis
STATIONARY_THRESHOLD = 0.1          # Speed threshold for stationary classification (m/s)
VELOCITY_COHERENCE_THRESHOLD = 0.3  # Threshold for coordinated movement detection
```

#### Velocity Analysis Logic

```mermaid
graph TD
    A[Velocity Analysis] --> B{Speed Check}
    B -->|< 0.1 m/s| C[Stationary]
    B -->|> 0.1 m/s| D{Coherence Check}
    D -->|High Coherence| E[Coordinated Parallel]
    D -->|Low Coherence| F{Direction Analysis}
    F -->|Toward Center| G[Converging]
    F -->|Away from Center| H[Diverging]
    F -->|Mixed| I[Chaotic]
```

## 🎯 Category-Specific Clustering

The service automatically optimizes DBSCAN parameters based on object categories, providing more accurate clustering for different object types:

### Benefits

- **Optimized Parameters**: Each object type uses clustering parameters optimized for its spatial characteristics
- **Better Accuracy**: Improved clustering accuracy by considering object-specific grouping behaviors
- **Automatic Selection**: Parameters are automatically selected based on detected object category
- **Fallback Support**: Unknown categories use sensible default parameters

### Category Optimization Examples

| Category     | eps (meters) | min_samples | Rationale                                |
| ------------ | ------------ | ----------- | ---------------------------------------- |
| `person`     | 0.5          | 3           | Social distancing, queue formations      |
| `vehicle`    | 4.0          | 2           | Parking lots, traffic clusters           |
| `bicycle`    | 1.5          | 2           | Bike racks, tight group riding           |
| `motorcycle` | 2.5          | 2           | Moderate spacing for motorcycle clusters |
| `truck`      | 5.0          | 2           | Large vehicle spacing requirements       |
| `bus`        | 6.0          | 2           | Bus stops, depot formations              |

### Usage in Analysis

The service automatically applies appropriate parameters when processing each object category:

```python
# Automatic parameter selection example
for category, objects in objects_by_category.items():
    dbscan_params = self.get_dbscan_params_for_category(category)
    clustering = DBSCAN(eps=dbscan_params['eps'],
                       min_samples=dbscan_params['min_samples'])
```

## MQTT Topics

### Input

- **Topic**: `scenescape/regulated/scene/{scene_id}`
- **Purpose**: Receives object detection data from SceneScape scenes
- **Format**: JSON with objects array containing detection results

### Output

- **Topic**: `scenescape/analytics/clusters/{scene_id}`
- **Purpose**: Publishes cluster analysis metadata
- **QoS**: 1 (at least once delivery)

## Output Data Structure

The Cluster Analytics service publishes detailed cluster metadata in the following JSON format:

```json
{
  "scene_id": "302cf49a-97ec-402d-a324-c5077b280b7b",
  "scene_name": "Queuing",
  "timestamp": "2025-10-14T09:16:41.377Z",
  "cluster_id": 0,
  "category": "person",
  "objects_in_cluster": 8,
  "cluster_center": {
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
  }
}
```

## Field Descriptions

### Core Metadata

| Field                | Type    | Description                                       |
| -------------------- | ------- | ------------------------------------------------- |
| `scene_id`           | String  | Unique identifier for the SceneScape scene        |
| `scene_name`         | String  | Human-readable name of the scene                  |
| `timestamp`          | String  | ISO 8601 timestamp when cluster was detected      |
| `cluster_id`         | Integer | Sequential ID for clusters within the category    |
| `category`           | String  | Object detection category (person, vehicle, etc.) |
| `objects_in_cluster` | Integer | Number of objects forming the cluster             |

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

Example Python code to process cluster metadata:

```python
import json
import paho.mqtt.client as mqtt

def on_message(client, userdata, message):
    try:
        cluster_data = json.loads(message.payload.decode())

        scene_name = cluster_data['scene_name']
        category = cluster_data['category']
        object_count = cluster_data['objects_in_cluster']
        movement_type = cluster_data['velocity_analysis']['movement_type']
        shape = cluster_data['shape_analysis']['shape']

        print(f"Scene: {scene_name}")
        print(f"Detected {shape} cluster of {object_count} {category} objects")
        print(f"Movement pattern: {movement_type}")

        if shape == "circle":
            radius = cluster_data['shape_analysis']['size']['radius']
            print(f"Circle radius: {radius:.2f}m")
        elif shape == "rectangle":
            width = cluster_data['shape_analysis']['size']['width']
            height = cluster_data['shape_analysis']['size']['height']
            print(f"Rectangle: {width:.2f}m x {height:.2f}m")

    except Exception as e:
        print(f"Error processing cluster data: {e}")

client = mqtt.Client()
client.on_message = on_message
client.connect("broker.scenescape.intel.com", 1883, 60)
client.subscribe("scenescape/analytics/clusters/+")
client.loop_forever()
```

## Deployment

### Docker Deployment

#### Using Docker Compose (Recommended)

The cluster analytics service is included in the main SceneScape demo docker-compose stack:

```bash
SUPASS=admin123 make
SUPASS=admin123 make demo
```

## Architecture

### Data Flow Diagram

```mermaid
sequenceDiagram
    participant OD as Object Detection
    participant SC as Scene Controller
    participant CA as Cluster Analytics
    participant MQTT as MQTT Broker
    participant APP as Applications

    OD->>SC: Objects detections
    SC->>MQTT: Objects coordinates and velocities
    MQTT->>CA: Objects metadata

    Note over CA: Category-specific DBSCAN clustering
    Note over CA: Cluster's shape and velocity analysis

    CA->>MQTT: Cluster metadata
    MQTT->>APP: Cluster based insights
```

## 📊 Optimized Logging

The service uses a two-tier logging approach to balance operational visibility with performance:

### Production Logging (INFO Level)

```bash
INFO : Scene 302cf49a-97ec-402d-a324-c5077b280b7b: Found 2 clusters for category 'person' (62 objects, 15 noise points) using eps=0.5, min_samples=3
INFO : Using category-specific DBSCAN parameters for 'person': eps=0.5, min_samples=3
INFO : Published cluster 0 metadata for scene 302cf49a-97ec-402d-a324-c5077b280b7b category 'person'
```

### Development Logging (DEBUG Level)

```bash
DEBUG: Detailed cluster metadata: {
  "scene_id": "302cf49a-97ec-402d-a324-c5077b280b7b",
  "cluster_id": 0,
  "category": "person",
  "objects_in_cluster": 8,
  "cluster_center": {"x": 4.29, "y": 4.93},
  "shape_analysis": {"shape": "circle", "size": {...}},
  "velocity_analysis": {"movement_type": "chaotic", ...},
  "dbscan_params": {"eps": 0.5, "min_samples": 3, "category": "person"}
}
```

### Benefits

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

---

_Intel® SceneScape Cluster Analytics Microservice - Advanced Object Clustering and Movement Analysis_
