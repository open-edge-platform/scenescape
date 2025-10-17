# Design Document: Vision Pipeline API for Domain Experts

- **Author(s)**: Rob Watts <robert.a.watts@intel.com>
- **Date**: 2025-10-07
- **Status**: `Proposed`
- **Related ADRs**: TBD

---

## Overview

This document defines a simple API for connecting cameras, configuring vision analytics pipelines, and accessing object detection metadata. The API enables domain experts to deploy computer vision capabilities without requiring deep technical knowledge of AI models, pipeline configurations, or video processing implementations.

The vision pipeline API abstracts away technical complexity while providing reliable object detection metadata that feeds into downstream systems like Intel SceneScape for multi-camera tracking and scene analytics.

## Goals

- **Simple Camera Management**: Easy API to connect and manage one or many camera inputs dynamically
- **Composable Analytics Pipelines**: Modular pipeline stages that can be chained together (e.g., vehicle detection → license plate detection → OCR) where each stage can be pre-configured but combined flexibly
- **Source Frame Access**: On-demand access to original camera frames regardless of input type or source
- **Performance Optimization**: Easy configuration of hardware acceleration targets (CPU, iGPU, GPU, NPU) for optimal utilization
- **Abstracted Complexity**: Hide AI model management, pipeline optimization details, and video processing complexity from domain experts
- **API-First Design**: Enable development of reference UIs for managing pipelines and sensor sources, supporting integration with SceneScape UI, VIPPET, or customer-implemented interfaces

## Non-Goals

- Advanced computer vision research or custom model training
- Multi-camera tracking and scene analytics (handled by downstream systems like SceneScape)
- Complex video processing workflows or custom pipeline development

## Design Context

### Primary Persona: **Traffic Operations Expert**

- **Background**: Transportation engineer, systems integrator, or traffic management specialist who wants to leverage computer vision to improve traffic flow, safety, and urban mobility
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

1. **Camera Management**: Connect 4-8 cameras dynamically via RTSP streams, USB connections, or video files - add/remove cameras without system restart

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
    class CAM1,CAM2,LIDAR,RADAR sensors
    class MODELS,CALIB config
    class TIME platform
    class DETECTIONS,RAWDATA,DECORATED outputs
```

## Vision Pipeline API Components

### Camera Management API

**Dynamic camera connection and configuration:**

- **Add Camera**: Connect new cameras via RTSP, USB, or file input without system restart
- **Remove Camera**: Disconnect cameras and clean up resources gracefully
- **Camera Status**: Monitor connection health, frame rate, and video quality
- **Camera Configuration**: Set resolution, frame rate, and encoding parameters
- **Multi-Source Support**: Handle mixed camera types (IP cameras, USB webcams, video files) in single deployment

### Pipeline Configuration API

**Composable analytics pipeline stages:**

- **Detection Stages**: Vehicle detection, person detection, general object detection, license plate detection, barcode detection, QR code detection, AprilTag detection
- **Classification Stages**: Vehicle type classification, person attribute classification, object categorization
- **Analysis Stages**: OCR text extraction, barcode decoding, QR code decoding, AprilTag pose estimation, re-identification embedding generation, pose estimation
- **Pipeline Composition**: Chain compatible stages together where outputs of one stage match inputs of the next (e.g., vehicle detection → vehicle classification, license plate detection → OCR, barcode detection → barcode decoding)
- **Compatibility Validation**: System prevents invalid stage chaining when output formats are incompatible (e.g., classification stage cannot feed into detection stage)
- **Parallel Processing**: Support both sequential stage chaining and parallel stage execution for independent analytics on the same input
- **Pre-configured Stages**: Each stage comes with optimized default settings but allows customization
- **Per-Stage Hardware Optimization**: Target each individual stage to specific hardware (CPU, iGPU, GPU, NPU) for optimal performance
- **Pipeline Templates**: Save and reuse common stage combinations across deployments

**Pipeline Stage Architecture:**

- **Self-Contained Processing**: Each stage includes its own pre-processing (data preparation, format conversion) and post-processing (result formatting, filtering, validation)
- **Technology Agnostic**: Stages can run any type of analytics including computer vision (CV), deep learning (DL), traditional image processing, or related technologies
- **Modular Interface**: Standardized input/output interfaces allow stages to be combined regardless of underlying technology
- **Flexible Optimization**: Each stage can be optimized for different performance characteristics and hardware targets, including inter-stage optimizations like buffer sharing on the same device

### Metadata Output API

**MQTT-focused metadata publishing for SceneScape integration:**

- **MQTT Publishing**: All detection metadata published to MQTT brokers in JSON format with procedurally generated topics
- **Batch Processing**: Minimized chatter with one message per batch to reduce network overhead and improve performance
- **Temporal Preservation**: Original frame timestamps preserved along with camera source ID for accurate temporal correlation
- **Updated Schema Availability**: Updated JSON schema provided for downstream metadata validation and integration (output from the pipeline is assumed to be valid against the provided schema)
- **Topic Generation**: MQTT topics are procedurally generated based on camera IDs and pipeline configuration, with optional top-level namespace configuration to prevent user errors

### Frame Access API

**On-demand access to camera frame data:**

- **Near Real-Time Source Frames**: Access undecorated source frames from any camera for calibration workflows and data flow confirmation
- **Near Real-Time Decorated Frames**: Access frames with detection bounding boxes, throughput, labels, and confidence scores overlaid for monitoring video analytics state
- **Web-Streamable Output**: Frame access designed for low-latency streaming into web application UIs (target <100ms latency)
- **Implementation Flexibility**: Frame access may be provided through various methods including REST endpoints, WebRTC streams, WebSocket connections, or dedicated streaming protocols

**Note**: This API specification focuses on near real-time frame access only. Historical frame access (by camera ID and timestamp or timestamp range) is not required for this interface and may be considered as a separate system capability in future versions.

**Performance Note**: Frame access operations must be designed to avoid impacting system throughput or latency whenever possible. Frame retrieval should use separate data paths or buffering mechanisms that do not interfere with real-time analytics processing.

## API Workflows

This section demonstrates common workflows using sequence diagrams to show the API interactions for typical deployment scenarios.

### Add Cameras for Connectivity and Calibration

**Purpose**: Verify camera connectivity and enable downstream calibration without analytics processing.

```mermaid
sequenceDiagram
    participant User as Traffic Engineer
    participant API as Vision Pipeline API
    participant Server as Pipeline Server
    participant Camera as Camera Source
    participant MQTT as MQTT Broker

    User->>API: POST /cameras
    Note over User,API: Configure camera (RTSP URL, resolution, etc.)
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
    participant User as Traffic Engineer
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
    participant User as Traffic Engineer
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
    participant User as Traffic Engineer
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
    participant User as Traffic Engineer
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
    participant User as Traffic Engineer
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
    participant User as Traffic Engineer
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
    participant User as Traffic Engineer
    participant API as Vision Pipeline API
    participant Server as Pipeline Server
    participant MQTT as MQTT Broker
    participant SceneScape as SceneScape System

    Note over User: Existing pipeline processing Camera 1<br/>with Vehicle Detection + Classification
    
    User->>API: POST /pipelines/{pipeline_id}/cameras
    Note over User,API: Add camera to existing pipeline:<br/>- Camera ID: "cam_south"<br/>- RTSP URL, resolution<br/>- Inherits pipeline analytics
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
    participant User as Traffic Engineer
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

## Implementation Considerations

### Coordinate System Management

- **Local Coordinates**: Pipeline outputs positions in camera/sensor coordinate space without knowledge of world coordinates or global scene context
- **Camera Coordinates**: Coordinate output depends on detection model and sensor modality:
  - **Monocular 3D Detectors**: Require intrinsic calibration parameters to estimate depth and convert to 3D camera space
  - **LiDAR/Radar Sensors**: Provide native 3D point cloud data in sensor coordinate space
  - **2D-Only Models**: Most 2D detectors operate natively in image pixel coordinates (x, y within frame dimensions) and it is acceptable to publish detection results in these units
- **World Coordinate Transformation**: External responsibility using extrinsic calibration data (handled by downstream systems like SceneScape)
- **Multi-Sensor Fusion**: Requires external coordinate system reconciliation and cross-sensor tracking - accomplished outside of the pipeline scope
- **Single-Sensor Scope**: Vision pipeline operates independently within individual sensor coordinate systems, maintaining clear boundaries

### Performance Considerations

- **Resource Management**: Interface should specify computational and memory requirements per pipeline stage for capacity planning
- **Hardware Targeting**: Enable per-stage optimization across CPU, iGPU, GPU, and NPU resources for balanced performance
- **Latency Requirements**: Support configurable real-time guarantees based on application needs (e.g., <15ms latency for traffic safety may cause more frames to be dropped and consequent drop in throughput)
  - Latency and throughput are not always inversely related when parallel operations are possible, such as cross-camera batching
- **Throughput Scaling**: Additional concurrent sensor streams should be optimized using techniques such as cross-sensor/camera batching and other methods that minimize latency and maximize throughput as much as possible
- **System Headroom**: Enable configuration of available computational headroom reserved for other workloads to prevent pipeline overload
- **Dynamic Load Balancing**: Support runtime adjustment of processing priorities based on system load and application criticality

### Time Coordination

- **System Requirements**: Time synchronization must be better than the dynamic observability of the system; e.g., monitoring scenes with faster moving objects requires better time precision
- **Precision Timestamping**: Spatiotemporal fusion requires precision timestamping, ideally at the moment of sensor data acquisition (before encoding, transmission, and other operations)
- **Platform Responsibility**: Implementation of time synchronization is the responsibility of the hardware+OS platform and is outside the scope of the pipeline server (system timestamps are assumed to be synchronized)
  - Various technologies may be applied, including NTP, IEEE 1588 PTP, time sensitive networking (TSN), GPS PPS, and related capabilities
- **Fallback Options**: Time synchronization may not always be possible at frame acquisition, and late timestamping may be the only viable option; in this case, a configurable latency offset may need to be applied (backdating the timestamp by some configurable amount on a per-camera and/or per camera batch basis) when the frame arrives at the pipeline

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

---

## Conclusion

This vision pipeline interface definition provides a clean separation between sensor inputs, configuration inputs, and standardized outputs. By focusing on the interface rather than implementation details, it enables technology-agnostic pipeline development while supporting debugging, validation, and gradual enhancement of existing robust pipeline technologies.

The interface is motivated by SceneScape's architectural needs but designed as a reusable specification for any computer vision application requiring clear, maintainable pipeline boundaries built on proven technologies.
