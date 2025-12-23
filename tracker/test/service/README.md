# Service Tests

Service-level tests for the Tracker microservice, validating it in isolation with mocked dependencies.

## Test Philosophy

This is a **service test suite** - not unit tests, not full integration tests.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Test Pyramid                             │
├─────────────────────────────────────────────────────────────────┤
│                      E2E Tests                                  │
│                   (full SceneScape)                             │
│                        ╱╲                                       │
│                       ╱  ╲                                      │
│                      ╱    ╲                                     │
│           ──────────╱──────╲──────────  ◀─── YOU ARE HERE       │
│                    ╱ Service ╲                                  │
│                   ╱   Tests   ╲                                 │
│                  ╱─────────────╲                                │
│                 ╱   Unit Tests  ╲                               │
│                ╱─────────────────╲                              │
└─────────────────────────────────────────────────────────────────┘
```

### What We Test

- **Tracker service** running in Docker container
- **Real MQTT broker** (Mosquitto) for message passing
- **Real OTEL collector** with Prometheus metrics endpoint
- **Simulated load** via K6 with MQTT extension

### What We Mock/Stub

- **Vision pipeline** - replaced by K6 generating synthetic detections
- **Manager API** - not connected (static scene config)
- **Downstream consumers** - no services subscribe to tracker output

### Assertion Philosophy

| Metric | Behavior | Rationale |
|--------|----------|-----------|
| Messages received | **FAIL** if any lost | Core functionality must work |
| Dropped messages | **WARN** only | Expected under heavy load; indicates backpressure |
| Active tracks | **FAIL** if zero | Tracker must produce output |
| Latency p95 | **FAIL** if > budget | Performance regression detection |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Docker Compose Stack                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────┐    MQTT     ┌─────────┐   OTLP    ┌──────────┐   │
│  │   K6    │ ──────────▶ │ Tracker │ ────────▶ │   OTEL   │   │
│  │ (load)  │  detections │         │  metrics  │ Collector│   │
│  └─────────┘             └─────────┘           └────┬─────┘   │
│                               │                     │          │
│                               │                     ▼          │
│                               │              ┌──────────┐      │
│                               │              │Prometheus│      │
│                               │              │ endpoint │      │
│                               │              │ :8889    │      │
│                               │              └──────────┘      │
│                               ▼                     ▲          │
│                          ┌─────────┐               │          │
│                          │  MQTT   │               │          │
│                          │ Broker  │               │          │
│                          │ :1883   │          ┌────┴────┐     │
│                          └─────────┘          │ pytest  │     │
│                                               │ asserts │     │
│                                               └─────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

## Usage

### CI Mode (Default)

```bash
# Small load, fast feedback
make load-test
```

Default configuration:
- 4 cameras
- 15 FPS per camera
- 30 second duration
- ~1,800 messages total

### Benchmark Mode

```bash
# Large load for performance validation
CAMERA_COUNT=16 CAMERA_FPS=30 TEST_DURATION=5m make load-test
```

### Individual Tests

```bash
# Run specific test
pytest test/service/test_tracker_service.py::TestTrackerService::test_mqtt_handler_latency -v

# Run with warnings shown
pytest test/service/test_tracker_service.py -v -W default::UserWarning
```

## Configuration

All configuration via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `MQTT_HOST` | `tcp://localhost` | MQTT broker host |
| `CAMERA_COUNT` | `4` | Number of simulated cameras |
| `CAMERA_FPS` | `15` | Messages per second per camera |
| `OBJECT_COUNT` | `10` | Persons per detection message |
| `TEST_DURATION` | `30s` | Load test duration |
| `PROCESSING_BUDGET_MS` | `100` | Max acceptable p95 latency |
| `METRICS_ENDPOINT` | `http://localhost:8889/metrics` | Prometheus endpoint |
| `METRICS_EXPORT_INTERVAL` | `10` | OTEL export interval (seconds) |
| `METRICS_TIMEOUT_BUFFER` | `20` | Additional wait time for metrics |

## Test Cases

| Test | Asserts | On Failure |
|------|---------|------------|
| `test_message_count` | All sent messages received | FAIL |
| `test_dropped_messages` | No messages dropped | WARN |
| `test_active_tracks` | Reliable tracks > 0 | FAIL |
| `test_mqtt_handler_latency` | p95 < budget | FAIL |
| `test_tracking_latency` | p95 < budget | FAIL |
| `test_zz_summary` | Print summary | Always passes |

## Troubleshooting

### Metrics endpoint not responding

```bash
# Check OTEL collector is running
docker compose ps otel-collector

# Check collector logs
docker compose logs otel-collector

# Manually check endpoint
curl -s http://localhost:8889/metrics | head -20
```

### K6 not sending messages

```bash
# Check MQTT broker
docker compose logs mqtt-broker

# Verify K6 can connect
docker run --rm --network host grafana/k6 version
```

### Dropped messages warning

This is expected under heavy load. The tracker uses time chunking to batch detections.
When load exceeds processing capacity, older detections are dropped.

To investigate:
```bash
# Increase logging
docker compose exec tracker env LOG_LEVEL=debug

# Check processing latency
curl -s http://localhost:8889/metrics | grep duration_milliseconds
```

### Test fails intermittently

1. **Increase timeout buffer**: `METRICS_TIMEOUT_BUFFER=30`
2. **Reduce load**: Lower `CAMERA_COUNT` or `CAMERA_FPS`
3. **Check system resources**: Docker may need more memory/CPU

## File Structure

```
test/service/
├── README.md           # This file
├── __init__.py         # Package exports
├── compose.yml         # Isolated Docker Compose stack
├── config.py           # Test configuration fixture
├── infrastructure.py   # Docker Compose management
├── metrics.py          # Prometheus metrics client
├── k6_runner.py        # K6 load test runner
├── reporting.py        # Rich console output
└── test_tracker_service.py  # Test cases
```

## Adding New Tests

1. Add test method to `TestTrackerService` in `test_tracker_service.py`
2. Access metrics via `load_test_results` fixture
3. Use `warnings.warn()` for non-critical assertions
4. Use `assert` for critical functionality
