# Tracker Service

Real-time multi-object tracking microservice for SceneScape, using Kalman filtering to maintain persistent object tracks across camera detection frames.

## Features

- **Real-time Tracking**: Kalman filter-based tracking with multiple motion models
- **Scene Isolation**: Independent tracking per scene and object category (person, vehicle, etc.)
- **Time Chunking**: Optimized detection batching for reduced computational overhead
- **SSL/TLS Support**: Secure MQTT communication with mutual certificate authentication
- **Hot Reload**: Scene configuration updates without service restart (SIGHUP)
- **Observability**: OpenTelemetry metrics, distributed tracing, and structured logging

## Quick Start

### Using Docker Compose (Recommended)

```bash
# Start full stack (MQTT broker, OTEL collector, Jaeger, tracker)
make compose-up

# View logs
docker compose logs -f tracker

# Stop stack
make compose-down
```

The service will be available with:
- Tracker: Processing detections from MQTT
- Jaeger UI: http://localhost:16686 (distributed traces)
- Prometheus metrics: http://localhost:8889/metrics

### Local Development

```bash
# Install dependencies
make dependencies-release

# Build
make build-release

# Run (requires MQTT broker on localhost:1883)
make run-release
```

## Configuration

The service requires two configuration files:

1. **Service Config** (`config/config.json`) - MQTT, observability, time chunking
2. **Scene Config** (`config/scenes.json`) - Camera and scene definitions

### Minimal Service Config

```json
{
  "mqtt": {
    "server_address": "tcp://localhost:1883",
    "client_id": "tracker-service",
    "qos": 1,
    "ssl": {
      "enabled": false
    }
  },
  "metrics": {
    "enabled": true,
    "otlp_endpoint": "http://localhost:4318",
    "export_interval_seconds": 10,
    "service_name": "tracker-service"
  },
  "tracing": {
    "enabled": true,
    "otlp_endpoint": "http://localhost:4318",
    "service_name": "tracker-service"
  },
  "logging": {
    "level": "info"
  },
  "scenes": {
    "source": "file",
    "file_path": "config/scenes.json"
  },
  "time_chunking_fps": 15,
  "max_lag_seconds": 1.0
}
```

### Scene Configuration

```json
{
  "cameras": [
    {
      "id": "cam1",
      "name": "Front Door",
      "intrinsics": {
        "fx": 1920.0,
        "fy": 1920.0,
        "cx": 960.0,
        "cy": 540.0
      },
      "distortion": {
        "k1": -0.1,
        "k2": 0.02,
        "p1": 0.001,
        "p2": 0.001
      }
    }
  ],
  "scenes": [
    {
      "id": "lobby",
      "name": "Building Lobby",
      "camera_ids": ["cam1"]
    }
  ]
}
```

### Reloading Scene Configuration

Update `config/scenes.json` and send SIGHUP signal:

**Local Development:**
```bash
# Update config file
vim config/scenes.json

# Find process ID and send signal
kill -HUP $(pgrep tracker)
```

**Docker Compose:**
```bash
# Update config file on host
vim config/scenes.json

# Restart tracker container to pick up changes
docker compose restart tracker
```

**Note**: Configs are mounted as immutable Docker configs (not volumes), so the container must be restarted. SIGHUP reload is not supported in Docker Compose deployment.

The service will reload scene configuration without restart. Service configuration (MQTT, metrics) is NOT reloadable.

## SSL/TLS Configuration

### Enabling SSL

Set `ssl.enabled: true` in service config and provide certificate paths:

```json
{
  "mqtt": {
    "server_address": "ssl://localhost:8883",
    "ssl": {
      "enabled": true,
      "ca_cert_path": "/certs/ca.crt",
      "client_cert_path": "/certs/client.crt",
      "client_key_path": "/certs/client.key",
      "verify_server": true
    }
  }
}
```

### Generating Test Certificates

For development and testing:

```bash
# Generate self-signed certificates
make generate-certs

# Certificates created in certs/ directory
# - ca.crt, ca.key - Certificate Authority
# - server.crt, server.key - MQTT broker certificate
# - client.crt, client.key - Tracker client certificate

# Clean certificates
make clean-certs
```

### Common SSL Errors

| Error | Solution |
|-------|----------|
| "SSL CA certificate not found" | Verify `ca_cert_path` exists and is readable |
| "SSL handshake failed" | Check CA certificate matches broker's certificate chain |
| "Certificate verification failed" | Set `verify_server: false` for self-signed certs (dev only) |
| "Connection refused on port 8883" | Ensure MQTT broker has SSL listener configured |
| "Private key does not match certificate" | Regenerate certificates with `make clean-certs && make generate-certs` |

## Running the Service

### Command Line

```bash
./tracker --config config/config.json
```

Options:
- `-c, --config <path>` - Path to service configuration file (required)
- `-h, --help` - Show help message

### Docker

```bash
# Build image
docker build -t tracker-service .

# Run container
docker run -d \
  --name tracker \
  -v $(pwd)/config:/config:ro \
  -v $(pwd)/certs:/certs:ro \
  tracker-service \
  --config /config/config.json
```

## MQTT Topics

### Input (Subscribed)

- `scenescape/data/camera/{camera_id}` - Detection messages from vision pipeline

### Output (Published)

- `scenescape/data/scene/{scene_id}/{thing_type}` - Tracked object positions in world coordinates
  - Example: `scenescape/data/scene/lobby/person`

See [DESIGN.md](DESIGN.md) for detailed message format specifications.

## Observability

### Metrics (Prometheus)

```bash
# View metrics (when using Docker Compose)
curl http://localhost:8889/metrics

# Key metrics:
# - mqtt_messages_received_total - Total messages received
# - scenescape_tracker_mqtt_handler_duration - Processing time per camera
```

### Distributed Traces (Jaeger)

```bash
# Open Jaeger UI
make jaeger-ui

# Or navigate to: http://localhost:16686
```

Trace hierarchy:
- `process_camera_detection` (root) - Full message processing
  - `kalman_tracking` - Tracking update
  - `publish_tracks` - MQTT publish

### Logs

Structured JSON logs with configurable levels (`trace`, `debug`, `info`, `warning`, `error`):

```bash
# View logs
docker compose logs -f tracker

# Filter by level
docker compose logs tracker | grep ERROR
```

## Architecture

For detailed architecture documentation, see [DESIGN.md](DESIGN.md):
- Component hierarchy and data flow
- Threading model and concurrency
- Time chunking and detection batching
- Configuration reload mechanisms
- Lazy initialization patterns

## Related Documentation

- **[DESIGN.md](DESIGN.md)** - Architecture, threading model, design decisions
- **Architecture Decision**: `docs/adr/0007-tracker-service.md`
- **RobotVision Tracking API**: `controller/src/robot_vision/include/rv/tracking/`

## License

See LICENSE file in repository root.
