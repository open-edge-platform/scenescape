# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Optional OpenTelemetry metrics owned by the Re-ID service."""

import os

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

from scene_common import log

SERVICE_NAME = "reid-service"
BACKEND_DURATION_BUCKETS = (0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)
DECISION_LATENCY_BUCKETS = (0.1, 0.25, 0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10, 15, 20, 30)
_provider = None
_decision_latency = None
_backend_query_duration = None
_backend_write_duration = None


def init():
  """Initialize optional OTLP metrics and return the provider for shutdown."""
  global _provider, _decision_latency, _backend_query_duration, _backend_write_duration
  if os.getenv("REID_ENABLE_METRICS", "false").lower() not in ("1", "true", "yes"):
    return None

  endpoint = os.getenv("REID_METRICS_ENDPOINT", "")
  if not endpoint:
    log.warning("REID_METRICS_ENDPOINT not set; disabling ReID metrics")
    return None

  provider = None
  try:
    export_interval_ms = int(os.getenv("REID_METRICS_EXPORT_INTERVAL_S", "60")) * 1000
    if export_interval_ms <= 0:
      raise ValueError()
  except ValueError:
    log.warning("Invalid REID_METRICS_EXPORT_INTERVAL_S; using default of 60s")
    export_interval_ms = 60000

  try:
    exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)
    reader = PeriodicExportingMetricReader(
      exporter, export_interval_millis=export_interval_ms)
    provider = MeterProvider(
      resource=Resource.create({"service.name": SERVICE_NAME}), metric_readers=[reader])
    meter = provider.get_meter(__name__)
    decision_latency = meter.create_histogram(
      "scenescape_reid_decision_latency", unit="s",
      description="Track first observation to completed ReID decision",
      explicit_bucket_boundaries_advisory=DECISION_LATENCY_BUCKETS)
    backend_query_duration = meter.create_histogram(
      "scenescape_reid_backend_query_duration", unit="s",
      description="Duration of a ReID backend similarity query",
      explicit_bucket_boundaries_advisory=BACKEND_DURATION_BUCKETS)
    backend_write_duration = meter.create_histogram(
      "scenescape_reid_backend_write_duration", unit="s",
      description="Duration of a ReID backend descriptor write",
      explicit_bucket_boundaries_advisory=BACKEND_DURATION_BUCKETS)
  except Exception as error:
    if provider is not None:
      provider.shutdown()
    log.warning(f"Could not initialize ReID metrics; disabling export: {error}")
    return None

  _provider = provider
  _decision_latency = decision_latency
  _backend_query_duration = backend_query_duration
  _backend_write_duration = backend_write_duration
  return provider


def record_decision_latency(duration_secs, category):
  """Record end-to-end matcher decision latency without affecting ingestion."""
  _record(_decision_latency, duration_secs, {"category": category})


def record_backend_query_duration(duration_secs, backend):
  """Record backend query duration separately from decision latency."""
  _record(_backend_query_duration, duration_secs, {"backend": backend})


def record_backend_write_duration(duration_secs, backend):
  """Record backend write duration separately from decision latency."""
  _record(_backend_write_duration, duration_secs, {"backend": backend})


def _record(histogram, value, attributes):
  if histogram is None:
    return
  try:
    histogram.record(max(0.0, float(value)), attributes=attributes)
  except Exception as error:
    log.warning(f"ReID metric recording failed: {error}")
