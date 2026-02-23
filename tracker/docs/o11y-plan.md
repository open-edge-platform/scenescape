# Tracker Observability Implementation Plan

**Branch**: `tracker-service-v0.5.0`
**PR**: https://github.com/open-edge-platform/scenescape/pull/1060
**Design doc**: `docs/design/tracker-service.md` §Observability

Each phase is a separate commit (or small PR). Phases build on each other sequentially.

---

## Phase 1 — OTel SDK Foundation ✅ DONE

**Commit**: `78b66ec2` + follow-ups (`48893229`, `edff5f84`, `f98ae07e`)

Bootstraps OTel SDK lifecycle so later phases can just call the API.

| Item                                                   | File(s)                                                       |
| ------------------------------------------------------ | ------------------------------------------------------------- |
| Add `opentelemetry-cpp/1.18.0` to Conan + CMake        | `conanfile.txt`, `CMakeLists.txt`, `test/unit/CMakeLists.txt` |
| `Telemetry` class (init/shutdown)                      | `inc/telemetry.hpp`, `src/telemetry.cpp`                      |
| `OtlpConfig`, `MetricsConfig`, `TracingConfig` structs | `inc/config_loader.hpp`                                       |
| JSON config parsing + env var overrides                | `src/config_loader.cpp`, `inc/env_vars.hpp`                   |
| Wire into `main.cpp`                                   | `src/main.cpp`                                                |
| 9 unit tests                                           | `test/unit/telemetry_test.cpp`                                |

**Env vars**: `TRACKER_OTLP_ENDPOINT`, `TRACKER_METRICS_ENABLED`, `TRACKER_TRACING_ENABLED`, `TRACKER_METRICS_EXPORT_INTERVAL_S`, `TRACKER_TRACING_EXPORT_INTERVAL_S`

**Key decisions**:

- `std::atomic<bool>` for thread-safe state queries
- `Telemetry::init()` throws on double-init (fail-fast)
- Default no-op providers when disabled (zero-cost API calls)
- Export intervals configurable for both metrics (default 60s) and tracing (default 5s, per OTel BSP spec)

---

## Phase 2 — Metrics Instrumentation

Add the 4 core instruments from the design doc. No new dependencies.

| Instrument              | Type                  | Unit      | Location                                                    |
| ----------------------- | --------------------- | --------- | ----------------------------------------------------------- |
| `tracker.mqtt.latency`  | Histogram             | ms        | `message_handler.cpp` (receive → dispatch)                  |
| `tracker.mqtt.messages` | Counter               | {message} | `message_handler.cpp` (per topic/status)                    |
| `tracker.mqtt.dropped`  | Counter               | {message} | `message_handler.cpp` (validation failures, unknown topics) |
| `tracker.tracks.active` | UpDownCounter (gauge) | {track}   | `tracking_worker.cpp` (after each cycle)                    |

**Files to create/modify**:

- `inc/metrics.hpp` / `src/metrics.cpp` — singleton instrument registry (lazy meter+instrument creation)
- `src/message_handler.cpp` — record latency, increment counters
- `src/tracking_worker.cpp` — observe active track count
- `test/unit/metrics_test.cpp` — verify instruments created, no-op when disabled

**Attributes** (labels):

- `scene`, `category` (tracking scope)
- `camera_id`, `topic` (MQTT context)
- `status`: `accepted` | `rejected_schema` | `rejected_unknown_topic`

---

## Phase 3 — Load Testing

Port k6/OTel collector load test infrastructure from `~/repos/tracker-service-poc/test/service/`.

**Source reference** (POC):

- `generate-detections.js` — k6 MQTT load generator
- `compose.yml` — 4-service stack (tracker, mosquitto, otel-collector, prometheus)
- `config/otel-collector.yaml` — OTel collector pipeline config
- `infrastructure.py` — Docker Compose lifecycle management
- `k6_runner.py` — k6 subprocess orchestration
- `metrics.py` — Prometheus metrics scraping + assertion
- `test_load.py` — pytest-based load test scenarios
- `config.py`, `conftest.py` — test configuration

**Target location**: `tracker/test/load/`

**Adaptation needed**:

- Update compose.yml to match current tracker image/config structure
- Adjust k6 script topic patterns to match tracker's MQTT topic schema
- Update Prometheus queries for the Phase 2 metric names
- Add Makefile target: `make load-test`

---

## Phase 4 — Distributed Tracing

Add spans to the request processing pipeline. Propagate W3C `traceparent` via MQTT v5 user properties.

**Spans** (from design doc):
| Span | Kind | Location |
|------|------|----------|
| `mqtt.message.receive` | CONSUMER | `message_handler.cpp` — wraps full message handling |
| `tracker.detection.validate` | INTERNAL | `message_handler.cpp` — schema validation |
| `tracker.detection.dispatch` | INTERNAL | `message_handler.cpp` → `time_chunk_buffer.cpp` |
| `tracker.tracking.cycle` | INTERNAL | `tracking_worker.cpp` — one time-chunk processing cycle |

**Files to create/modify**:

- `inc/observability_context.hpp` — `ObservabilityContext` struct (trace_id, span_id, from design doc)
- Modify MQTT interface to extract/propagate `traceparent` header from MQTT v5 user properties
- `src/message_handler.cpp` — start/end spans, set attributes, propagate context
- `src/tracking_worker.cpp` — tracking cycle span
- `test/unit/tracing_test.cpp` — verify spans created with correct names/attributes

**Key**: `ObservabilityContext` carries trace/span IDs through the pipeline without coupling business logic to OTel API.

---

## Phase 5 — Trace-Log Correlation & Exemplars

Wire trace context into structured logs and add histogram exemplars.

**Trace-log correlation**:

- Logger already has `TraceContext` struct (`logger.hpp` L63-67) with `trace_id`/`span_id` fields
- Wire `ObservabilityContext` → `TraceContext` so every log line in an active span includes `trace_id` and `span_id`
- Enables log → trace navigation in Grafana/Jaeger

**Histogram exemplars**:

- Attach `trace_id` as exemplar to `tracker.mqtt.latency` histogram recordings
- Enables metric → trace drill-down (click a latency spike → jump to the trace)

**Files to modify**:

- `src/message_handler.cpp` — populate `TraceContext` from active span, pass to logger
- `src/metrics.cpp` — add exemplar context to histogram record calls
- `test/unit/correlation_test.cpp` — verify trace IDs appear in log output

---

## Reference: Controller O11y Pattern (Python)

The Python controller's observability is in `controller/src/controller/observability/metrics.py` and serves as the reference pattern:

- Environment variables: `CONTROLLER_ENABLE_METRICS`, `CONTROLLER_ENABLE_TRACING`
- Context manager: `metrics.time_mqtt_handler(attributes)` for latency tracking
- Same OTLP gRPC export pattern
