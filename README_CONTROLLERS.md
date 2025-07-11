# SceneScape Controller Implementations

This directory contains three implementations of the SceneScape controller service for performance and architecture comparison.

## Directory Structure

```
├── controller/          # Original Python implementation
├── controller-cpp/      # C++ implementation  
├── controller-go/       # Go implementation
└── CONTROLLER_COMPARISON.md  # Detailed comparison document
```

## Quick Start

### Python (Original)
```bash
cd controller/
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-runtime.txt
python src/controller-cmd --restauth user:password
```

### C++
```bash
cd controller-cpp/
mkdir build && cd build
cmake ..
make -j$(nproc)
./controller --restauth user:password
```

### Go
```bash
cd controller-go/
go mod tidy
go build -o controller ./cmd/controller
./controller --restauth user:password
```

## Key Features

All implementations provide:
- ✅ MQTT communication for real-time data
- ✅ REST API integration for configuration
- ✅ Object tracking and scene management
- ✅ Time synchronization and data validation
- ✅ Multi-camera and sensor support
- ✅ Region and tripwire event detection

## Robot Vision Library

The `robot_vision` library remains unchanged across all implementations:
- **Python**: Uses existing Python bindings
- **C++**: Native C++ library integration
- **Go**: CGO bindings to C++ library

## Performance Characteristics

| Metric | Python | C++ | Go |
|--------|--------|-----|-----|
| Memory Usage | High | Low | Medium |
| CPU Performance | Moderate | High | High |
| Concurrency | Limited (GIL) | Manual | Excellent |
| Development Speed | Fast | Slow | Medium |
| Deployment | Complex | Medium | Simple |

## Use Cases

### Python
- Rapid prototyping and development
- Research and experimentation
- Teams with Python expertise
- Non-performance-critical deployments

### C++
- High-performance production systems
- Real-time processing requirements
- Memory-constrained environments
- Maximum robot_vision integration

### Go
- Modern cloud-native deployments
- Concurrent processing workloads
- Teams preferring modern languages
- Balance of performance and productivity

## Next Steps

1. Review [CONTROLLER_COMPARISON.md](CONTROLLER_COMPARISON.md) for detailed analysis
2. Test each implementation with your specific workload
3. Benchmark performance with representative data
4. Consider team expertise and maintenance requirements
5. Choose implementation based on your priorities

## Contributing

When working on any implementation:
1. Maintain API compatibility across versions
2. Add comprehensive tests for new features  
3. Update documentation for changes
4. Ensure robot_vision integration remains consistent

## Support

For questions about specific implementations:
- **Python**: Check existing controller documentation
- **C++**: Review CMakeLists.txt and include headers
- **Go**: Check go.mod and internal package structure
