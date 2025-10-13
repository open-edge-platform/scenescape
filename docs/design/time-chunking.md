# Time-Chunking Architecture for SceneScape Controller

## Current Architecture: Per-Category Tracker Threads (SceneScape v1.4)

```mermaid
sequenceDiagram
    participant MB as MQTT Broker
    participant SC as SceneController
    participant PT as Person Thread
    participant VT as Vehicle Thread

    Note over MB,SC: 🔵 Main Thread
    Note over PT: 🟠 Person Tracker Thread 
    Note over VT: 🟡 Vehicle Tracker Thread
    
    rect rgb(100, 149, 237, 0.2)
        MB->>+SC: Person Detection
        SC->>SC: Process & Validate
        SC->>+PT: Enqueue Objects
        deactivate SC
    end
    
    rect rgb(255, 165, 0, 0.2)
        PT->>PT: Track Objects
        deactivate PT
    end
    
    rect rgb(100, 149, 237, 0.2)
        MB->>+SC: Vehicle Detection
        SC->>SC: Process & Validate
        SC->>+VT: Enqueue Objects
        deactivate SC
    end
    
    rect rgb(255, 215, 0, 0.2)
        VT->>VT: Track Objects
        deactivate VT
    end
    
    Note over MB,VT: Sequential processing
```

### Implementation Details

#### Message Processing Flow
1. **MQTT Message Reception**: [`SceneController.handleMovingObjectMessage()`](../controller/src/controller/scene_controller.py#L320)
   - Validates schema and processes timestamps
   - Calls [`processCameraData(jdata, when)`](../controller/src/controller/scene.py#L137) for camera detections

2. **Object Processing**: [`Scene._finishProcessing(detectionType, when, objects)`](../controller/src/controller/scene.py#L204)
   - Updates object visibility
   - Calls tracker for object tracking

3. **Tracker Orchestration**: [`Tracking.trackObjects()`](../controller/src/controller/tracking.py#L44)
   - Creates per-category threads via [`_createTrackers()`](../controller/src/controller/tracking.py#L83)
   - Enqueues objects: `self.trackers[category].queue.put((new_objects, when, already_tracked_objects))`

4. **Per-Category Threading**: Each category (person, vehicle, etc.) has:
   - **Own Queue**: `Queue()` instance for thread communication
   - **Own Thread**: Runs [`run()`](../controller/src/controller/tracking.py#L135) method continuously
   - **Independent Processing**: [`trackCategory(objects, when, already_tracked_objects)`](../controller/src/controller/ilabs_tracking.py#L166)

## Proposed Architecture: Time-Chunked Per-Category Processing (SceneScape v1.5)

```mermaid
sequenceDiagram
    participant MB as MQTT Broker
    participant SC as SceneController
    participant PT as Timer Thread
    participant PTh as Person Thread
    participant VTh as Vehicle Thread

    Note over MB,SC: 🔵 Main Thread
    Note over PT: � Timer Thread (with TimeChunkBuffer)
    Note over PTh: 🟠 Person Thread
    Note over VTh: 🔴 Vehicle Thread
    
    rect rgb(100, 149, 237, 0.2)
        MB->>+SC: Person Detection
        SC->>SC: Process & Validate
        SC->>+PT: Buffer Person Objects
        deactivate SC
    end
    
    rect rgb(255, 215, 0, 0.2)
        PT->>PT: Add to internal buffer
        deactivate PT
    end
    
    rect rgb(100, 149, 237, 0.2)
        MB->>+SC: Vehicle Detection
        SC->>SC: Process & Validate
        SC->>+PT: Buffer Vehicle Objects
        deactivate SC
    end
    
    rect rgb(255, 215, 0, 0.2)
        PT->>PT: Add to internal buffer
        deactivate PT
    end
    
    rect rgb(100, 149, 237, 0.2)
        MB->>+SC: Person Detection
        SC->>SC: Process & Validate
        SC->>+PT: Buffer Person Objects
        deactivate SC
    end
    
    rect rgb(255, 215, 0, 0.2)
        PT->>PT: Replace in internal buffer
        deactivate PT
        
        Note over PT: Timer fires (100ms)
        activate PT
        PT->>PT: Process internal buffer
        Note over PT: Prepare Synchronized Dispatch
    end
    
    par Synchronized Processing
        rect rgb(255, 165, 0, 0.2)
            PT->>+PTh: Dispatch Person Batch
            PTh->>PTh: Track Objects
            deactivate PTh
        end
    and
        rect rgb(220, 20, 60, 0.2)
            PT->>+VTh: Dispatch Vehicle Batch
            VTh->>VTh: Track Objects
            deactivate VTh
        end
    end
    
    rect rgb(255, 215, 0, 0.2)
        deactivate PT
    end
    
    Note over PT,VTh: Synchronized processing
```

### v1.5 Time-Chunking Flow Details

#### Modified Message Processing Flow
1. **MQTT Message Reception**: Same as v1.4 - [`handleMovingObjectMessage()`](../controller/src/controller/scene_controller.py#L320)
   - Same processing pipeline through [`processCameraData()`](../controller/src/controller/scene.py#L137)
   - Same object creation and validation

2. **Time-Chunk Buffering** (NEW): Instead of immediate tracker dispatch:
   ```python
   # Current v1.4: Direct dispatch
   self.trackers[category].queue.put((new_objects, when, already_tracked_objects))
   
   # Proposed v1.5: Buffered dispatch to timer thread  
   self.time_chunk_processor.buffer_message(category, new_objects, when, already_tracked_objects)
   ```

3. **Timer Thread with Internal Buffer** (NEW): [`TimeChunkProcessor.run()`] - To be implemented
   - Contains internal `TimeChunkBuffer` (similar to how tracker threads contain `Queue`)
   - Receives messages via `buffer_message()` method (thread-safe)
   - Timer fires every configurable interval (50-500ms) to process internal buffer
   - Dispatches to existing tracker queues simultaneously

4. **Synchronized Dispatch**: Maintains existing interface:
   - Same [`queue.put()`](../controller/src/controller/tracking.py#L62) calls to tracker threads
   - Same [`run()`](../controller/src/controller/tracking.py#L135) and [`trackCategory()`](../controller/src/controller/ilabs_tracking.py#L166) processing
   - **Key difference**: All categories receive data from the same time window

#### Implementation Components (To Be Added)
- **TimeChunkProcessor**: Timer thread class (similar to `Tracking` thread)
  - Contains internal `TimeChunkBuffer` (similar to how `Tracking` contains `Queue`)
  - Provides `buffer_message(category, objects, when, already_tracked)` method
  - Runs periodic timer to process buffered messages
- **TimeChunkBuffer**: Internal buffer class using `threading.RLock()` (encapsulated within processor)
- **Configuration**: Adjustable time window settings

## TimeChunkBuffer Class Design

```mermaid
classDiagram
    class TimeChunkBuffer {
        +add_message(category, objects, when, already_tracked)
        +pop_all_latest()
        +get_categories()
    }
    
    class TimeChunkProcessor {
        +buffer_message(category, objects, when, already_tracked)
        +run()
    }
    
    class Thread {
        <<abstract>>
    }
    
    TimeChunkProcessor --|> Thread : inherits
    TimeChunkProcessor *-- TimeChunkBuffer : contains
    
    note for TimeChunkBuffer "Thread-safe buffer</br>Stores latest per category</br>Atomic operations"
    
    note for TimeChunkProcessor "Timer thread</br>Periodic processing</br>Synchronized dispatch"
```

### Design Principles

#### **Thread Safety**
- All operations are thread-safe with proper locking
- Prevents race conditions between message buffering and processing

#### **Latest Message Strategy** 
- Keeps only the most recent message per category
- Reduces memory usage and processing overhead

#### **Atomic Batch Processing**
- All categories processed together for temporal consistency
- Either all categories dispatched simultaneously or none



