# How to Enable Observability for the Scene Controller and Tracker Service

> **⚠️ Experimental feature.** OpenTelemetry-based observability for the Scene
> Controller and Tracker Service is an **experimental** capability. Metric
> names, span names, attributes, configuration keys, and environment variables
> may change or be removed between releases without following the usual
> deprecation policy. The current implementation exports telemetry over
> **insecure OTLP/gRPC only** — do not enable it on untrusted networks or in
> production deployments that require TLS between the service and the
> collector. See ADR
> [`0002-controller-otel`](https://github.com/open-edge-platform/scenescape/blob/main/docs/adr/0002-controller-otel.md)
> and the design documents linked at the bottom of this page for background.

This guide explains how to enable and configure the experimental
[OpenTelemetry](https://opentelemetry.io/) instrumentation available in two
Scenescape microservices:

- **Scene Controller** (Python) — emits metrics and distributed traces for MQTT
  message processing, tracking updates, and the time-chunking scheduler.
- **Tracker Service** (C++, used when the Scene Controller runs in
  `--analytics-only` mode) — emits metrics and distributed traces for its
  end-to-end detection→track pipeline.

Both services push data to an OpenTelemetry Collector using OTLP/gRPC. From
the Collector you can forward metrics to Prometheus, traces to Tempo/Jaeger,
and logs to Loki (or any other OTLP-compatible backend).

By completing this guide, you will:

- Understand which telemetry signals are produced by each service.
- Enable metrics and tracing for the Scene Controller and Tracker Service.
- Configure the OTLP endpoint used by each service.
- Know where to look next if you need to change what is exported.

---

## Prerequisites

Before you begin, ensure the following:

- Scenescape is deployed and running (see the
  [Installation Guide](../get-started/installation.md)).
- You are able to edit the Compose file used by your deployment (for example
  `sample_data/compose/docker-compose-dl-streamer-example.yml`) and set environment
  variables for the affected containers.
- You have an OpenTelemetry Collector reachable from the service containers.
  A minimal collector configuration used by the tracker load tests is
  available at
  [`tracker/test/load/config/otel-collector.yaml`](https://github.com/open-edge-platform/scenescape/blob/main/tracker/test/load/config/otel-collector.yaml)
  and can be used as a starting point.

> **Note:** The collector endpoint must be reachable over **plaintext
> gRPC** — the current instrumentation does not support TLS to the
> collector. Place the collector on a trusted network (for example the
> same Docker Compose network as the services) and use the collector
> itself to forward telemetry to any TLS-secured backend.

---

## Enable Observability for the Scene Controller

The Scene Controller reads its observability configuration from environment
variables at startup. Metrics and tracing are **disabled by default**.

### Environment Variables

| Variable                               | Applies to | Default          | Description                                                                                                      |
| -------------------------------------- | ---------- | ---------------- | ---------------------------------------------------------------------------------------------------------------- |
| `CONTROLLER_ENABLE_METRICS`            | metrics    | `false`          | Set to `true` (or `1`/`yes`) to enable OpenTelemetry metrics export.                                             |
| `CONTROLLER_METRICS_ENDPOINT`          | metrics    | _(none)_         | OTLP/gRPC endpoint for metrics, e.g. `otel-collector:4317`. Required when `CONTROLLER_ENABLE_METRICS` is `true`. |
| `CONTROLLER_METRICS_EXPORT_INTERVAL_S` | metrics    | `60`             | Metrics export interval in seconds. Must be a positive integer.                                                  |
| `CONTROLLER_ENABLE_TRACING`            | tracing    | `false`          | Set to `true` to enable OpenTelemetry distributed tracing.                                                       |
| `CONTROLLER_TRACING_ENDPOINT`          | tracing    | `localhost:4317` | OTLP/gRPC endpoint for traces, e.g. `otel-collector:4317`.                                                       |
| `CONTROLLER_TRACING_SAMPLE_RATIO`      | tracing    | `1.0`            | Trace sampling ratio (`0.0`–`1.0`). Use e.g. `0.1` for 10 % or `0.01` for 1 % sampling.                          |

If `CONTROLLER_ENABLE_METRICS=true` is set but `CONTROLLER_METRICS_ENDPOINT`
is empty, the controller logs a warning and disables metrics. Invalid values
for `CONTROLLER_METRICS_EXPORT_INTERVAL_S` fall back to the default of
`60` seconds. An out-of-range `CONTROLLER_TRACING_SAMPLE_RATIO` causes
startup to fail with a `ValueError`.

### Enabling via Docker Compose

The provided Compose files already wire these variables through to the
`scene` service. For example, in
[`sample_data/compose/docker-compose-dl-streamer-example.yml`](https://github.com/open-edge-platform/scenescape/blob/main/sample_data/compose/docker-compose-dl-streamer-example.yml)
the controller declares:

```yaml
environment:
  CONTROLLER_ENABLE_METRICS: ${CONTROLLER_ENABLE_METRICS}
  CONTROLLER_METRICS_ENDPOINT: ${CONTROLLER_METRICS_ENDPOINT}
  CONTROLLER_METRICS_EXPORT_INTERVAL_S: ${CONTROLLER_METRICS_EXPORT_INTERVAL_S}
  CONTROLLER_ENABLE_TRACING: ${CONTROLLER_ENABLE_TRACING}
  CONTROLLER_TRACING_ENDPOINT: ${CONTROLLER_TRACING_ENDPOINT}
  CONTROLLER_TRACING_SAMPLE_RATIO: ${CONTROLLER_TRACING_SAMPLE_RATIO}
```

To turn observability on, export the variables in your shell (or set them
in a `.env` file next to the Compose file) before starting the stack:

```bash
export CONTROLLER_ENABLE_METRICS=true
export CONTROLLER_METRICS_ENDPOINT=otel-collector:4317
export CONTROLLER_METRICS_EXPORT_INTERVAL_S=15

export CONTROLLER_ENABLE_TRACING=true
export CONTROLLER_TRACING_ENDPOINT=otel-collector:4317
export CONTROLLER_TRACING_SAMPLE_RATIO=1.0

docker compose -f sample_data/compose/docker-compose-dl-streamer-example.yml up
```

Make sure your OpenTelemetry Collector container is on the same network as
the `scene` service so the hostname resolves.

### What the Scene Controller Exports

The Scene Controller emits the following OpenTelemetry instruments under the
`scene-controller` service name:

**MQTT / tracking metrics**

- `scenescape_controller_mqtt_messages` (counter) — MQTT messages received
  and processed.
- `scenescape_controller_mqtt_messages_dropped` (counter) — MQTT messages
  dropped.
- `scenescape_controller_mqtt_handler_duration` (histogram, ms) — MQTT
  handler processing time.
- `scenescape_controller_tracking_duration` (histogram, ms) — Tracking
  thread processing time.
- `scenescape_controller_objects_in_mqtt_message` (histogram) — Object
  count per MQTT message.

**Time-chunking counters** (emitted only when `time_chunking_enabled: true`
in the tracker configuration — see
[How to Configure the Tracker](../microservices/controller/how-to-configure-tracker.md)):

- `scenescape_controller_time_chunking_duplicated_cameras` — buffered
  camera frames overwritten before dispatch.
- `scenescape_controller_time_chunking_unique_cameras` — distinct cameras
  dispatched per non-empty chunk.
- `scenescape_controller_time_chunking_non_empty_chunks` — dispatch
  intervals that had buffered data.
- `scenescape_controller_time_chunking_empty_chunks` — dispatch intervals
  with no buffered data.

**Tracing.** Spans are created for MQTT message handling, object tracking
updates, coordinate transformations, and REST API requests. Trace context
follows the OpenTelemetry SDK defaults.

---

## Enable Observability for the Tracker Service

The Tracker Service is used when the Scene Controller runs in
[analytics-only mode](../microservices/controller/controller.md#configurable-arguments-and-flags).
Its observability settings live in the tracker service configuration file
(see [`tracker/config/tracker.json`](https://github.com/open-edge-platform/scenescape/blob/main/tracker/config/tracker.json))
and can also be overridden with environment variables.

### Configuration File

Metrics and tracing are configured under `infrastructure.otlp` and
`observability` in the tracker configuration:

```json
{
  "infrastructure": {
    "otlp": {
      "endpoint": "otel-collector:4317",
      "insecure": true
    }
  },
  "observability": {
    "logging": {
      "level": "info"
    },
    "metrics": {
      "enabled": true,
      "export_interval_s": 60
    },
    "tracing": {
      "enabled": true,
      "export_interval_s": 5
    }
  }
}
```

- `infrastructure.otlp.endpoint` — OTLP/gRPC endpoint shared by metrics and
  tracing (required when either signal is enabled).
- `infrastructure.otlp.insecure` — must be `true`; secure (TLS) OTLP is not
  yet supported by the tracker.
- `observability.metrics.enabled` / `observability.tracing.enabled` — turn
  each signal on independently (both default to `false`).
- `observability.metrics.export_interval_s` — metrics push interval
  (seconds, ≥ 1).
- `observability.tracing.export_interval_s` — batch span processor schedule
  delay (seconds, ≥ 1).
- `observability.logging.level` — one of `trace`, `debug`, `info`,
  `warning`, `error`.

### Environment Variable Overrides

Any of the settings above can be overridden without editing the
configuration file. The service uses these variables (defined in
[`tracker/inc/env_vars.hpp`](https://github.com/open-edge-platform/scenescape/blob/main/tracker/inc/env_vars.hpp)):

| Variable                            | Description                                         |
| ----------------------------------- | --------------------------------------------------- |
| `TRACKER_OTLP_ENDPOINT`             | OTLP/gRPC endpoint, e.g. `otel-collector:4317`.     |
| `TRACKER_METRICS_ENABLED`           | `true`/`false` — enable metrics export.             |
| `TRACKER_TRACING_ENABLED`           | `true`/`false` — enable distributed tracing.        |
| `TRACKER_METRICS_EXPORT_INTERVAL_S` | Metrics export interval (seconds, ≥ 1).             |
| `TRACKER_TRACING_EXPORT_INTERVAL_S` | Batch span processor schedule delay (seconds, ≥ 1). |

Example (adapted from the tracker load-test Compose file):

```yaml
services:
  tracker:
    image: intel/scenescape-tracker:${VERSION:-latest}
    environment:
      - TRACKER_METRICS_ENABLED=true
      - TRACKER_TRACING_ENABLED=true
      - TRACKER_OTLP_ENDPOINT=otel-collector:4317
      - TRACKER_METRICS_EXPORT_INTERVAL_S=15
      - TRACKER_TRACING_EXPORT_INTERVAL_S=5
```

For a working end-to-end setup with an OpenTelemetry Collector, tracker
service, and load generator, see
[`tracker/test/load/compose.yml`](https://github.com/open-edge-platform/scenescape/blob/main/tracker/test/load/compose.yml)
and the collector configuration in the same directory.

### What the Tracker Service Exports

The Tracker Service publishes OpenTelemetry data under the `tracker` meter
scope with the following instruments (see
[`tracker/inc/metrics.hpp`](https://github.com/open-edge-platform/scenescape/blob/main/tracker/inc/metrics.hpp)):

**Core metrics**

- `tracker.mqtt.latency` (histogram, ms) — end-to-end processing latency,
  attributed by `scene` and `category`.
- `tracker.mqtt.messages` (counter) — messages received, attributed by
  `scene`, `camera_id`, and `reason` (accepted / rejected).
- `tracker.mqtt.dropped` (counter) — messages dropped, attributed by
  `scene`, `camera_id`, and `reason`.
- `tracker.tracks.active` (gauge) — currently active tracks, attributed by
  `scene` and `category`.

**Per-stage latency histograms** (in milliseconds) for breaking down the
pipeline:

- `tracker.stage.parse_duration`
- `tracker.stage.buffer_duration`
- `tracker.stage.queue_duration`
- `tracker.stage.transform_duration`
- `tracker.stage.track_duration`
- `tracker.stage.publish_duration`

**Time-chunking counters**

- `tracker.time_chunking.duplicated_cameras`
- `tracker.time_chunking.unique_cameras`
- `tracker.time_chunking.non_empty_chunks`
- `tracker.time_chunking.empty_chunks`

**Tracing.** Spans are created for MQTT message handling
(`tracker.mqtt_handler`), tracking (`tracker.tracking`), publishing
(`tracker.publish`), and end-to-end detection processing
(`tracker.process`). Trace context is propagated using W3C Trace Context so
that traces can be correlated with upstream detection producers (for
example DL Streamer).

For attribute values, drop reasons, histogram buckets, and additional
detail, see the tracker service
[design document](https://github.com/open-edge-platform/scenescape/blob/main/docs/design/tracker-service.md#observability).

---

## Verify That Telemetry Is Flowing

After enabling either signal, restart the affected service and check:

1. **Service logs** — on startup the Scene Controller logs a message such
   as `Exporting OpenTelemetry metrics to <endpoint> every <N>s`. The
   Tracker Service logs the initialized providers when metrics or tracing
   are enabled.
2. **OpenTelemetry Collector logs** — with the `debug` exporter (or the
   `logging` exporter in older collector versions) enabled, you should see
   metric and span batches arriving from `scene-controller` and/or
   `tracker` service resources.
3. **Downstream backend** — verify the metrics appear in your chosen
   backend (for example a Prometheus target scraped from the collector's
   Prometheus exporter, or a Jaeger/Tempo search filtered by service
   name).

---

## Limitations and Known Caveats

- **Experimental API.** Metric names, span names, attribute keys,
  configuration keys, and environment variables can change between
  releases. Do not rely on this instrumentation for long-lived dashboards
  or alerts without pinning versions.
- **Insecure OTLP only.** The Scene Controller and Tracker Service export
  telemetry over plaintext gRPC. Deploy the collector on a trusted network
  and let it handle any TLS termination toward downstream backends.
- **No collector is bundled.** Scenescape does not ship an OpenTelemetry
  Collector. You are responsible for deploying and configuring one; the
  tracker load-test configuration is a good starting point.
- **Cost.** Both services record data on the hot path. Enable observability
  only when needed, and consider adjusting export intervals or the
  Scene Controller tracing sample ratio to reduce overhead.

---

## Supporting Resources

- ADR: [0002 Adopt OpenTelemetry in Controller Microservice](https://github.com/open-edge-platform/scenescape/blob/main/docs/adr/0002-controller-otel.md)
- Design: [Tracker Service — Observability](https://github.com/open-edge-platform/scenescape/blob/main/docs/design/tracker-service.md#observability)
- [Scene Controller Service](../microservices/controller/controller.md)
- [How to Configure the Tracker](../microservices/controller/how-to-configure-tracker.md)
- Tracker service source: [`tracker/`](https://github.com/open-edge-platform/scenescape/tree/main/tracker)
- Example collector configuration: [`tracker/test/load/config/otel-collector.yaml`](https://github.com/open-edge-platform/scenescape/blob/main/tracker/test/load/config/otel-collector.yaml)
