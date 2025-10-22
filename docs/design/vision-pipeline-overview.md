# Design Document: Vision Pipeline API for Domain Experts

- **Author(s)**: Rob Watts <robert.a.watts@intel.com>
- **Date**: 2025-10-21
- **Status**: `Proposed`
- **Related ADRs**: TBD

---

## Overview

This document defines a simple REST API for connecting cameras, configuring vision analytics pipelines, and managing pipeline metadata publishing. The API enables domain experts to deploy computer vision capabilities without requiring deep technical knowledge of AI models, pipeline configurations, or video processing implementations.

A **domain expert** in this context is a consumer of the video analytics pipeline who has expertise in a given field that is not computer vision. They understand their domain-specific requirements and goals but prefer to focus on their area of expertise rather than the technical complexities of computer vision implementation.

The vision pipeline API abstracts away technical complexity while providing reliable object detection metadata that feeds into downstream systems like Intel SceneScape for multi-camera tracking and scene analytics.

## Core Operating Principles

The vision pipeline API is built on three fundamental principles:

**1. Production Robustness**: The pipeline must maintain continuous operation in dynamic production environments. Common scenarios such as network jitter, RTSP stream timeouts, camera power cycling, pipeline stage model updates, hardware acceleration target changes (switching between CPU, GPU, NPU), and MQTT broker reconnections should have minimal impact on running pipelines, including minimizing restarts or loss of metadata output when changes or errors occur in any aspect of the system.

**2. Domain Expert Accessibility**: The pipeline must be easily configurable by domain experts without requiring deep technical knowledge of computer vision implementations. All operations should be intuitive, well-documented, and abstracted from underlying technical complexity while maintaining full functionality and flexibility.

**3. Modular Manageability**: System components (cameras, pipelines, and pipeline stages) must be defined once and connected together in modular ways. Cameras are managed independently from pipelines, pipelines are managed independently from cameras, and pipeline stages are reusable across different pipeline configurations. This "define once, connect many" approach dramatically reduces configuration complexity, eliminates duplication, and enables rapid deployment changes without system-wide reconfiguration.

## Goals

- **Simple Camera Management**: Easy API to connect and manage one or many camera inputs dynamically
- **Composable Analytics Pipelines**: Modular pipeline stages that can be chained together (e.g., vehicle detection → license plate detection → OCR) where each pre-configured stage can be flexibly combined and downstream stages operate on the output of the previous stage only (and do not operate at all when stage output is null)
- **Source Frame Access**: On-demand access to original camera frames regardless of input type or source
- **Performance Optimization**: Easy configuration of hardware acceleration targets (CPU, iGPU, GPU, NPU) for optimal utilization with automatic but configurable hardware acceleration for all operations where possible
- **Abstracted Complexity**: Hide AI model management, pipeline optimization details, and video processing complexity from domain experts
- **API-First Design**: Enable development of reference UIs for managing pipelines and sensor sources, supporting integration with SceneScape UI, VIPPET, or customer-implemented interfaces

## Non-Goals

- Advanced computer vision research or custom model training
- Multi-camera tracking and scene analytics (handled by downstream systems like SceneScape)
- Complex video processing workflows or custom pipeline development

## Design Context

### Primary Persona: **Traffic Operations Expert**

- **Background**: Independent Software Vendor (ISV) engineer working with a city to build smart intersections to improve traffic flow, safety, and urban mobility
- **Goal**: Deploy smart intersection systems that provide actionable traffic insights and automated responses without requiring deep computer vision expertise
- **Technical Level**: Understands traffic engineering, urban planning, and sensor networks but has limited computer vision knowledge; wants to focus on traffic optimization, not algorithm configuration
- **Pain Points**:

  - Complex vision systems obscure traffic engineering value
  - Difficulty translating traffic requirements into vision configurations
  - Unclear what vision capabilities are available for traffic applications
  - Technical complexity prevents rapid deployment and testing of traffic solutions

### Use Case: "Vision Pipeline API for Traffic Monitoring"

A traffic operations expert wants to deploy vision analytics at a busy intersection to feed object detection metadata into their Intel SceneScape system for multi-camera tracking and scene analytics.

**API Requirements:**

1. **Camera Management**: Dynamically connect 4-8 cameras using various input methods (RTSP streams, MJPEG streams, WebRTC streams, USB connections, or offline video files) with fast, API-driven camera addition and removal that handles backend operations transparently

2. **Pipeline Composition**: Compose analytics pipelines by chaining stages together:

   - Vehicle detection → license plate detection → OCR
   - Person detection → re-identification embedding generation
   - General object detection → vehicle classification
   - Custom combinations based on specific needs

3. **Metadata Output**: Send detection results to MQTT broker for SceneScape processing:

   - JSON format with validated schema structure
   - Batched messages to minimize network chatter
   - Preserved frame timestamps and camera source IDs
   - Procedurally generated MQTT topics with optional namespace configuration

4. **Source Frame Access**: Provide on-demand access to original camera frames for debugging, validation, and manual review - regardless of camera type or connection method

They want to say: Connect these cameras, run vehicle and person detection, send metadata to SceneScape via MQTT and have a simple API that handles all the technical complexity - without needing to understand AI model formats, video decoding, or pipeline optimization.

The vision pipeline interface enables this by providing:

- **Intuitive Input/Output Selection**: Ability to independently select and configure sensor inputs and desired outputs
- **Modular Component Configuration**: Modular approach to configuring video analytics components (detection, tracking, classification)
- **Standardized Abstraction**: Clean separation between data streams, algorithmic configuration, and output products
- **Technology Independence**: Interface that works with any underlying pipeline implementation

## Vision Pipeline Interface

### Interface Definition

The vision pipeline interface defines a clear contract between data inputs, processing components, and outputs. This interface can be implemented by any computer vision technology stack.

```mermaid
flowchart LR
    subgraph Inputs["Inputs"]
        subgraph SensorInputs["Sensor Inputs"]
            CAM1["Camera 1<br/>Source Video"]
            CAM2["Camera 2<br/>Source Video"] 
            LIDAR["LiDAR<br/>Point Cloud"]
            RADAR["Radar<br/>Point Cloud"]
            AUDIO["Audio<br/>Sound Data"]
        end
        
        subgraph ConfigInputs["Configuration Inputs"]
            MODELS["AI Models<br/>Detection/Classification"]
            CALIB["Calibration Data<br/>Intrinsics + Distortion"]
        end
        
        subgraph PlatformInputs["Platform Inputs"]
            TIME["Synchronized System Time<br/>(timestamps, time sync)"]
        end
    end
    
    subgraph Pipeline["Vision Pipeline"]
        VIDEO["Video Processing<br/>Decode → Detect → Single-Camera Track → Embed → Classify"]
        POINTCLOUD["Point Cloud Processing<br/>Segment → Detect → Single-Sensor Track → Embed"]
    end
    
    subgraph Outputs["Pipeline Outputs"]
        DETECTIONS["Object Detections & Tracks<br/>(bounding boxes, classifications, temporal associations, IDs, embeddings)"]
        RAWDATA["Source Data<br/>(original frames, point clouds)"]
        DECORATED["Decorated Data<br/>(annotated images, segmented point clouds)"]
    end
    
    %% Styling
    classDef pipeline fill:#fff8e1,stroke:#ff8f00,stroke-width:3px,color:#000000
    classDef sensors fill:#e8f5e8,stroke:#388e3c,stroke-width:2px,color:#000000
    classDef config fill:#e3f2fd,stroke:#1976d2,stroke-width:2px,color:#000000
    classDef platform fill:#fce4ec,stroke:#c2185b,stroke-width:2px,color:#000000
    classDef outputs fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,color:#000000
    
    class VIDEO,POINTCLOUD pipeline
    class CAM1,CAM2,LIDAR,RADAR,AUDIO sensors
    class MODELS,CALIB config
    class TIME platform
    class DETECTIONS,RAWDATA,DECORATED outputs
```

### Multimodal Input Support

While this document primarily focuses on camera-based vision systems, the interface is designed to establish a unified approach that accommodates multiple sensor modalities including 3D point-cloud sources and audio data. This multimodal architecture ensures the API can support sensor fusion applications where different sensors contribute complementary information:

- **Cameras**: Provide high-resolution visual data for object detection, classification, and visual analytics
- **LiDAR/Radar**: Contribute precise spatial positioning, distance measurements, and velocity data through 3D point-cloud processing
- **Audio**: Enable acoustic event detection, sound classification, and audio-visual correlation for comprehensive scene understanding

The interface design anticipates the growing prevalence of multimodal sensing in computer vision deployments, such as demonstrated in the Sensor Fusion for Traffic Management sample application (formerly TFCC) in the Metro AI Suite. All general requirements, API patterns, and architectural principles described in this document apply to multimodal data sources, even while cameras remain the primary sensor type in current implementations.

## Vision Pipeline API Components

### Camera Management API

**Camera-Pipeline Separation**: Cameras are managed independently from pipeline configuration, dramatically improving system manageability through modular design. Each camera is defined once with its connection details and properties, then can be dynamically connected to any compatible pipeline without reconfiguration. A single camera can feed into multiple pipelines for different analytics, while a single pipeline can process video from multiple cameras simultaneously. This modular approach eliminates configuration duplication, reduces operational complexity, and enables rapid deployment changes without system-wide reconfiguration.

**Dynamic camera connection and configuration:**

- **Add Camera**: Connect new cameras via RTSP, MJPEG, WebRTC, USB, or file input
- **Remove Camera**: Disconnect cameras and clean up resources gracefully
- **Camera Configuration**: Set resolution, frame rate, and encoding parameters
- **Camera Properties**: Configure camera intrinsics and distortion parameters, with support for dynamically updating these values in near real-time to support zoom cameras
- **Default Configuration**: Apply sensible defaults when configuration parameters are not explicitly provided, minimizing setup complexity for common camera types and use cases
- **JSON Configuration**: All camera configuration handled through JSON-only payloads for consistent API interaction
- **Multi-Source Support**: Handle mixed camera types (IP cameras, USB webcams, video files) in single deployment
- **Robust Error Handling**: Comprehensive error handling for network issues, frame corruption, authentication failures, and protocol incompatibilities with detailed logging, while maintaining pipeline operation when possible
- **Connection Resilience**: Automatic retry mechanisms with configurable backoff strategies for network interruptions and camera disconnections
- **Persistent Reconnection**: Optional continuous reconnection attempts that persist indefinitely until cameras return online, maintaining system resilience during extended outages

The following examples demonstrate adding cameras independently of pipeline configuration. Each camera inherits sensible system defaults (such as auto-detected resolution, frame rate, and default intrinsics) while allowing selective override of specific parameters when needed. Cameras can be added without concern for what analytics pipelines will eventually process their video streams.

**Example Configuration (RTSP Camera):**
```json
{
  "camera_id": "cam_north",
  "source": "rtsp://192.168.1.100:554/stream1"
}
```

**Example Configuration (USB Camera):**
```json
{
  "camera_id": "cam_usb",
  "source": "/dev/video0"
}
```

**Example Configuration (MJPEG Camera):**
```json
{
  "camera_id": "cam_mjpeg",
  "source": "http://192.168.1.102:8080/video"
}
```

**Example Configuration (RTSP with Authentication and Custom Intrinsics):**
```json
{
  "camera_id": "cam_south", 
  "source": "rtsp://admin:camera_pass@192.168.1.101:554/stream1",
  "intrinsics": [
    [1000.0, 0.0, 960.0],
    [0.0, 1000.0, 540.0],
    [0.0, 0.0, 1.0]
  ],
  "distortion": [-0.1, 0.05, 0.0, 0.0, -0.01]
}
```

### Pipeline Configuration API

**Pipeline-Camera Independence**: Pipelines are defined and managed independently from camera sources, significantly improving system manageability through reusable analytics configurations. Each pipeline is defined once with its analytics stages and processing requirements, then can be applied to any compatible camera or set of cameras without modification. This modular approach eliminates the need to recreate identical analytics configurations for each camera, reduces maintenance overhead, and enables consistent analytics behavior across diverse camera deployments. Pipeline definitions become reusable assets that can be instantly deployed across new camera installations.

**Pipeline Stage Types:**

The following stage types represent common analytics capabilities that can be configured and chained together. These are examples of the types of stages available - the system is designed to support additional stage types and custom analytics as needed.

- **Detection Stages**: Vehicle detection, person detection, general object detection, license plate detection, oriented bounding box detection, segmentation, keypoint detection, 3D bounding box detection
- **Classification Stages**: Generate text labels for vehicle types, person attributes, object categories, age/gender, personal protective equipment, mask wearing, and image-to-text descriptions
- **Analysis Stages**: OCR text extraction, barcode detection/decoding, QR code detection/decoding, AprilTag detection/decoding, re-identification embedding generation, pose estimation

**Pipeline Stage Requirements:**

- **MQTT Broker Configuration**: Each pipeline must specify the MQTT broker connection details where metadata will be published, including broker host, port, authentication credentials, TLS settings, and optional topic namespace prefix
- **Multi-Camera Processing**: Pipelines can simultaneously process video from multiple cameras, applying identical analytics configurations across all camera sources while maintaining per-camera metadata identification
- **Pipeline Composition**: Chain compatible stages together where outputs of one stage match inputs of the next (e.g., vehicle detection → vehicle classification, license plate detection → OCR)
- **Compatibility Validation**: System prevents invalid stage chaining when output formats are incompatible (e.g., classification stage cannot feed into detection stage)
- **Parallel and Sequential Processing**: Support both sequential stage chaining and parallel stage execution for independent analytics on the same input
- **Pre-configured Stages**: Each stage comes with optimized default settings but allows customization
- **Per-Stage Hardware Optimization**: Target each individual stage to specific hardware (CPU, iGPU, GPU, NPU) for optimal performance
- **Pipeline Templates**: Save and reuse common stage combinations across deployments
- **Configuration Schema Availability**: JSON schema for pipeline and stage configurations provided via API endpoints for validation and tooling integration, ideally with a single extensible schema for all possible pipeline configurations
- **Stage Input/Output Behavior**: A given stage operates on the output of the previous stage (or the original frame for the first stage), and may operate on an array of outputs from that single previous stage
- **Unscaled Image Data Output**: For stages that output image-like data (rather than text data), the output must refer to the unscaled portion of the input associated with the detection, such as the bounding box or a masked output of oriented bounding box or instance segment
- **Metadata Collation**: Whenever a stage runs, the metadata is collated into a single object array per chain, with a property key defined by each stage that has run (e.g. when `vehicle+lpd+lpr` finds a vehicle but no plate, the metadata will have an empty `"lpd: []"` array to indicate the stage ran but found nothing, and no `lpr` value exists because it didn't run)
- **Guaranteed Output**: Every frame input must have a resultant metadata output, even if nothing is detected (not detecting something is also an important result)
- **Source Frame Coordinates**: All collated metadata is reported in source frame coordinates for staged operations, e.g. vehicle bounding box and the license plate bounding box are both reported in original frame pixel units

**Pipeline Stage Architecture:**

- **Self-Contained Processing**: Each stage includes its own pre-processing (data preparation, format conversion) and post-processing (result formatting, filtering, validation)
- **Technology Agnostic**: Stages can run any type of analytics including computer vision (CV), deep learning (DL), traditional image processing, or related technologies
- **Modular Interface**: Standardized input/output interfaces allow stages to be combined regardless of underlying technology, dramatically improving system manageability by enabling stage reuse across different pipelines
- **Flexible Optimization**: Each stage can be optimized for different performance characteristics and hardware targets, including inter-stage optimizations like buffer sharing on the same device
- **Define Once, Connect Many**: Pipeline stages are defined once with their analytics capabilities and requirements, then can be dynamically connected into different pipeline configurations without modification, reducing configuration complexity and enabling rapid analytics deployment

### Frame Access API

**On-demand access to camera frame data:**

- **Near Real-Time Source Frames**: Access undecorated source frames from any camera for calibration workflows and data flow confirmation
- **Near Real-Time Decorated Frames**: Access frames with detection bounding boxes, throughput, labels, and confidence scores overlaid for monitoring video analytics state
- **Web-Streamable Output**: Frame access designed for low-latency streaming into web application UIs (target <100ms latency)
- **Implementation Flexibility**: Frame access may be provided through various methods including REST endpoints, WebRTC streams, WebSocket connections, or dedicated streaming protocols

**Note**: This API specification focuses on near real-time frame access only. Historical frame access (by camera ID and timestamp or timestamp range) is not required for this interface and may be considered as a separate system capability in future versions.

**Performance Note**: Frame access operations must be designed to avoid impacting system throughput or latency whenever possible. Frame retrieval should use separate data paths or buffering mechanisms that do not interfere with real-time analytics processing.

### System Monitoring API

**Observability endpoints for system health and performance:**

- **Health Check Endpoints**: System-wide health status including API availability, pipeline server status, and MQTT broker connectivity
- **Hardware Enumeration**: Discovery endpoint that returns available hardware accelerators on the platform, providing device identifiers that can be used in pipeline stage configuration (e.g., "CPU", "GPU.0", "GPU.1", "NPU.0", "iGPU") along with device capabilities, memory specifications, and current availability status
- **Camera Monitoring**: Per-camera connection status, frame rate statistics, error counts, and reconnection attempt history
- **Pipeline Performance**: Per-pipeline throughput metrics, processing latency measurements, and resource utilization statistics
- **Resource Monitoring**: Hardware utilization metrics for CPU, GPU, NPU, and memory across all pipeline stages
- **Error Rate Tracking**: Aggregated error rates and failure patterns across cameras, pipelines, and individual processing stages
- **System Metrics Export**: Prometheus-compatible metrics export for integration with existing monitoring infrastructure
- **Alert Integration**: Configurable thresholds and alert generation for proactive issue detection and notification

## Metadata Output

**MQTT-focused metadata publishing for SceneScape integration:**

- **MQTT Publishing**: All detection metadata published to MQTT brokers in JSON format
- **Batch Processing**: Minimized chatter with one message per batch to reduce network overhead and improve performance
- **Individual Frame Timestamps**: Each frame maintains its individual timestamp within batched messages for accurate temporal correlation
- **Camera Source Identification**: Each frame preserves its camera source ID within batch metadata
- **Cross-Camera Batching**: Frames are captured and batched across cameras within small time windows for efficiency
- **Original Timing Preservation**: Each frame's metadata preserves its original capture timestamp and camera identifier
- **Metadata Schema Availability**: JSON schemas for detection metadata provided via dedicated API endpoints for programmatic validation and integration
- **Clean Configuration**: Schema artifacts must not be included in configuration JSON to maintain separation of concerns
- **Topic Generation**: MQTT topics procedurally generated based on camera IDs and pipeline configuration with optional namespace configuration

## API Workflows

This section demonstrates common workflows using sequence diagrams to show the API interactions for typical deployment scenarios.

### Add Cameras for Connectivity and Calibration

**Purpose**: Verify camera connectivity and enable downstream calibration without analytics processing.

```mermaid
sequenceDiagram
    participant User
    participant API as Vision Pipeline API
    participant Server as Pipeline Server
    participant Camera as Camera Source
    participant MQTT as MQTT Broker

    User->>API: POST /cameras
    Note over User,API: Configure camera<br/>(RTSP URL, camera ID, etc.)
    API->>Server: Create camera instance
    Server->>Camera: Establish connection
    Camera-->>Server: Video stream
    Server->>MQTT: Publish camera status (connected)
    API-->>User: Camera ID and status
    
    Note over User,MQTT: Camera running in free-run mode<br/>Source frames available for calibration<br/>No analytics processing yet
```

### Add Single Pipeline Stage and Verify Results

**Purpose**: Add analytics processing to connected cameras and verify output in SceneScape.

```mermaid
sequenceDiagram
    participant User
    participant API as Vision Pipeline API
    participant Server as Pipeline Server
    participant MQTT as MQTT Broker
    participant SceneScape as SceneScape System

    User->>API: POST /pipelines
    Note over User,API: Configure pipeline:<br/>- Camera ID<br/>- Stage: Vehicle Detection<br/>- Hardware: GPU
    API->>Server: Create pipeline with detection stage
    Server->>Server: Start analytics processing
    Server->>MQTT: Publish detection metadata
    MQTT->>SceneScape: Forward detection data
    SceneScape->>SceneScape: Process multi-camera tracking
    SceneScape->>MQTT: Publish tracks and properties
    MQTT-->>User: Track data available for consumption
    SceneScape-->>User: Visual verification in SceneScape UI
    
    User->>API: Request decorated frames for camera
    API-->>User: Stream frames with detection overlays
    Note over User: Visual verification of detections<br/>Complete data flow: detections → tracks → properties
```

### Modify Pipeline Stage Model

**Purpose**: Change the analytics model for an existing pipeline stage.

```mermaid
sequenceDiagram
    participant User
    participant API as Vision Pipeline API
    participant Server as Pipeline Server
    participant MQTT as MQTT Broker

    User->>API: PUT /pipelines/{pipeline_id}/stages/{stage_id}
    Note over User,API: Update stage configuration:<br/>- Change from Vehicle Detection<br/>- To Person Detection
    API->>Server: Send pipeline configuration change
    Server->>Server: Cleanup detection resources
    Server->>Server: Initialize person detection
    Server->>Server: Resume analytics processing
    Server->>MQTT: Publish updated metadata
    API-->>User: Stage update confirmation
    
    Note over Server,MQTT: Pipeline now outputs<br/>person detection data
```

### Modify Camera Configuration

**Purpose**: Update camera properties like camera ID with graceful system handling.

```mermaid
sequenceDiagram
    participant User
    participant API as Vision Pipeline API
    participant Server as Pipeline Server
    participant MQTT as MQTT Broker

    User->>API: PUT /cameras/{camera_id}
    Note over User,API: Update camera config:<br/>- Change camera ID<br/>- From "cam_01"<br/>- To "cam_north"
    API->>Server: Update camera metadata
    Server->>Server: Apply configuration changes
    Server->>Server: Update internal camera references
    Server->>MQTT: Publish with updated camera ID
    API-->>User: Camera update confirmation
    
    Note over Server,MQTT: System gracefully handles<br/>camera ID changes
```

### Delete Camera

**Purpose**: Remove camera and clean up all associated resources.

```mermaid
sequenceDiagram
    participant User
    participant API as Vision Pipeline API
    participant Server as Pipeline Server
    participant MQTT as MQTT Broker

    User->>API: DELETE /cameras/{camera_id}
    API->>Server: Initiate camera deletion
    Server->>Server: Stop associated pipelines
    Server->>Server: Cleanup analytics resources
    Server->>Server: Disconnect from camera source
    Server->>MQTT: Publish camera offline status
    Server->>Server: Remove camera instance
    API-->>User: Deletion confirmation
    
    Note over Server: All camera resources cleaned up<br/>Associated pipelines terminated
```

### Add Sequential Pipeline Stages

**Purpose**: Chain multiple analytics stages for complex processing workflows.

```mermaid
sequenceDiagram
    participant User
    participant API as Vision Pipeline API
    participant Server as Pipeline Server
    participant MQTT as MQTT Broker

    Note over User: Existing pipeline: Vehicle Detection
    
    User->>API: POST /pipelines/{pipeline_id}/stages
    Note over User,API: Add classification stage:<br/>- Input: Vehicle detections<br/>- Stage: Vehicle Type Classification<br/>- Hardware: NPU
    API->>Server: Validate stage compatibility
    Server->>Server: Create classification stage
    Server->>Server: Link detection → classification
    Server->>Server: Start chained processing
    
    Note over Server: Processing chain:<br/>1. Vehicle Detection (GPU)<br/>2. Vehicle Classification (NPU)
    
    Server->>MQTT: Publish enhanced metadata
    Note over MQTT: Detection + classification data<br/>in single message batch
    API-->>User: Stage addition confirmation
```

### Add Parallel Pipeline Stages

**Purpose**: Add concurrent analytics processing for independent object types on the same camera input.

```mermaid
sequenceDiagram
    participant User
    participant API as Vision Pipeline API
    participant Server as Pipeline Server
    participant MQTT as MQTT Broker

    Note over User: Existing pipeline: Vehicle Detection
    
    User->>API: POST /pipelines/{pipeline_id}/stages
    Note over User,API: Add parallel stage:<br/>- Input: Source camera frames<br/>- Stage: Person Detection<br/>- Hardware: GPU<br/>- Mode: Parallel
    API->>Server: Validate parallel stage configuration
    Server->>Server: Create person detection stage
    Server->>Server: Configure parallel processing
    Server->>Server: Start concurrent analytics
    
    Note over Server: Parallel processing:<br/>1. Vehicle Detection (GPU)<br/>2. Person Detection (GPU)<br/>Both processing same input frames
    
    Server->>Server: Merge results from parallel stages
    Server->>MQTT: Publish combined metadata
    Note over MQTT: Single message with unified detection list:<br/>All vehicle + person detections<br/>from concurrent analytics
    API-->>User: Parallel stage addition confirmation
```

### Add Additional Camera to Existing Pipeline

**Purpose**: Scale pipeline to process multiple cameras with batched MQTT output while preserving individual camera metadata.

```mermaid
sequenceDiagram
    participant User
    participant API as Vision Pipeline API
    participant Server as Pipeline Server
    participant MQTT as MQTT Broker
    participant SceneScape as SceneScape System

    Note over User: Existing pipeline processing Camera 1<br/>with Vehicle Detection + Classification
    
    User->>API: POST /pipelines/{pipeline_id}/cameras
    Note over User,API: Add camera to existing pipeline:<br/>- Camera ID: "cam_south"<br/>- RTSP URL<br/>- Inherits pipeline analytics
    API->>Server: Create camera and add to pipeline
    Server->>Server: Establish camera connection
    Server->>Server: Configure multi-camera batching
    Server->>Server: Apply existing analytics to new camera
    
    Note over Server: Processing both cameras:<br/>Camera 1 + Camera 2<br/>→ Detection + Classification
    
    Server->>Server: Batch results from both cameras
    Server->>MQTT: Publish aggregated batch
    Note over Server,MQTT: Single MQTT message containing:<br/>- Camera 1 detections (ID + timestamp)<br/>- Camera 2 detections (ID + timestamp)<br/>- Preserved individual metadata
    
    MQTT->>SceneScape: Process batched multi-camera data
    API-->>User: Camera addition confirmation
```

### Retrieve Pipeline Overview

**Purpose**: Request and view all pipelines with their associated cameras and sensors for system-wide inspection.

```mermaid
sequenceDiagram
    participant User
    participant API as Vision Pipeline API
    participant Server as Pipeline Server

    User->>API: GET /pipelines
    Note over User,API: Request all pipeline configurations
    API->>Server: Retrieve system-wide pipeline data
    Server->>Server: Collect all pipeline configurations
    Server->>Server: Include associated cameras and stages
    API-->>User: Complete pipeline overview (JSON format)
    Note over User: UI displays system overview:<br/>- All active pipelines<br/>- Camera assignments<br/>- Stage configurations<br/>- Resource utilization
```

**Note**: The JSON response format is designed to be compatible with web-based graph visualization tools, enabling interactive pipeline diagrams where cameras appear as input nodes, stages as processing nodes, and data flows as connecting edges.

## Implementation Requirements

### Coordinate System Management

- **Local Coordinates**: Pipeline outputs positions in camera/sensor coordinate space without knowledge of world coordinates or global scene context
- **Camera Coordinates**: Coordinate output depends on detection model and sensor modality:
  - **Monocular 3D Detectors**: Require intrinsic calibration parameters to estimate depth and convert to 3D camera space
  - **LiDAR/Radar Sensors**: Provide native 3D point cloud data in sensor coordinate space
  - **2D-Only Models**: Most 2D detectors operate natively in image pixel coordinates (x, y within frame dimensions) and it is acceptable to publish detection results in these units
- **World Coordinate Transformation**: External responsibility using extrinsic calibration data (handled by downstream systems like SceneScape)
- **Multi-Sensor Fusion**: Requires external coordinate system reconciliation and cross-sensor tracking - accomplished outside of the pipeline scope
- **Single-Sensor Scope**: Vision pipeline operates independently within individual sensor coordinate systems, maintaining clear boundaries

### Time Coordination

- **System Requirements**: Time synchronization must be better than the dynamic observability of the system; e.g., monitoring scenes with faster moving objects requires better time precision
- **Precision Timestamping**: Spatiotemporal fusion requires precision timestamping, ideally at the moment of sensor data acquisition (before encoding, transmission, and other operations)
- **Platform Responsibility**: Implementation of time synchronization is the responsibility of the hardware+OS platform and is outside the scope of the pipeline server (system timestamps are assumed to be synchronized)
  - Various technologies may be applied, including NTP, IEEE 1588 PTP, time sensitive networking (TSN), GPS PPS, and related capabilities
- **Fallback Options**: Time synchronization may not always be possible at frame acquisition, and late timestamping may be the only viable option; in this case, a configurable latency offset may need to be applied (backdating the timestamp by some configurable amount on a per-camera and/or per camera batch basis) when the frame arrives at the pipeline
- **Distributed System Architecture**: In many deployments, the system operates in a distributed manner across edge clusters with various processing stages running on different compute nodes. This distributed architecture requires robust time synchronization across network boundaries and careful consideration of network latency when correlating timestamped data between processing stages.

### Performance Considerations

- **Resource Management**: Interface should specify computational and memory requirements per pipeline stage for capacity planning
- **Hardware Targeting**: Enable per-stage optimization across CPU, iGPU, GPU, and NPU resources for balanced performance
- **Throughput Scaling**: Additional concurrent sensor streams should be optimized using techniques such as cross-sensor/camera batching and other methods that minimize latency and maximize throughput as much as possible
- **System Headroom**: Enable configuration of available computational headroom reserved for other workloads to prevent pipeline overload
- **Dynamic Load Balancing**: Support runtime adjustment of processing priorities based on system load and application criticality

### Latency Requirements

Latency is critical for real-time operation and must be configurable based on application needs (e.g., <15ms for traffic safety applications).

- **Real-Time Priority**: Low latency is essential for safety-critical applications where delayed responses can impact traffic flow and safety
- **Critical Use Cases**: Ultra-low latency enables mission-critical applications such as CV2X signaling for jaywalking detection, adaptive traffic light controls using pedestrian monitoring, and collision avoidance systems where milliseconds can prevent accidents
- **Latency vs Throughput Trade-offs**: Strict latency requirements may necessitate dropping frames to maintain real-time guarantees, but parallel operations like cross-camera batching can optimize both
- **End-to-End Optimization**: Minimize total pipeline latency from camera data acquisition through analytics output using multiple techniques:
  - Avoid unnecessary streaming/restreaming stages that add buffering delays
  - Implement cross-camera batching to process multiple camera feeds simultaneously for improved GPU utilization
  - Use direct memory access (DMA) and zero-copy operations between pipeline stages
  - Optimize network configurations with dedicated VLANs, jumbo frames, and quality of service (QoS) settings
  - Minimize intermediate data serialization and format conversions
  - Configure hardware-specific optimizations like GPU memory pooling and CPU affinity
  - Implement frame skipping strategies under high load to maintain real-time guarantees
- **IP Camera Protocol Selection**: Both RTSP and MJPEG streaming protocols must be supported (robust MJPEG support was lacking in DLS-PS). MJPEG can provide significant latency improvements compared to RTSP (typical: MJPEG ~50-100ms vs RTSP ~500-2000ms+, with some configurations experiencing even higher delays) at the cost of 3-5x higher bandwidth usage, making MJPEG preferable for edge deployments with local network connectivity

### Server Architecture

- **Single Server Instance**: One persistent server instance per compute node manages all vision pipelines, eliminating configuration complexity from multiple service instances
- **Always Running**: Server instance maintains continuous availability, managing pipeline lifecycle internally without requiring external service management
- **Pipeline Management**: Server handles creation, configuration, monitoring, and cleanup of individual pipelines through a unified API interface
- **Port Consolidation**: All pipeline operations accessible through single API endpoint, avoiding the configuration challenges of multiple services on different ports
- **Resource Coordination**: Centralized server enables optimal resource allocation and conflict resolution across concurrent pipelines
- **Simplified Deployment**: Single service deployment model reduces operational complexity compared to per-pipeline service instances

### Pipeline Stage Management

A pipeline stage represents a single operation such as a detection or classification step that includes its pre- and post-processing operations. It can represent any number of types of analytics, including deep learning, computer vision, transformer, or other related operations.

- **Initial Configuration**: Pipeline stages can be initially managed through manual configuration files or system administration tools
- **Stage Discovery**: System should provide mechanisms to discover available analytics stages and their capabilities (input/output formats, hardware requirements)
- **Stage Validation**: Automated validation of stage compatibility when composing pipelines to prevent invalid configurations
- **Stage Versioning**: Support for multiple versions of analytics stages to enable gradual upgrades and rollback capabilities
- **Customer Extensibility**: Future capability for customers to register custom analytics stages through standardized interfaces
- **Configuration Templates**: Pre-built stage combinations and templates for common use cases to simplify deployment
- **Runtime Management**: Eventually support dynamic loading and unloading of analytics stages without service restart
- **Stage Management Service**: Future consideration for a dedicated stage management service, particularly when integrated with a model server for centralized analytics lifecycle management

### Security Considerations

Security requirements including authentication, authorization, data encryption, and access control are not covered in this document but must be considered in the implementation. Security architecture, threat models, and hardening procedures will be documented in a separate security and hardening guide.

---

## Conclusion

This vision pipeline interface definition is built on three core operating principles that drive both technical excellence and business value: **Production Robustness** ensures reliable operation in dynamic environments, **Domain Expert Accessibility** enables non-specialists to deploy sophisticated computer vision capabilities, and **Modular Manageability** provides unprecedented flexibility through reusable, composable components.

This principled approach delivers significant customer benefits that accelerate adoption and reduce time to market. Domain experts can rapidly deploy computer vision solutions without deep technical expertise, while the modular architecture eliminates configuration duplication and enables instant reuse of analytics across diverse deployments. The clean separation between cameras, pipelines, and stages dramatically reduces integration complexity and operational overhead.

The modular composability of pipeline components also enables automated optimization of hardware platforms. Since cameras, analytics stages, and acceleration targets are independently configurable, optimization systems can dynamically reassign workloads across CPU, GPU, and NPU resources based on real-time performance metrics and system load, maximizing throughput while maintaining quality of service guarantees.

By focusing on interface definitions rather than implementation details, this specification enables technology-agnostic pipeline development while supporting debugging, validation, and gradual enhancement of existing robust pipeline technologies. The interface is motivated by SceneScape's architectural needs but designed as a reusable specification for any computer vision application requiring clear, maintainable pipeline boundaries built on proven technologies.
