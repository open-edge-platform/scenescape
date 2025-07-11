# SceneScape Controller - C++ Implementation

This is a C++ translation of the Python controller service. The robot_vision library remains unchanged and is used as-is.

## Architecture

The C++ implementation maintains the same architecture as the Python version:

- **SceneController**: Main orchestrator that manages MQTT connections and scene processing
- **Scene**: Scene management and object tracking
- **CacheManager**: Handles REST API caching and scene data management
- **DetectionsBuilder**: Builds detection data structures for publishing
- **MovingObject**: Represents tracked objects in the scene

## Dependencies

- **C++17 or later**
- **CMake 3.16+**
- **paho-mqtt-cpp**: MQTT client library
- **nlohmann/json**: JSON processing
- **OpenCV**: Computer vision functionality
- **cpprest**: REST client functionality
- **robot_vision**: Existing C++ library (unchanged)

## Building

```bash
mkdir build
cd build
cmake ..
make -j$(nproc)
```

## Running

```bash
./controller --broker broker.scenescape.intel.com:1883 \
             --restauth user:password \
             --resturl https://web.scenescape.intel.com/api/v1
```

## Key Differences from Python Version

1. **Type Safety**: Strong typing prevents runtime errors common in Python
2. **Performance**: Better memory management and computational efficiency
3. **Concurrency**: Native thread management for better performance
4. **Memory Management**: RAII ensures proper resource cleanup
