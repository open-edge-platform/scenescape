# Scene Controller Service: Architecture and Implementation Deep Dive

## Table of Contents
1. [Introduction](#introduction)
2. [High-Level Architecture](#high-level-architecture)
3. [Core Components](#core-components)
4. [Data Flow and Message Processing](#data-flow-and-message-processing)
5. [Object Tracking and Management](#object-tracking-and-management)
6. [Scene Management](#scene-management)
7. [Event Processing and Analytics](#event-processing-and-analytics)
8. [Configuration and Deployment](#configuration-and-deployment)
9. [Key Implementation Patterns](#key-implementation-patterns)
10. [Performance Considerations](#performance-considerations)
11. [Troubleshooting and Debugging](#troubleshooting-and-debugging)

## Introduction

The Scene Controller Service is the central orchestration component of Intel® SceneScape, responsible for fusing multimodal sensor data to enable spatial analytics at the edge. This document provides a comprehensive technical deep dive into its architecture and implementation for engineers with medium-level Python and AI experience who are ramping up on the project.

### What Does the Scene Controller Do?

The Scene Controller answers the fundamental question of **"What, When, and Where"** by:
- Receiving object detections from multiple cameras and sensors
- Contextualizing them in a common reference frame
- Fusing detections across multiple sources
- Tracking objects over time
- Providing spatial analytics (regions of interest, tripwires, sensor regions)
- Publishing processed data and events via MQTT

## High-Level Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Percebro      │    │   Cameras       │    │   Sensors       │
│  (Vision AI)    │    │   (Raw Data)    │    │ (Environmental) │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                         ┌───────▼───────┐
                         │  MQTT Broker  │
                         └───────┬───────┘
                                 │
                    ┌────────────▼────────────┐
                    │   Scene Controller      │
                    │                         │
                    │  ┌─────────────────┐   │
                    │  │ Message Router  │   │
                    │  └─────────────────┘   │
                    │  ┌─────────────────┐   │
                    │  │ Object Tracker  │   │
                    │  └─────────────────┘   │
                    │  ┌─────────────────┐   │
                    │  │ Scene Manager   │   │
                    │  └─────────────────┘   │
                    │  ┌─────────────────┐   │
                    │  │ Event Processor │   │
                    │  └─────────────────┘   │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │    Client Applications  │
                    │  (Web UI, Analytics)    │
                    └─────────────────────────┘
```

### Key Architectural Principles

1. **Event-Driven Architecture**: All communication happens via MQTT publish/subscribe
2. **Microservice Design**: Decoupled components communicating through well-defined interfaces
3. **Real-Time Processing**: Low-latency data processing with configurable performance tuning
4. **Scalable Scene Management**: Support for hierarchical scenes and child scene relationships
5. **Extensible Object Classes**: Dynamic object type management through asset definitions

## Core Components

### 1. SceneController Class (`scene_controller.py`)

The main orchestrator class that coordinates all scene controller functionality.

```python
class SceneController:
    def __init__(self, rewrite_bad_time, rewrite_all_time, max_lag, mqtt_broker,
                 mqtt_auth, rest_url, rest_auth, client_cert, root_cert, ntp_server,
                 tracker_config_file, schema_file, visibility_topic):
```

**Key Responsibilities:**
- MQTT message routing and handling
- Scene lifecycle management
- Object tracking coordination
- Event publishing
- Time synchronization with NTP

**Important Attributes:**
- `pubsub`: MQTT client for pub/sub operations
- `cache_manager`: Manages scene data and REST API interactions
- `schema_val`: Validates incoming message schemas
- `regulate_cache`: Buffers for regulated publication rates

### 2. CacheManager Class (`cache_manager.py`)

Manages scene data caching and REST API interactions with the Manager service.

```python
class CacheManager:
    def __init__(self, rest_url, rest_auth, root_cert, tracker_config_data):
```

**Key Functions:**
- `refreshScenes()`: Fetches and caches scene configurations
- `sceneWithCameraID()`: Maps camera IDs to scenes
- `sceneWithSensorID()`: Maps sensor IDs to scenes
- `getChildScenes()`: Manages hierarchical scene relationships

### 3. Scene Class (`scene.py`)

Represents individual scenes with their cameras, sensors, regions, and tracking state.

```python
class Scene(SceneModel):
    def __init__(self, name, map_file, scale=None,
                 max_unreliable_time=MAX_UNRELIABLE_TIME,
                 non_measurement_time_dynamic=NON_MEASUREMENT_TIME_DYNAMIC,
                 non_measurement_time_static=NON_MEASUREMENT_TIME_STATIC):
```

**Key Features:**
- Tracker management (default: Intel Labs tracking)
- Camera and sensor registration
- Region and tripwire management
- Coordinate system transformations
- Child scene hierarchy support

### 4. Tracking System (`tracking.py`, `ilabs_tracking.py`)

Multi-threaded object tracking with configurable algorithms.

```python
class Tracking(Thread):
    def trackObjects(self, objects, already_tracked_objects, when, categories,
                     ref_camera_frame_rate, max_unreliable_time,
                     non_measurement_time_dynamic, non_measurement_time_static):
```

**Tracking Features:**
- Per-category tracker instances
- Queue-based processing for performance
- Configurable tracking parameters
- UUID management for unique object identification

## Data Flow and Message Processing

### MQTT Topic Structure

The Scene Controller uses a structured MQTT topic hierarchy:

```
scenescape/
├── data/
│   ├── camera/{camera_id}          # Raw camera detections
│   ├── sensor/{sensor_id}          # Sensor data
│   ├── scene/{scene_id}/{type}     # Processed scene detections
│   ├── region/{scene_id}/{region_id}/{type}  # Region-specific detections
│   └── external/{scene_id}/{type}  # Child scene data
├── regulated/
│   └── scene/{scene_id}            # Rate-regulated detections
├── event/
│   └── {type}/{scene_id}/{region_id}/{event_type}  # Analytics events
└── cmd/
    ├── database                    # Database update commands
    └── camera/{camera_id}          # Camera control commands
```

### Message Processing Pipeline

1. **Message Reception**: MQTT messages arrive via subscribed topics
2. **Schema Validation**: Messages validated against JSON schema
3. **Time Synchronization**: Timestamps adjusted using NTP offset
4. **Scene Resolution**: Determine target scene from camera/sensor ID
5. **Object Tracking**: Update tracking state with new detections
6. **Analytics Processing**: Evaluate regions, tripwires, sensor zones
7. **Event Generation**: Create and publish analytics events
8. **Rate Regulation**: Buffer and publish at controlled rates

### Key Message Handlers

```python
def handleMovingObjectMessage(self, client, userdata, message):
    """Process camera detection messages"""
    
def handleSensorMessage(self, client, userdata, message):
    """Process environmental sensor data"""
    
def handleDatabaseMessage(self, client, userdata, message):
    """Handle configuration update notifications"""
```

## Object Tracking and Management

### Tracking Architecture

The tracking system uses a multi-threaded, category-based approach:

```python
# Each object category gets its own tracker thread
self.trackers = {
    'person': TrackerThread(),
    'vehicle': TrackerThread(),
    'apriltag': TrackerThread()
}
```

### Object Lifecycle

1. **Detection**: Raw detections arrive from cameras
2. **Association**: Match detections to existing tracks or create new ones
3. **Prediction**: Estimate object motion between frames
4. **Update**: Refine track state with new measurements
5. **Pruning**: Remove lost or unreliable tracks

### Moving Object Representation

```python
class MovingObject:
    def __init__(self, category, detection_confidence, bounds, when, camera, point):
        self.category = category          # Object type (person, vehicle, etc.)
        self.gid = None                  # Global unique identifier
        self.detection_confidence = detection_confidence
        self.locations = []              # Position history
        self.chain_data = ChainData()    # Analytics state
```

### Tracking Configuration

Tracking behavior is controlled via `tracker-config.json`:

```json
{
  "max_unreliable_frames": 10,        # Frames before track deletion
  "non_measurement_frames_dynamic": 8, # Prediction frames for moving objects
  "non_measurement_frames_static": 16, # Prediction frames for static objects
  "baseline_frame_rate": 30           # Reference frame rate
}
```

## Scene Management

### Scene Hierarchy

SceneScape supports hierarchical scene relationships:

```
Parent Scene
├── Child Scene A (Local)
├── Child Scene B (Remote)
└── Child Scene C (Local)
```

**Local Children**: Same SceneScape deployment, direct MQTT communication
**Remote Children**: Different deployments, authenticated MQTT bridging

### Coordinate System Management

Each scene maintains its own coordinate system with transformations:

```python
class Scene:
    def updateScene(self, scene_data):
        self.cameraPose = None
        if 'transform' in scene_data:
            self.cameraPose = CameraPose(scene_data['transform'], None)
```

### Camera Calibration Integration

The Scene Controller integrates with auto-calibration services:

```python
def updateCameras(self):
    for scene in self.scenes:
        for camera in scene.cameras:
            cam = scene.cameras[camera]
            if not hasattr(cam, "pose"):
                self.cache_manager.updateCamera(cam)
```

## Event Processing and Analytics

### Analytics Types

1. **Region Events**: Object entry/exit from regions of interest
2. **Tripwire Events**: Object crossing of virtual lines
3. **Sensor Events**: Environmental sensor threshold violations
4. **Dwell Events**: Object residence time in areas

### Event Generation Pipeline

```python
def publishEvents(self, scene, ts_str):
    for event_type in scene.events:
        for _, region in scene.events[event_type]:
            # Build event data structure
            event_data = {
                'timestamp': ts_str,
                'scene_id': scene.uid,
                'scene_name': scene.name,
                # ... additional metadata
            }
            
            # Publish to appropriate MQTT topic
            event_topic = PubSub.formatTopic(PubSub.EVENT, ...)
            self.pubsub.publish(event_topic, json.dumps(event_data))
```

### Region Management

Regions are geometric areas with associated analytics:

```python
class Region:
    def __init__(self, name, points, singleton_type=None):
        self.name = name
        self.points = points              # Polygon vertices
        self.objects = {}                 # Current objects in region
        self.entered = {}                 # Recently entered objects
        self.exited = {}                  # Recently exited objects
        self.singleton_type = singleton_type  # For sensor regions
```

## Configuration and Deployment

### Command Line Arguments

```bash
python scene_controller.py \
    --broker mqtt://broker:1883 \
    --resturl http://manager:8000/api \
    --maxlag 1.0 \
    --tracker_config_file config/tracker-config.json \
    --schema_file schema/metadata.schema.json \
    --visibility_topic regulated
```

### Key Configuration Options

- `--maxlag`: Maximum message latency before dropping (seconds)
- `--visibility_topic`: Publication mode (`regulated`, `unregulated`, `none`)
- `--rewrite_bad_time`: Fix timestamps exceeding max lag
- `--rewrite_all_time`: Override all timestamps with current time
- `--ntp`: NTP server for time synchronization

### Docker Integration

The service runs as a containerized microservice:

```dockerfile
FROM python:3.8-slim
COPY requirements-runtime.txt .
RUN pip install -r requirements-runtime.txt
COPY src/ /app/
WORKDIR /app
CMD ["python", "controller-cmd"]
```

## Key Implementation Patterns

### 1. Pub/Sub Message Routing

```python
def onConnect(self, client, userdata, flags, rc):
    # Dynamic subscription management
    for scene in self.scenes:
        for camera in scene.cameras:
            topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera)
            self.pubsub.addCallback(topic, self.handleMovingObjectMessage)
```

### 2. Rate-Regulated Publishing

```python
def publishRegulatedDetections(self, scene_obj, msg_objects, otype, jdata, camera_id):
    now = get_epoch_time()
    if self.shouldPublish(scene['last'], now, 1/scene_obj.regulated_rate):
        # Publish aggregated data
        self.pubsub.publish(topic, jstr)
        scene['last'] = now
```

### 3. Schema-Driven Validation

```python
class SchemaValidation:
    def validateMessage(self, message_type, data, check_format=True):
        validator = self.validator[message_type] if check_format else self.validator_no_format[message_type]
        return validator.is_valid(data)
```

### 4. Thread-Safe Tracking

```python
class Tracking(Thread):
    def __init__(self):
        super().__init__()
        self.queue = Queue()
        
    def run(self):
        while True:
            objects, when, already_tracked = self.queue.get()
            self.trackCategory(objects, when, already_tracked)
```

## Performance Considerations

### 1. Message Processing Optimization

- **Lazy Schema Validation**: Only validate when necessary
- **Batched Processing**: Group operations for efficiency
- **Queue Management**: Prevent tracker queue overflow

### 2. Memory Management

- **Object Pruning**: Remove stale tracks and event data
- **Cache Invalidation**: Refresh scene data periodically
- **Location History Limits**: Bounded object position history

### 3. Rate Limiting

```python
def calculateRate(self):
    # Exponential moving average for rate calculation
    now = get_epoch_time()
    delta = now - self.regulate_last
    self.regulate_rate *= AVG_FRAMES
    self.regulate_rate += delta
    self.regulate_rate /= AVG_FRAMES + 1
```

### 4. Time Synchronization

```python
def adjust_time(now, ntp_server, ntp_client, last_sync, time_offset, ntp_exception):
    # Periodic NTP synchronization with fallback
    if last_sync is None or now - last_sync > TIME_SYNC_INTERVAL:
        try:
            ntp_time = ntp_client.request(ntp_server).tx_time
            time_offset = ntp_time - now
        except ntp_exception:
            pass  # Use previous offset
    return time_offset, now
```

## Troubleshooting and Debugging

### Common Issues and Solutions

#### 1. Message Processing Delays

**Symptoms**: "FELL BEHIND" warnings in logs
**Causes**: High inference latency, network delays
**Solutions**: 
- Increase `--maxlag` parameter
- Enable `--rewrite_bad_time`
- Optimize camera frame rates

#### 2. Tracking Inconsistencies

**Symptoms**: Objects losing identity, duplicate tracks
**Causes**: Poor camera calibration, tracking parameter mismatch
**Solutions**:
- Verify camera pose accuracy
- Adjust tracker configuration
- Check scene coordinate systems

#### 3. Missing Events

**Symptoms**: No region/tripwire events generated
**Causes**: Objects not properly localized, region configuration errors
**Solutions**:
- Validate region polygon definitions
- Check object visibility across cameras
- Verify coordinate transformations

### Debugging Tools

#### 1. Log Analysis

```python
# Enable debug logging
from scene_common import log
log.setLevel(log.DEBUG)
```

#### 2. MQTT Message Inspection

```bash
# Subscribe to all SceneScape topics
mosquitto_sub -h broker -t "scenescape/+/+/+/+"
```

#### 3. REST API Queries

```python
# Inspect scene configuration
curl -H "Authorization: Token <token>" \
     http://manager:8000/api/scene/<scene_id>
```

### Performance Monitoring

Monitor these key metrics:
- Message processing latency
- Tracker queue sizes
- Memory usage patterns
- MQTT connection stability
- Scene update frequencies

## Conclusion

The Scene Controller Service represents a sophisticated real-time data fusion system that bridges computer vision, IoT sensors, and spatial analytics. Its modular architecture enables scalable deployment while maintaining low-latency processing requirements.

Key takeaways for developers:
1. **Event-driven design** enables loose coupling and scalability
2. **Schema validation** ensures data integrity across the pipeline
3. **Configurable tracking** allows optimization for different use cases
4. **Hierarchical scenes** support complex multi-camera deployments
5. **Rate regulation** balances real-time requirements with system resources

Understanding these architectural patterns and implementation details will enable you to effectively extend, debug, and optimize the Scene Controller for your specific use cases.
