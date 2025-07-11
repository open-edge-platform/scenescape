# SceneScape Controller - Go Implementation

This is a Go translation of the Python controller service. The robot_vision library remains unchanged and is used as-is through CGO bindings.

## Architecture

The Go implementation maintains the same architecture as the Python version:

- **SceneController**: Main orchestrator that manages MQTT connections and scene processing
- **Scene**: Scene management and object tracking
- **CacheManager**: Handles REST API caching and scene data management
- **DetectionsBuilder**: Builds detection data structures for publishing
- **MovingObject**: Represents tracked objects in the scene

## Dependencies

- **Go 1.19+**
- **Paho MQTT Go client**: MQTT communication
- **Gorilla WebSocket**: WebSocket support for MQTT
- **Go-resty**: HTTP REST client
- **robot_vision**: Existing C++ library (accessed via CGO)

## Building

```bash
go mod tidy
go build -o controller ./cmd/controller
```

## Running

```bash
./controller --broker broker.scenescape.intel.com:1883 \
             --restauth user:password \
             --resturl https://web.scenescape.intel.com/api/v1
```

## Key Differences from Python Version

1. **Concurrency**: Native goroutines for better concurrent processing
2. **Type Safety**: Compile-time type checking prevents runtime errors
3. **Performance**: Better memory efficiency and garbage collection
4. **Error Handling**: Explicit error handling throughout the codebase
5. **Channels**: Efficient inter-goroutine communication

## CGO Integration

The robot_vision library is accessed through CGO bindings, allowing seamless integration with the existing C++ tracking algorithms while maintaining Go's advantages for the rest of the system.
