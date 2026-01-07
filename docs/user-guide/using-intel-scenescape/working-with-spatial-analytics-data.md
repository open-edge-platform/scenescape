# Working with Spatial Analytics Data: ROIs and Tripwires

This guide provides comprehensive information for developers who want to build applications that consume Intel® SceneScape's spatial analytics event data. You'll learn how to subscribe to MQTT events from Regions of Interest (ROIs) and Tripwires to create intelligent applications that respond to object interactions within defined areas, regardless of the sensor modality used for detection.

## Table of Contents

1. [Overview](#overview)
2. [Understanding ROIs and Tripwires](#understanding-rois-and-tripwires)
3. [Authentication](#authentication)
4. [Discovering Existing ROIs and Tripwires via API](#discovering-existing-rois-and-tripwires-via-api)
5. [MQTT Event Topics and Data Flow](#mqtt-event-topics-and-data-flow)
6. [Event Data Structures](#event-data-structures)
7. [Code Examples](#code-examples)
8. [Conclusion](#conclusion)

---

## Overview

Intel® SceneScape's spatial analytics system enables you to receive real-time notifications when objects interact with predefined virtual areas and boundaries within monitored scenes. The system supports various sensor modalities including cameras, lidar, radar, and other detection technologies. This guide focuses on consuming these events to build dynamic applications.

### Multi-Sensor Advantages

Intel® SceneScape's scene-based spatial analytics operate on a unified view that combines data from multiple sensors (cameras, lidar, radar, etc.), offering several key benefits:

- **Comprehensive Coverage**: Multi-modal sensor fusion provides enhanced accuracy and reliability
- **Resilient Operation**: Sensor redundancy maintains monitoring even if individual sensors fail
- **Sensor-Agnostic Analytics**: ROIs and tripwires use scene-level coordinates, independent of specific sensors
- **Superior Performance**: Leverage strengths of different sensor types for better object tracking

This approach enables applications with accuracy, coverage, and resilience impossible with single-sensor systems.

### Key Challenges Addressed

Intel® SceneScape's scene-based approach addresses common analytics challenges:

1. **Multi-Region Management**: Manage multiple regions across the entire scene rather than per-camera, simplifying configuration and maintenance
2. **Large Area Coverage**: Multi-sensor fusion covers areas too large for single sensors or with occlusion issues

The sensor-agnostic architecture ensures spatial analytics continue working reliably as sensor infrastructure evolves.

### Use Cases for Event Data

- **Security and Surveillance**: Monitor restricted areas, detect unauthorized access
- **Traffic Management**: Count vehicles crossing intersections, monitor pedestrian crossings
- **Retail Analytics**: Track customer movement patterns, analyze dwell time in product areas
- **Industrial Safety**: Monitor safety zones, detect personnel in dangerous areas
- **Smart City Applications**: Optimize traffic flow, manage public spaces

This guide focuses on consuming spatial analytics event data. ROIs and Tripwires are created through the Intel® SceneScape UI or REST API—see the [How to Configure Spatial Analytics](../building-a-scene/how-to-configure-spatial-analytics.md) guide for setup instructions.

---

## Understanding ROIs and Tripwires

![Sample Region and Tripwire](../images/ui/sample_region_tripwire.png)

The image above shows a practical example from Intel's headquarters parking lot in Santa Clara, CA, demonstrating how spatial analytics elements are deployed in real-world scenarios. In this scene, you can see:

- **Tripwire (green line)**: A directional tripwire positioned across a one-way lane to monitor vehicle traffic. The tripwire appears as a green line with small circles at each endpoint, and a short perpendicular line extending from the center that acts as a directional flag. This tripwire counts vehicles moving in the correct direction and can trigger alerts when vehicles drive the wrong way, providing both traffic analytics and safety monitoring for one-way traffic enforcement.

- **Region of Interest (red polygon)**: A polygonal region drawn around the loading zone area. This ROI monitors when vehicles enter and exit the designated loading area, tracks how long they remain (dwell time), and can trigger alerts if the zone becomes occupied for extended periods or if multiple vehicles are present simultaneously.

This shows how ROIs and tripwires work together to provide comprehensive monitoring: the tripwire captures traffic flow at access points, while the ROI provides detailed occupancy analytics for specific functional areas.

### Regions of Interest (ROIs)

ROIs are virtual areas defined within a scene's physical space where you want to monitor object presence and behavior. ROIs are defined at the scene level using world coordinates, making them independent of any specific sensor or viewing angle. Each ROI can track:

- **Object Entry**: When objects enter the region
- **Object Exit**: When objects leave the region
- **Object Counts**: Number of objects currently in the region
- **Dwell Time**: How long objects remain in the region

#### ROI Properties

- **UUID**: Unique identifier for the ROI
- **Name**: Human-readable name for the ROI
- **Points**: Array of (x, y) coordinates defining the polygon boundary in scene world coordinates
- **Volumetric**: Controls how tracked objects are evaluated within the region:
  - **When enabled**: Objects are treated as 3D volumes; events trigger if any part of the tracked volume intersects the region
  - **When disabled**: Objects are treated as center points; events trigger only when the object's center point enters or leaves the region
- **Height**: Physical height of the ROI in meters
- **Buffer Size**: Additional boundary area around the defined polygon
- **Color Range**: When "Visualize ROIs" is enabled in the 2D UI, color the ROI based on occupancy thresholds

### Tripwires

Tripwires are virtual lines defined within a scene's physical space that detect when objects cross them. Like ROIs, tripwires are defined using scene world coordinates, making them independent of any specific sensor or viewing perspective. They are ideal for:

- **Directional Counting**: Count objects moving in specific directions
- **Boundary Monitoring**: Detect when objects cross important boundaries
- **Flow Analysis**: Monitor traffic flow through specific points

#### Tripwire Properties

- **UUID**: Unique identifier for the tripwire
- **Name**: Human-readable name for the tripwire
- **Points**: Array of exactly 2 (x, y) coordinates defining the line endpoints in scene world coordinates

---

## Authentication

Intel® SceneScape supports different authentication approaches depending on your deployment scenario:

### REST API Authentication

For REST API access (discovering regions, tripwires, and configuration data):

```bash
# Request header format
Authorization: Token <your_api_token>
```

**Getting Your API Token:**

- Access the Intel® SceneScape Admin panel: `https://<your-host>/admin`
- Navigate to **Tokens** section
- Use tokens from `admin` or `scenectrl` user accounts

### MQTT Authentication Options

#### Quick Testing & Development

For rapid testing and development, use admin credentials with WebSocket MQTT:

```python
# WebSocket MQTT (port 443, easy setup)
client = mqtt.Client(transport="websockets")
client.username_pw_set("admin", os.environ['SUPASS'])  # Web login password
```

**Pros**: Works immediately, no additional configuration
**Cons**: Uses admin credentials, WebSocket overhead

#### Production Python Applications

For external applications, use dedicated MQTT accounts with direct protocol:

```python
# Direct MQTT protocol (port 1883, more efficient)
client = mqtt.Client()
client.username_pw_set(mqtt_user, mqtt_password)
client.tls_set_context(ssl_context)
client.connect(host, 1883, 60)

```

**Setup Requirements:**

- Expose MQTT port 1883 in deployment configuration
- Create dedicated MQTT user accounts (not admin)
- Use MQTT-specific credentials from secrets management

#### Web Applications

For browser-based applications, additional security considerations apply:

```javascript
// Client-side WebSocket MQTT (security considerations required)
const client = mqtt.connect(`wss://${host}/mqtt`, {
  username: "limited_user", // NOT admin
  password: "client_password", // NOT SUPASS
});
```

**Security Considerations:**

- **Never expose admin credentials to client-side code**
- Use limited-privilege MQTT accounts for web clients
- Consider authentication proxies or token-based MQTT access
- Implement proper credential rotation and access controls

### Environment Setup

**For Development/Testing:**

```bash
export SCENESCAPE_HOST="scenescape-hostname-or-ip-address"
export SCENESCAPE_TOKEN="your-api-token"  # For REST API calls
export SUPASS="your-web-login-password"   # For quick MQTT testing
```

**For Production:**

```bash
export SCENESCAPE_HOST="scenescape-hostname-or-ip-address"
export SCENESCAPE_TOKEN="your-api-token"
export MQTT_USER="dedicated-mqtt-user"    # Production MQTT account
export MQTT_PASS="dedicated-mqtt-password"
```

---

## Discovering Existing ROIs and Tripwires via API

Before subscribing to events, discover what ROIs and Tripwires exist in your scenes using the REST API. While this information is available through the Intel® SceneScape UI, the API provides complete configuration details, structured metadata, and immediate access without waiting for events.

**Important**: Handle dynamic configuration changes in your applications. Spatial analytics may be added, removed, or modified during operation—implement periodic API checks rather than hard-coding IDs.

### API Endpoints

#### List All Regions

```bash
curl -k -H "Authorization: Token $SCENESCAPE_TOKEN" \
  https://$SCENESCAPE_HOST/api/v1/regions
```

**Response Example:**

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "uid": "5908cfbe-2090-4dc9-b200-6608e2c3be86",
      "name": "queue",
      "points": [
        [0.4, 3.14],
        [0.32, 1.85],
        [2.97, 0.57],
        [4.62, 2.01]
      ],
      "scene": "302cf49a-97ec-402d-a324-c5077b280b7b",
      "buffer_size": 0.0,
      "height": 1.0,
      "volumetric": false
    }
  ]
}
```

#### List All Tripwires

```bash
curl -k -H "Authorization: Token $SCENESCAPE_TOKEN" \
  https://$SCENESCAPE_HOST/api/v1/tripwires
```

**Response Example:**

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "uid": "23ae85b3-4b2c-4f38-a0bc-684b774d320c",
      "name": "entry",
      "points": [
        [2.62, 2.73],
        [1.18, 0.26]
      ],
      "height": 1.0,
      "scene": "302cf49a-97ec-402d-a324-c5077b280b7b"
    }
  ]
}
```

#### Get Specific Region

```bash
curl -k -H "Authorization: Token $SCENESCAPE_TOKEN" \
  https://$SCENESCAPE_HOST/api/v1/region/{region_id}
```

#### Get Specific Tripwire

```bash
curl -k -H "Authorization: Token $SCENESCAPE_TOKEN" \
  https://$SCENESCAPE_HOST/api/v1/tripwire/{tripwire_id}
```

---

## MQTT Event Topics and Data Flow

Intel® SceneScape uses MQTT for real-time event delivery. Understanding the topic structure is crucial for building reactive applications.

### Object Type Definitions

Object types are defined dynamically by the class labels from input detection data (e.g., `person`, `vehicle`, `forklift`, `package`, `bicycle`, etc.). The system supports any object class without requiring pre-registration, making it flexible for diverse detection scenarios.

**Note**: While dynamic object classification works out-of-the-box, tracking performance and accuracy can be improved by pre-defining object classes and their properties (such as expected size dimensions) in the Intel® SceneScape Object Library. This allows the system to use more accurate object models for tracking and spatial analytics calculations. For details on configuring object properties, see [How to Define Object Properties](../other-topics/how-to-define-object-properties.md).

This dynamic classification applies to all MQTT topics, event data, and API responses throughout the system.

### Event Topics

#### Region Events

```text
scenescape/event/region/{scene_id}/{region_id}/{event_type}
```

**Event Types:**

- `count` - Object count changes within the region (contains entered/exited arrays)
- `objects` - Object changes within the region (entry/exit events with full object details)

**Purpose**: Both event types fire when objects enter or exit regions. The main difference is data format:

- **`count` events**: Focus on count changes with summary entry/exit information
- **`objects` events**: Provide complete object details for entry/exit events

**Note**: Both event types typically fire together for the same entry/exit events. Choose based on whether you need full object details (`objects`) or just count summaries (`count`). For continuous positional updates of objects within regions, subscribe to streaming data topics instead—see [Streaming Data Topics](#streaming-data-topics).

#### Tripwire Events

```text
scenescape/event/tripwire/{scene_id}/{tripwire_id}/{event_type}
```

**Event Types:**

- `objects` - Objects crossing the tripwire

### Example MQTT Subscriptions

```python
import paho.mqtt.client as mqtt

# Subscribe to region count events (entry/exit only) for a specific scene
region_count_topic = f"scenescape/event/region/{scene_id}/+/count"
client.subscribe(region_count_topic)

# Subscribe to tripwire events
tripwire_events_topic = f"scenescape/event/tripwire/{scene_id}/+/objects"
client.subscribe(tripwire_events_topic)

# Subscribe to streaming data for specific object types in regions (continuous updates)
region_person_data_topic = f"scenescape/data/region/{scene_id}/{region_id}/person"
client.subscribe(region_person_data_topic)

region_vehicle_data_topic = f"scenescape/data/region/{scene_id}/{region_id}/vehicle"
client.subscribe(region_vehicle_data_topic)

# Subscribe to streaming data for all object types in a specific region
region_all_objects_data_topic = f"scenescape/data/region/{scene_id}/{region_id}/+"
client.subscribe(region_all_objects_data_topic)

# Subscribe to all region count events across all scenes
all_regions_count_topic = "scenescape/event/region/+/+/count"
client.subscribe(all_regions_count_topic)

# Subscribe to all tripwire events across all scenes
all_tripwires_topic = "scenescape/event/tripwire/+/+/objects"
client.subscribe(all_tripwires_topic)

# Subscribe to ALL events with wildcard pattern (for debugging/exploration)
all_events_topic = "scenescape/event/+/+/+/+"
client.subscribe(all_events_topic)
```

---

## Event Data Structures

Intel® SceneScape generates three types of events in addition to the usual streaming data available on other topics:

1. **Region entry events** - triggered when objects enter regions (with entry timestamps)
2. **Region exit events** - triggered when objects leave regions (with dwell time calculations)
3. **Tripwire crossing events** - triggered when objects cross tripwires (with directional information)

Each event includes object metadata and spatial context.

### Region Event Structure

#### Entry Event Example

**Topic:** `scenescape/event/region/302cf49a.../5908cfbe.../count`

> **Note**: UUIDs, coordinates, and decimal precision have been simplified for readability. Actual values will be longer and more precise.

```json
{
  "timestamp": "2025-11-13T20:11:38.971Z",
  "scene_id": "302cf49a...",
  "scene_name": "Queuing",
  "region_id": "5908cfbe...",
  "region_name": "queue",
  "counts": {
    "person": 1
  },
  "objects": [
    {
      "category": "person",
      "confidence": 0.997,
      "id": "82d54b1b...",
      "type": "person",
      "translation": [4.03, 1.53, 0.0],
      "size": [0.5, 0.5, 1.85],
      "velocity": [-1.16, 0.57, 0.0],
      "rotation": [0, 0, 0, 1],
      "visibility": ["atag-qcam1", "atag-qcam2"],
      "regions": {
        "5908cfbe...": {
          "entered": "2025-11-13T20:11:38.971Z"
        }
      },
      "similarity": null,
      "first_seen": "2025-11-13T20:11:35.839Z"
    }
  ],
  "entered": [
    {
      "category": "person",
      "confidence": 0.997,
      "id": "82d54b1b...",
      "first_seen": "2025-11-13T20:11:35.839Z"
    }
  ],
  "exited": [],
  "metadata": {
    "points": [
      [0.4, 3.14],
      [0.32, 1.85],
      [2.97, 0.57],
      [4.62, 2.01]
    ],
    "title": "queue",
    "uuid": "5908cfbe...",
    "area": "poly",
    "fromSensor": false
  }
}
```

**Key Properties in Entry Events:**

- **`counts`**: Current object counts by type after the entry occurred
- **`entered` array**: Contains summary information about objects that just entered
- **`objects` array**: Full object details for all objects currently in the region, including the newly entered object with its `regions.{region_id}.entered` timestamp

#### Exit Event Example

**Topic:** `scenescape/event/region/302cf49a.../5908cfbe.../count`

```json
{
  "timestamp": "2025-11-13T20:11:47.128Z",
  "scene_id": "302cf49a...",
  "scene_name": "Queuing",
  "region_id": "5908cfbe...",
  "region_name": "queue",
  "counts": {
    "person": 1
  },
  "objects": [
    {
      "category": "person",
      "confidence": 0.998,
      "id": "a266a0be...",
      "type": "person",
      "translation": [2.24, 1.7, 0.0],
      "size": [0.5, 0.5, 1.85],
      "velocity": [-0.01, 0.07, 0.0],
      "rotation": [0, 0, 0, 1],
      "visibility": ["atag-qcam1", "atag-qcam2"],
      "regions": {
        "5908cfbe...": {
          "entered": "2025-11-13T20:11:27.515Z"
        }
      },
      "similarity": null,
      "first_seen": "2025-11-13T20:11:26.121Z"
    }
  ],
  "entered": [],
  "exited": [
    {
      "object": {
        "category": "person",
        "confidence": 0.997,
        "id": "f6f8d2a3...",
        "type": "person",
        "translation": [1.04, 2.3, 0.0],
        "size": [0.5, 0.5, 1.85],
        "velocity": [0.01, -0.02, 0.0],
        "rotation": [0, 0, 0, 1],
        "visibility": ["atag-qcam2"],
        "regions": {},
        "similarity": null,
        "first_seen": "2025-11-13T20:11:26.121Z"
      },
      "dwell": 19.6
    }
  ],
  "metadata": {
    "points": [
      [0.4, 3.14],
      [0.32, 1.85],
      [2.97, 0.57],
      [4.62, 2.01]
    ],
    "title": "queue",
    "uuid": "5908cfbe...",
    "area": "poly",
    "fromSensor": false
  }
}
```

**Key Properties in Exit Events:**

- **`counts`**: Current object counts by type after the exit occurred
- **`exited` array**: Contains critical `dwell` time data - how long each object spent in the region (essential for situational awareness applications like queue monitoring, loitering detection, and process timing analysis)
- **`objects` array**: Full details for objects still remaining in the region after the exit

### Tripwire Event Structure

**Topic:** `scenescape/event/tripwire/302cf49a.../23ae85b3.../objects`

```json
{
  "timestamp": "2025-11-12T21:03:14.318Z",
  "scene_id": "302cf49a...",
  "scene_name": "Queuing",
  "tripwire_id": "23ae85b3...",
  "tripwire_name": "entry",
  "counts": {
    "person": 1
  },
  "objects": [
    {
      "category": "person",
      "confidence": 0.743,
      "id": "63684acf...",
      "type": "person",
      "translation": [1.77, 1.23, 0.0],
      "size": [0.5, 0.5, 1.85],
      "velocity": [0.36, -0.32, 0.0],
      "rotation": [0, 0, 0, 1],
      "visibility": ["atag-qcam1"],
      "regions": {
        "5908cfbe...": {
          "entered": "2025-11-12T21:02:57.228Z"
        }
      },
      "similarity": null,
      "first_seen": "2025-11-12T21:02:53.720Z",
      "direction": -1
    }
  ],
  "entered": [],
  "exited": [],
  "metadata": {
    "title": "entry",
    "points": [
      [2.62, 2.73],
      [1.18, 0.26]
    ],
    "uuid": "23ae85b3..."
  }
}
```

**Key Properties in Tripwire Events:**

- **`direction` field**: Critical directional indicator (+1 or -1) showing which way each individual object crossed the tripwire relative to the configured directional flag - essential for counting applications, access control, and flow analysis. Each object in the `objects` array has its own direction field (always +1 or -1)
- **`objects` array**: Contains full object details at the moment of crossing, including position, velocity, and confidence
- **`counts`**: Number of objects crossing in this event - almost always 1 (single object crossing), except in rare cases where multiple objects cross simultaneously

### Event Field Descriptions

| Field                           | Type   | Description                                                                                                                                       |
| ------------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `timestamp`                     | string | ISO 8601 timestamp of the original data frame or sensor input when the object interaction occurred (not when the event was detected or processed) |
| `scene_id`                      | string | UUID of the scene containing the region/tripwire                                                                                                  |
| `scene_name`                    | string | Human-readable scene name                                                                                                                         |
| `region_id` / `tripwire_id`     | string | UUID of the region or tripwire                                                                                                                    |
| `region_name` / `tripwire_name` | string | Human-readable region or tripwire name                                                                                                            |
| `counts`                        | object | Current object counts by category                                                                                                                 |
| `objects`                       | array  | Objects currently in region or crossing tripwire                                                                                                  |
| `entered`                       | array  | Objects that entered the region (ROI events only)                                                                                                 |
| `exited`                        | array  | Objects that exited the region (ROI events only); includes `object` details and `dwell` time in seconds                                           |
| `metadata`                      | object | Region/tripwire configuration data                                                                                                                |
| `dwell`                         | number | Time in seconds that an object spent in the region (only in exited events)                                                                        |
| `id`                            | string | Object identifier (within object data)                                                                                                            |
| `category` / `type`             | string | Object classification (person, vehicle, etc.)                                                                                                     |
| `confidence`                    | number | Detection confidence (0.0 - 1.0)                                                                                                                  |
| `translation`                   | array  | 3D world coordinates [x, y, z] in meters                                                                                                          |
| `velocity`                      | array  | Velocity vector [vx, vy, vz] in meters per second                                                                                                 |
| `visibility`                    | array  | List of sensors that can detect this object                                                                                                       |
| `regions`                       | object | Region membership and entry times                                                                                                                 |
| `direction`                     | number | Crossing direction for tripwire events (-1 or 1)                                                                                                  |

---

## Streaming Data Topics

In addition to event-driven notifications, Intel® SceneScape provides continuous streaming data topics for real-time object tracking within regions.

### Region Data Topics

```bash
scenescape/data/region/{scene_id}/{region_id}/{object_type}
```

**Object Types**: Detected object types (see [Object Type Definitions](#object-type-definitions) above).

**Purpose**: These topics provide continuous real-time updates for all objects currently within the region, including positional changes, confidence updates, and other dynamic properties. They act as a spatial filter to the larger scene data, delivering streaming updates only for objects inside the specific region. Unlike event topics that fire on entry/exit, these data topics stream continuously while objects remain in the region.

**Use Case**: Subscribe to these topics when you need continuous tracking of object movement and properties within a region, rather than just entry/exit notifications.

**Calculating Dwell Time for Active Objects**: To calculate how long an object has been in a region while it's still present, you must use these streaming data topics, not the event topics. Each object contains a `regions` field with the entry timestamp. Calculate current dwell time by subtracting the `entered` timestamp from the current time. This is essential for applications that need to detect when objects have waited too long in a region before they exit - event topics only provide dwell time after an object has already left the region.

---

## Code Examples

**Prerequisites:** Before running these examples, create at least one region and one tripwire using the Intel® SceneScape web interface. In your Intel® SceneScape deployment, select a scene and use the Regions and Tripwires tabs to draw spatial analytics elements. The examples below will discover and monitor these configured elements.

### Prerequisites

**Ubuntu Setup:**

```bash
sudo apt update && sudo apt install python3-requests python3-paho-mqtt
```

**Alternative (using virtual environment):**

```bash
sudo apt update && sudo apt install python3-full
python3 -m venv scenescape-env
source scenescape-env/bin/activate
pip install requests paho-mqtt
```

**Environment Variables:**

```bash
export SCENESCAPE_HOST="scenescape-hostname-or-ip-address"
export SCENESCAPE_TOKEN="your-api-token"  # Found in SceneScape Admin panel > Tokens (admin or scenectrl user)
export SUPASS="your-web-login-password"
```

### Step 1: Discover Your Regions and Tripwires

**Save as:** `discover.py`

```python
#!/usr/bin/env python3
import os, requests, json
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

host = os.environ["SCENESCAPE_HOST"]
token = os.environ["SCENESCAPE_TOKEN"]
headers = {"Authorization": f"Token {token}"}

print("Discovering regions...")
regions = requests.get(
    f"https://{host}/api/v1/regions", headers=headers, verify=False
).json()
for r in regions["results"]:
    print(f"  {r['name']} ({r['uid']})")

print("\nDiscovering tripwires...")
tripwires = requests.get(
    f"https://{host}/api/v1/tripwires", headers=headers, verify=False
).json()
for t in tripwires["results"]:
    print(f"  {t['name']} ({t['uid']})")
```

**Run:** `python3 discover.py`

### Step 2: Listen to Live Events

**Save as:** `listen.py`

```python
#!/usr/bin/env python3
import os, json, ssl
import paho.mqtt.client as mqtt


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected! Listening for events...")
        client.subscribe("scenescape/event/+/+/+/+")
    else:
        print(f"Connection failed: {rc}")


def on_message(client, userdata, msg):
    try:
        event = json.loads(msg.payload.decode())
        topic_parts = msg.topic.split("/")

        if topic_parts[2] == "region":
            region_name = event.get("region_name")
            counts = event.get("counts", {})

            print(f"Region '{region_name}': {counts}")
            if event.get("entered"):
                print(f"  → {len(event['entered'])} entered")
            if event.get("exited"):
                for exit_info in event["exited"]:
                    dwell = exit_info.get("dwell", 0)
                    print(f"  ← exited (dwell: {dwell:.1f}s)")

        elif topic_parts[2] == "tripwire":
            tripwire_name = event.get("tripwire_name")
            for obj in event.get("objects", []):
                direction = "→" if obj.get("direction", 0) > 0 else "←"
                print(f"Tripwire '{tripwire_name}': {obj.get('category')} {direction}")

    except Exception as e:
        print(f"Error: {e}")


client = mqtt.Client(transport="websockets")
client.username_pw_set("admin", os.environ["SUPASS"])

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE
client.tls_set_context(ssl_context)

client.on_connect = on_connect
client.on_message = on_message

client.ws_set_options(path="/mqtt")
client.connect(os.environ["SCENESCAPE_HOST"], 443, 60)
client.loop_forever()
```

**Run:** `python3 listen.py`

### Step 3: JavaScript Web Example

**Save as:** `index.html`

```html
<!DOCTYPE html>
<html>
  <head>
    <meta charset="UTF-8" />
    <title>SceneScape Events</title>
    <script src="https://unpkg.com/mqtt/dist/mqtt.min.js"></script>
  </head>
  <body>
    <h1>SceneScape Live Events</h1>
    <div id="status">Connecting...</div>
    <div id="events"></div>

    <script>
      // Replace these with your actual values
      const SCENESCAPE_HOST = "YOUR_SCENESCAPE_HOST";
      const SUPASS = "YOUR_SUPASS"; // Your SceneScape login password

      const client = mqtt.connect(`wss://${SCENESCAPE_HOST}/mqtt`, {
        username: "admin",
        password: SUPASS,
      });

      client.on("connect", () => {
        document.getElementById("status").textContent = "Connected!";
        client.subscribe("scenescape/event/+/+/+/+");
      });

      client.on("message", (topic, message) => {
        try {
          const event = JSON.parse(message.toString());
          const parts = topic.split("/");

          let text = "";
          if (parts[2] === "region" && parts[5] === "count") {
            // Only process count events to avoid duplicates
            const counts = Object.entries(event.counts || {})
              .map(([type, count]) => `${count} ${type}`)
              .join(", ");
            text = `Region "${event.region_name}": ${counts}`;

            if (event.entered?.length > 0) {
              text += ` &rarr; ${event.entered.length} entered`;
            }
            if (event.exited?.length > 0) {
              text += ` &larr; ${event.exited.length} exited`;
            }
          } else if (parts[2] === "tripwire") {
            const objects = event.objects || [];
            text = `Tripwire "${event.tripwire_name}": ${objects.length} crossed`;
          }

          if (text) {
            const div = document.createElement("div");
            div.innerHTML = `${new Date().toLocaleTimeString()} - ${text}`;
            document.getElementById("events").prepend(div);
          }
        } catch (e) {
          console.error("Error processing message:", e);
        }
      });
    </script>
  </body>
</html>
```

**Run:** `python3 -m http.server 8000` then open http://&lt;your-server-ip&gt;:8000 in your browser

**Important:** Replace `YOUR_SCENESCAPE_HOST` and `YOUR_SUPASS` with your actual values:

- **Host**: Use `localhost` only if your browser and Intel® SceneScape are running on the same system, otherwise use the actual hostname or IP address of your Intel® SceneScape deployment
- **Password**: Use your Intel® SceneScape web interface login password (same as the `SUPASS` environment variable)

These three simple scripts provide a complete foundation for working with Intel® SceneScape spatial analytics data. The tutorial emphasizes immediate testability with minimal setup requirements.

### Direct MQTT Access (Alternative to WebSockets)

For applications that need direct MQTT access instead of WebSockets, additional configuration is required:

**Docker Compose Setup:**
In `docker-compose.yml`, uncomment the broker ports section:

```yaml
broker:
  image: eclipse-mosquitto:2.0.22
  ports:
    - "1883:1883" # Uncomment this line
  # ... rest of broker config
```

**Kubernetes Setup:**
Direct MQTT access is configured via NodePort service. Check `kubernetes/scenescape-chart/values.yaml`:

```yaml
mqttService:
  nodePort:
    enabled: true
    nodePort: 31883 # External port for MQTT access
```

**MQTT Credentials:**
Use the generated MQTT credentials instead of web login credentials:

```bash
# Read MQTT credentials from secrets file
export MQTT_USER=$(jq -r '.user' manager/secrets/controller.auth)
export MQTT_PASS=$(jq -r '.password' manager/secrets/controller.auth)
```

**Python Example for Direct MQTT:**

```python
import os, ssl
import paho.mqtt.client as mqtt


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to direct MQTT!")
        client.subscribe("scenescape/event/+/+/+/+")
    else:
        print(f"Connection failed: {rc}")


def on_message(client, userdata, msg):
    # Process events here
    print(f"Topic: {msg.topic}")
    print(f"Message: {msg.payload.decode()}")


# Use dedicated MQTT credentials (not admin/SUPASS)
client = mqtt.Client()
client.username_pw_set(os.environ["MQTT_USER"], os.environ["MQTT_PASS"])

# Configure TLS
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE
client.tls_set_context(ssl_context)

client.on_connect = on_connect
client.on_message = on_message

# Direct MQTT connection with TLS
host = os.environ["SCENESCAPE_HOST"]
client.connect(host, 1883, 60)
client.loop_forever()
```

**Environment Setup for Direct MQTT:**

```bash
export SCENESCAPE_HOST="scenescape-hostname-or-ip"  # No https:// prefix
export MQTT_USER="dedicated-mqtt-user"
export MQTT_PASS="dedicated-mqtt-password"
```

**Note:** WebSocket MQTT works out-of-the-box with standard HTTPS port 443, while direct MQTT requires exposing additional ports.

---

## Conclusion

Intel® SceneScape's spatial analytics provide a powerful abstraction that separates monitoring logic from individual sensor perspectives. By defining regions and tripwires at the scene level using world coordinates, your applications gain a critical advantage: **sensor independence**.

This architecture means your spatial analytics logic — the regions you define, the business rules you implement, and the applications you build — remain completely unchanged even as your sensor infrastructure evolves. Whether you add new cameras, upgrade to different sensor technologies, or reconfigure your monitoring setup, your ROIs and tripwires continue working seamlessly.

**Key Benefits:**

- **Future-proof applications**: Analytics logic survives sensor changes and infrastructure upgrades
- **Unified monitoring**: Single API and event stream regardless of underlying sensor types or count
- **Simplified maintenance**: Manage spatial analytics once at the scene level, not per-sensor

**Getting Started:**

1. Run the tutorial examples (`discover.py`, `listen.py`, `index.html`)
2. Define regions and tripwires that match your monitoring needs
3. Build applications using the REST API and MQTT event streams
4. Scale and adapt your sensor infrastructure independently of your analytics logic

This sensor-agnostic approach ensures your investment in spatial analytics applications provides long-term value, adapting to new technologies while maintaining consistent monitoring capabilities.
