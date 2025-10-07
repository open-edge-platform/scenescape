# ADR 2: Adopt OpenTelemetry in Controller Microservice

- **Author**: [Józef Daniecki](https://github.com/jdanieck)
- **Date**: 2025-02-10
- **Status**: Proposed

## Context

The Controller microservice currently runs without built-in performance visibility. In v1.4.0 we rely on ad-hoc parsing of logs to extract a few coarse metrics (e.g., dropped messages), which is brittle and incomplete.

At scale, deployments will involve multiple cameras, higher frame rates, and more object detections per video stream — significantly increasing message throughput and processing load. To meet these demands, we require:

- End-to-end latency measurements for each MQTT message
- Throughput metrics (messages processed per second)
- Error and drop counts (e.g. messages dropped due tracker queue saturation)

Without structured metrics and distributed traces, diagnosing performance regressions or bottlenecks is slow, manual, and error-prone.

## Decision

We will adopt OpenTelemetry (OTEL) as our vendor-neutral observability framework, applying both metrics and distributed tracing to the Controller microservice. This choice provides:

- A single, consistent instrumentation standard across metrics and tracing
- Seamless integration with OTLP-based telemetry pipelines (Prometheus, Grafana, traces backend)

Exact metrics definitions, span structure and instrumentation patterns will be specified in a separate design document.

## Alternatives Considered

### No instrumentation

- Pros: zero additional dependencies, zero overhead
- Cons: no visibility into runtime performance or failures

### Python Prometheus client only (metrics)

- Pros: simple to adopt, familiar Prometheus ecosystem
- Cons: no distributed tracing, limited context for diagnosing multi-step flows

## Consequences

### Positive

- Detailed metrics enable SLO tracking and capacity planning.
- Distributed traces simplify identification of performance hotspots.
- OpenTelemetry standard ensures consistent instrumentation across services.
- Leverages existing Prometheus/Grafana tooling with minimal integration.
- Provides a foundation to extend the same OpenTelemetry pipeline to structured logging in future iterations.
- Provides a foundation to extend observability to other SceneScape services

### Negative

- Introduces OpenTelemetry SDK and exporter dependencies.
- CPU and memory overhead for recording metrics and spans.
- Operational overhead to maintain and scale an OTEL Collector and related infrastructure.

## References

- [What is OpenTelemetry?](https://opentelemetry.io/docs/what-is-opentelemetry/)
