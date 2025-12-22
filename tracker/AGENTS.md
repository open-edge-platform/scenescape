# AGENTS.md

Think of AGENTS.md as a README for agents: a dedicated, predictable place to provide the context and instructions to help AI coding agents work on your project.

# Tracker Service 

A C++ microservice for real-time object tracking in SceneScape, using Kalman filtering to track objects detected by vision pipelines.

**See [DESIGN.md](DESIGN.md) for architecture, threading model, and design decisions.**

## Quick Start

```bash
# Install dependencies and build (release)
make dependencies-release && make build-release

# Run locally (requires MQTT broker)
make run

# OR use full Docker Compose stack
make compose-up
```

## Build System

**CMake 3.28+ with Conan dependency management**

```bash
# Build variants
make build-release  # Optimized release build (default for deployment)
make build-debug    # Debug build with symbols (for debugging)
make build-profile  # Release with debug symbols (for profiling/flame graphs)

# Clean build artifacts
make clean  # Removes all build directories (Conan cache persists)
```

**Build Flow Details:**
- Conan outputs to `build-release/`, `build-debug/`, or `build-profile/` directory
- CMake uses Conan-provided toolchain: `<build-dir>/conan_toolchain.cmake`
- Compile commands exported to `<build-dir>/compile_commands.json` for IDE support
- C++20 standard (required, no fallback)
- Libraries installed to `~/.conan2/p/` cache

**Profiling and Performance Analysis:**
```bash
# Install prerequisites (one-time setup)
# Option 1: Install from packages (if available for your kernel)
sudo apt-get install linux-tools-generic linux-tools-$(uname -r)

# Option 2: Build perf from kernel source (if package not available)
make install-perf  # Builds and installs to ~/bin/perf

# Clone FlameGraph tools
git clone https://github.com/brendangregg/FlameGraph.git

# Build with profiling symbols
make build-profile

# Run with perf and generate flame graph (requires sudo)
make run-profile

# Manual profiling workflow:
perf record -F 99 -g ./build-profile/tracker  # Run and profile
perf script | FlameGraph/stackcollapse-perf.pl | FlameGraph/flamegraph.pl > flame.svg
```

**Profile Build Flags:**
- Build type: `RelWithDebInfo` (optimized with debug symbols)
- Additional flags: `-fno-omit-frame-pointer` (enables accurate stack traces)
- Output: `build-profile/tracker` with full symbol information
- Prerequisites: `linux-tools-generic`, `FlameGraph` scripts

## Dependencies

**Runtime Dependencies (from conanfile.txt [requires]):**
- `paho-mqtt-cpp/1.5.3` - MQTT client for pub/sub messaging
- `simdjson/4.2.2` - Fast JSON parser for detection messages
- `rapidjson/cci.20230929` - Fast JSON serialization
- `eigen/3.4.0` - Linear algebra (used by robot_vision)
- `opencv/4.12.0` - Computer vision (tracking/video/calib3d modules only)
- `opentelemetry-cpp/1.17.0` - Metrics, tracing and observability (OTLP HTTP)
- `quill/10.2.0` - High-performance structured logging

**Build Tools (from conanfile.txt [tool_requires]):**
- CMake 3.28+ is system-provided (not managed by Conan)
- Add `cmake/3.28+` to [tool_requires] if system CMake version is insufficient

**External Dependency:**
- `RobotVision` library from `../controller/src/robot_vision` (built as CMake subdirectory)
  - Provides `rv::tracking::TrackTracker` - Kalman filter-based tracking
  - Provides `rv::tracking::TrackedObject` - Object state representation
  - Provides `rv::computePixelsToMeterPlane` - Coordinate transformation

**Adding New Dependencies:**
1. Add runtime library to `conanfile.txt` under `[requires]` or build tool under `[tool_requires]`
2. Set options if needed under `[options]`
3. Run `make dependencies-release` (or `make dependencies-debug` for debug builds)
4. Add `find_package()` in `CMakeLists.txt` (for runtime deps only)
5. Link with `target_link_libraries(tracker PRIVATE <package>::<target>)` (for runtime deps only)

## Code Style

**Enforced via .clang-format (LLVM base):**
- **Standard**: C++20
- **Indentation**: 4 spaces (never tabs)
- **Column limit**: 100 characters
- **Braces**: K&R style (opening brace on same line)
- **Pointers**: Left-aligned (`Type* ptr` not `Type *ptr`)
- **Includes**: Case-insensitive sorting

**Format Commands:**
```bash
make format       # Auto-format all source files
make format-check # CI check - fails if formatting needed
```

**Naming Conventions (observed patterns):**
- Classes: `PascalCase` (MqttClient, MessageHandler)
- Functions/methods: `camelCase` (connectBroker, parseMessage)
- Private members: Trailing underscore (pImpl_, enabled_, client_)
- Namespaces: lowercase (logger, simdjson::dom)

## Testing

**End-to-End Test:**
```bash
make e2e-test
```
- Starts Docker Compose stack (MQTT broker, OTEL collector, tracker)
- Publishes 4 test detection messages from `test/data/`
- Subscribes to tracker output topic
- Validates 4 messages received within timeout
- Saves output to `/tmp/tracker_e2e_TIMESTAMP.txt`
- Shows container logs on failure

**Load Test with Metrics Validation:**
```bash
# Requires k6 installed: https://k6.io/docs/get-started/installation/
make load-test

# Configure test parameters with env vars:
export MQTT_HOST=tcp://localhost
export CAMERA_COUNT=4        # Number of simulated cameras
export CAMERA_FPS=15         # Messages per second per camera
export OBJECT_COUNT=10       # Persons per detection message
export TEST_DURATION=30s     # Test duration
make load-test
```
- Uses pytest to orchestrate k6 load generation
- k6 script (`generate-detections.js`) simulates realistic movement patterns
- Validates OpenTelemetry metrics via Prometheus endpoint
- Checks `mqtt_messages_received_total` counter
- Verifies `scenescape_tracker_mqtt_handler_duration` histogram

**Manual MQTT Testing:**
```bash
# Publish single test message
make mqtt-publish

# Subscribe to tracker output
make mqtt-subscribe
```

**Test Message Format:**
Detection messages in `test/data/detection-message-*.json`:
```json
{
  "id": "camera_id",
  "timestamp": "2025-10-08T13:21:40.482Z",
  "rate": 9.78,
  "objects": {
    "person": [{
      "category": "person",
      "confidence": 0.989,
      "center_of_mass": {"x": 45, "y": 77, "width": 42.67, "height": 77.25},
      "bounding_box_px": {"x": 4, "y": 0, "width": 127, "height": 309},
      "id": 1
    }]
  }
}
```

## Configuration

**Config path**: Required via `--config` CLI flag (no default)  
**Usage**: `./tracker --config config/config.json`

**Configuration Overview:**
- **Service config** (`config/config.json`): MQTT, SSL, metrics, tracing, logging, time chunking params - **NOT reloadable**
- **Scene config** (`config/scenes.json`): Cameras and scenes - **Reloadable via SIGHUP**
  - Validated against `config/scenes.schema.json` (JSON Schema)
  - When `scenes.source: "api"`, Manager API response is transformed and written to file in the same schema before load

**See [DESIGN.md](DESIGN.md#configuration) for full config structure, reload mechanisms, and API integration details.**

### SSL/TLS Configuration

The tracker service supports secure MQTT connections using TLS/SSL with mutual certificate authentication (mTLS).

**SSL Configuration Block:**
- `enabled` (bool): Enable/disable SSL (default: `false`)
- `ca_cert_path` (string): Path to CA certificate for server verification (PEM format)
- `client_cert_path` (string): Path to client certificate for client authentication (PEM format)
- `client_key_path` (string): Path to client private key (PEM format)
- `verify_server` (bool): Verify server certificate against CA (default: `true`)

**Certificate Requirements:**
- All certificates must be in PEM format
- Files must be readable by the tracker process (file permissions)
- For Docker deployments, certificates are mounted as Docker secrets (no bind mounts)
- CA certificate must be the trust store root for the MQTT broker
- Client certificate/key pair must be signed by the CA

**Connection Behavior:**
- When `ssl.enabled: true`, server address uses `ssl://` scheme (port typically 8883)
- When `ssl.enabled: false`, server address uses `tcp://` scheme (port typically 1883)
- Certificate paths are validated at startup - service exits if files are missing
- SSL handshake failures are logged with paho-mqtt-cpp error details

**Generating Test Certificates:**
For local development and testing, use the automated certificate generation:

```bash
# Generate self-signed certificates for testing
make generate-certs

# Certificates are auto-generated during compose-up if missing
make compose-up

# Clean generated certificates
make clean-certs
```

This creates:
- `certs/ca.crt` and `certs/ca.key` - Certificate Authority
- `certs/server.crt` and `certs/server.key` - Mosquitto broker certificate
- `certs/client.crt` and `certs/client.key` - Tracker client certificate

**Docker Deployment:**
Certificates are mounted as Docker secrets (read-only, no bind mounts):

```yaml
# compose.yml
secrets:
  mqtt_ca_cert:
    file: ./certs/ca.crt
  mqtt_client_cert:
    file: ./certs/client.crt
  mqtt_client_key:
    file: ./certs/client.key

services:
  tracker:
    secrets:
      - source: mqtt_ca_cert
        target: /certs/ca.crt
      - source: mqtt_client_cert
        target: /certs/client.crt
      - source: mqtt_client_key
        target: /certs/client.key
```

**Common SSL Errors and Troubleshooting:**
1. **"SSL CA certificate not found"**: Check `ca_cert_path` exists and is readable
2. **"SSL handshake failed"**: Verify CA certificate matches broker's certificate chain
3. **"Certificate verification failed"**: Set `verify_server: false` for self-signed certs (dev only)
4. **"Connection refused on port 8883"**: Ensure MQTT broker has SSL listener configured
5. **"Private key does not match certificate"**: Regenerate client cert/key pair with `make clean-certs && make generate-certs`
6. **"Unable to get local issuer certificate"**: CA certificate incomplete or wrong trust store
7. **"Bind source path does not exist"**: Run `make generate-certs` to create certificates

**Disabling SSL (for development):**
Set `ssl.enabled: false` in config.json and use port `1883` with `tcp://` scheme.

**Modifying Config Schema:**
1. Update structs in `inc/config.h` or `inc/scene_config.h`
2. Update parsing logic in `src/config.cpp` or `src/scene_config.cpp` (simdjson API)
  - Scene config files are schema-validated via RapidJSON against `config/scenes.schema.json`
  - API-based scene fetch transforms Manager API payload to unified file schema
3. Update stream operators (`operator<<`) for logging
4. Update example config files in `config/`
5. Document changes in [DESIGN.md](DESIGN.md) and code comments

## Docker Development

**Docker Compose Stack:**
```bash
# Build Docker image
make compose-build

# Start services (MQTT, OTEL collector, tracker)
make compose-up

# Stop and remove
make compose-down

# View logs
docker compose logs -f tracker
docker compose logs -f otel-collector
```

**Services in compose.yml:**
1. **jaeger** - Jaeger all-in-one (ports 16686 UI, 4317/4318 OTLP)
2. **otel-collector** - Metrics and traces collection (ports 4318 OTLP, 8889 Prometheus)
3. **mqtt-broker** - Eclipse Mosquitto (ports 1883, 9001)
4. **tracker** - Main service (depends on above three)

**Dockerfile Details (multi-stage):**
- **Build stage**: Debian-based, installs deps, runs Conan, compiles
- **Runtime stage**: Distroless (no shell!), minimal image, non-root user
- Libraries copied from Conan cache to `/scenescape/lib`
- OpenCV libs renamed: `.so.4.12.0` → `.so.412` for linker compatibility

## Architecture & Design

**See [DESIGN.md](DESIGN.md) for comprehensive details on:**
- Component hierarchy and data flow
- Threading model (MQTT callback, timer threads per scene+category)
- Time chunking and detection batching
- Locking strategy and lock-free fast path
- Lazy initialization of trackers and processors
- Configuration reload mechanisms (SIGHUP, API integration)

**Key Points for Development:**
- Trackers created on-demand per scene+category combination
- Time chunking always enabled (batches detections at configurable FPS)
- Scene config reloadable via SIGHUP (atomic handler swap)
- RobotVision library provides Kalman filter tracking (`rv::tracking::TrackTracker`)

## Observability

**Logging (Quill):**
- High-performance async logging with structured output
- Log levels: `trace`, `debug`, `info`, `warning`, `error`
- Set via config: `logging.level`
- Pattern: `%(time) [%(thread_id)] %(file_name):%(line_number) %(log_level) %(message)`
- Access logger: `logger::get_logger()`
- Example: `LOG_INFO(logger::get_logger(), "Message: {}", value);`

**Metrics (OpenTelemetry):**
- Counter: `mqtt_messages_received_total` - Total MQTT messages received
- Histogram: `scenescape_tracker_mqtt_handler_duration` - Processing time (ms) by camera
- Export: OTLP HTTP to collector endpoint
- Interval: Configurable (default 10s)
- View metrics: `curl http://localhost:8889/metrics` (when using Docker Compose)

**Tracing (OpenTelemetry):**
- Distributed tracing with Jaeger backend
- Export: OTLP HTTP to collector → Jaeger
- Jaeger UI: `http://localhost:16686` or `make jaeger-ui`
- Service name: `tracker-service` (configurable)

**Trace Span Hierarchy:**
```
process_camera_detection (root span)
├── attributes: camera.id, message.timestamp, objects.count, processing.duration_ms
├── kalman_tracking (child span)
│   └── attributes: detections.count, tracks.count
└── publish_tracks (child span)
    └── attributes: mqtt.topic, tracks.count
```

**Span Attributes:**
- `camera.id` - Camera identifier from detection message
- `message.timestamp` - Detection message timestamp
- `objects.count` - Number of detected objects in message
- `detections.count` - Number of detections sent to tracker
- `tracks.count` - Number of reliable tracks returned/published
- `mqtt.topic` - MQTT topic for published tracks
- `processing.duration_ms` - Total processing time in milliseconds

**Adding New Metrics:**
1. Declare instrument in `inc/metrics_manager.h`
2. Create in `MetricsManager::initializeMetrics()`
3. Add public method to record value (e.g., `recordMyMetric()`)
4. Call from appropriate location in code
5. Verify at Prometheus endpoint during testing

**Adding New Trace Spans:**
1. Get tracer from `TraceManager::getInstance().getTracer()`
2. Create span: `auto span = tracer->StartSpan("span_name", options);`
3. Set parent context if creating child span:
   ```cpp
   opentelemetry::trace::StartSpanOptions options;
   options.parent = parent_span->GetContext();
   ```
**Debugging Tips:**
- Use `LOG_TRACE_L1` for verbose debugging (set `logging.level: "trace"`)
- Monitor MQTT traffic: `docker exec mqtt-broker mosquitto_sub -h localhost -t '#' -v`
- Check metrics: `curl http://localhost:8889/metrics | grep tracker`
- View traces: `make jaeger-ui` or open `http://localhost:16686`
- View OTEL logs: `docker compose logs otel-collector`
- View Jaeger logs: `docker compose logs jaeger`
- E2E test output saved to `/tmp/tracker_e2e_*.txt`

**Adding a New Source File:**
1. Create `inc/my_module.h` (interface) and `src/my_module.cpp` (implementation)
2. Add `.cpp` to `add_executable()` source list in `CMakeLists.txt`
3. Include header where needed
4. Rebuild: `make build-release` (or `make build-debug` for debug)

**Local Development (without Docker):**
```bash
# Requires local MQTT broker on localhost:1883
make run

# LD_LIBRARY_PATH automatically set from Conan cache
# --config flag passed in Makefile run target
```

## Important Gotchas

1. **Proxy Settings**: `main.cpp` disables all HTTP/HTTPS proxy env vars (Paho MQTT library issue)
2. **Library Paths**: Local run requires `LD_LIBRARY_PATH` from Conan cache (Makefile handles this)
3. **Distroless Container**: Runtime image has no shell - cannot `docker exec` into it for debugging
4. **Config Path**: Required via `--config` CLI flag, no default (fail early if not provided)
5. **Camera Calibration**: Currently uses dummy intrinsics/distortion - TODO to provide actual values
6. **Object ID Dependency**: Tracker relies on detection IDs from vision pipeline for association
7. **OpenCV Library Naming**: Dockerfile renames `.so.4.12.0` to `.so.412` for linker compatibility
8. **Conan Cache**: `make clean` removes `build/` but Conan cache in `~/.conan2/` persists

## Related Documentation

- **[DESIGN.md](DESIGN.md)** - Architecture, threading model, design decisions
- **Architecture Decision**: `docs/adr/0007-tracker-service.md`
- **RobotVision Tracking API**: `controller/src/robot_vision/include/rv/tracking/`
- **Pull Request**: https://github.com/open-edge-platform/scenescape/pull/614
