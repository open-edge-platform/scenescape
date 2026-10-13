# Viewing Re-identification Match Latency Metrics

The controller exports metrics over **OTLP/gRPC** — a push protocol, not an
HTTP endpoint you can curl or scrape. You need something on the receiving
end that implements the OTel `MetricsService` to see them.

## Prerequisites

- Network reachability between the controller container and wherever your
  receiver runs
- `CONTROLLER_ENABLE_METRICS=true` and `CONTROLLER_METRICS_ENDPOINT` set
  (typically in your `.env` file, picked up by `docker-compose.yml`'s
  `x-controller-base` anchor)

## Recommended: run the real OTel Collector

For anything beyond a one-off "is this metric being emitted at all" check,
run an actual OpenTelemetry Collector feeding Prometheus + Grafana (or your
OTLP-compatible backend of choice) — see `otel-collector-config.yaml` for a
minimal starting config. Point `CONTROLLER_METRICS_ENDPOINT` at the
Collector's OTLP/gRPC receiver, then query/dashboard from Prometheus as
normal.

This is the only path that gives you real percentile queries (see
[Computing P95/P99](#computing-p95p99) below) — a print-and-discard receiver
cannot compute those, only a backend with the histogram's bucket data over a
time range can.

## Quick ad-hoc check (no repo changes)

If you just want to confirm data is flowing before standing up a full
Collector, a few lines of Python stood up locally will do it — this is not a
script shipped in this repo, just something you can save and run yourself:

```python
# save locally as e.g. quick_otlp_check.py -- not part of this repo
# requires: pip install grpcio opentelemetry-proto
from concurrent import futures
import grpc
from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2, metrics_service_pb2_grpc

class Printer(metrics_service_pb2_grpc.MetricsServiceServicer):
  def Export(self, request, context):
    for rm in request.resource_metrics:
      for sm in rm.scope_metrics:
        for m in sm.metrics:
          print(m.name)
    return metrics_service_pb2.ExportMetricsServiceResponse()

server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
metrics_service_pb2_grpc.add_MetricsServiceServicer_to_server(Printer(), server)
server.add_insecure_port("[::]:4317")
server.start()
print("Listening on :4317, Ctrl-C to stop")
server.wait_for_termination()
```

Point `CONTROLLER_METRICS_ENDPOINT` at `<host-or-container-name>:4317`,
restart the controller, and trigger some tracking activity. You should see
metric names printing as they export (every
`CONTROLLER_METRICS_EXPORT_INTERVAL_S` seconds, default 60 — set it lower,
e.g. `5`, while testing so you're not waiting a full minute per export).

This is enough to confirm the pipe is connected. For anything you'd act on
(latency trends, correlating against camera/tracked-object count), use the
real Collector path above.

## Metrics reference

| Metric                                                  | Kind      | Unit  | Tagged with | Meaning                                                               |
| ------------------------------------------------------- | --------- | ----- | ----------- | --------------------------------------------------------------------- |
| `scenescape_controller_reid_match_latency`              | histogram | s     | `category`  | Raw per-match latency samples; source for rigorous P95/P99 downstream |
| `scenescape_controller_reid_rolling_avg_match_latency`  | gauge     | s     | `category`  | Average over the last 10 matches                                      |
| `scenescape_controller_reid_rolling_min_match_latency`  | gauge     | s     | `category`  | Min over the last 10 matches                                          |
| `scenescape_controller_reid_rolling_max_match_latency`  | gauge     | s     | `category`  | Max over the last 10 matches                                          |
| `scenescape_controller_reid_current_camera_count`       | gauge     | count | `category`  | Cameras configured _and_ confirmed producing embeddings               |
| `scenescape_controller_reid_tracked_object_count`       | gauge     | count | `category`  | Active tracked objects/persons for one category                       |
| `scenescape_controller_reid_total_tracked_object_count` | gauge     | count | —           | Sum of tracked-object count across every category                     |

All ReID gauges and the histogram carry the same `category` attribute
(e.g. `person` vs `car`) so multiple tracked categories do not collide on
the same series — except the total tracked-object count, which is
intentionally unattributed since it is already summed across categories.

Plus the pre-existing controller metrics (MQTT throughput, tracking
duration, time-chunking stats) — those export the same way, unrelated to
ReID.

## Computing P95/P99

The histogram itself does not carry a precomputed percentile — only raw
`count`/`sum`/`min`/`max` plus bucket data. Real P95/P99 come from a proper
metrics backend querying that bucket data over a time range, e.g. in
Prometheus:

```promql
histogram_quantile(0.95,
  sum(rate(scenescape_controller_reid_match_latency_bucket[5m])) by (le, category))

histogram_quantile(0.99,
  sum(rate(scenescape_controller_reid_match_latency_bucket[5m])) by (le, category))
```

## Troubleshooting

- **No data reaching the Collector/receiver at all**: confirm
  `CONTROLLER_ENABLE_METRICS=true` _and_ `CONTROLLER_METRICS_ENDPOINT` is
  set — if the endpoint is empty, metrics init silently disables itself
  even with the flag on. Also confirm the controller can actually reach the
  receiver's host:port (same Docker network, correct alias/hostname, port
  not typo'd).
- **Other metrics appear but ReID-specific ones (`reid_*`) never show up**:
  those only fire on real match decisions — confirm cameras are actually
  streaming and objects are being detected/tracked, not just that the
  controller is up.
- **Changed `CONTROLLER_METRICS_EXPORT_INTERVAL_S` and nothing changed**:
  it is only read once, at process start (`metrics.init()`) — restart the
  `scene`/`controller-analytics` container after changing it.
