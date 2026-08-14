# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""OpenTelemetry metrics for Scenescape controller.

WARNING: Experimental API, insecure OTLP only.

Environment variables:
- CONTROLLER_ENABLE_METRICS: "true"/"false" (default: "false")
- CONTROLLER_METRICS_ENDPOINT: OTLP gRPC endpoint
- CONTROLLER_METRICS_EXPORT_INTERVAL_S: Export interval in seconds (default: 60)
"""


import time
import os
from contextlib import contextmanager

from opentelemetry import metrics
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

from scene_common import log

# Export simplified public API functions only
__all__ = ['init', 'inc_messages', 'inc_dropped', 'record_object_count', 'time_mqtt_handler', 'time_tracking',
           'inc_time_chunking_duplicated_cameras', 'add_time_chunking_unique_cameras',
           'inc_time_chunking_non_empty_chunks', 'inc_time_chunking_empty_chunks',
           'record_reid_rolling_avg_match_latency',
           'record_reid_rolling_min_match_latency', 'record_reid_rolling_max_match_latency',
           'record_reid_match_latency',
           'record_reid_current_camera_count', 'record_reid_tracked_object_count',
           'record_reid_total_tracked_object_count']

# OpenTelemetry metric name constants
METRIC_MQTT_MESSAGES_COUNT = "scenescape_controller_mqtt_messages"
METRIC_MQTT_MESSAGES_DROPPED = "scenescape_controller_mqtt_messages_dropped"
METRIC_MQTT_HANDLER_DURATION = "scenescape_controller_mqtt_handler_duration"
METRIC_TRACKING_DURATION = "scenescape_controller_tracking_duration"
METRIC_MQTT_MESSAGES_OBJECT_COUNT = "scenescape_controller_objects_in_mqtt_message"
METRIC_TIME_CHUNKING_DUPLICATED_CAMERAS = "scenescape_controller_time_chunking_duplicated_cameras"
METRIC_TIME_CHUNKING_UNIQUE_CAMERAS = "scenescape_controller_time_chunking_unique_cameras"
METRIC_TIME_CHUNKING_NON_EMPTY_CHUNKS = "scenescape_controller_time_chunking_non_empty_chunks"
METRIC_TIME_CHUNKING_EMPTY_CHUNKS = "scenescape_controller_time_chunking_empty_chunks"
METRIC_REID_ROLLING_AVG_MATCH_LATENCY = "scenescape_controller_reid_rolling_avg_match_latency"
METRIC_REID_ROLLING_MIN_MATCH_LATENCY = "scenescape_controller_reid_rolling_min_match_latency"
METRIC_REID_ROLLING_MAX_MATCH_LATENCY = "scenescape_controller_reid_rolling_max_match_latency"
METRIC_REID_MATCH_LATENCY = "scenescape_controller_reid_match_latency"
METRIC_REID_CURRENT_CAMERA_COUNT = "scenescape_controller_reid_current_camera_count"
METRIC_REID_TRACKED_OBJECT_COUNT = "scenescape_controller_reid_tracked_object_count"
METRIC_REID_TOTAL_TRACKED_OBJECT_COUNT = "scenescape_controller_reid_total_tracked_object_count"

METRIC_INSTRUMENTS = [
    {
        "name": METRIC_MQTT_MESSAGES_COUNT,
        "description": "MQTT messages processed",
        "unit": "1",
        "kind": "counter"
    },
    {
        "name": METRIC_MQTT_MESSAGES_DROPPED,
        "description": "MQTT messages dropped",
        "unit": "1",
        "kind": "counter"
    },
    {
        "name": METRIC_MQTT_HANDLER_DURATION,
        "description": "MQTT handler processing time",
        "unit": "ms",
        "kind": "histogram"
    },
    {
        "name": METRIC_TRACKING_DURATION,
        "description": "Tracking thread processing time",
        "unit": "ms",
        "kind": "histogram"
    },
    {
        "name": METRIC_MQTT_MESSAGES_OBJECT_COUNT,
        "description": "Object count per MQTT message",
        "unit": "1",
        "kind": "histogram"
    },
    {
        "name": METRIC_TIME_CHUNKING_DUPLICATED_CAMERAS,
        "description": "Time-chunking buffered camera frames overwritten before dispatch",
        "unit": "1",
        "kind": "counter"
    },
    {
        "name": METRIC_TIME_CHUNKING_UNIQUE_CAMERAS,
        "description": "Time-chunking unique cameras dispatched per chunk",
        "unit": "1",
        "kind": "counter"
    },
    {
        "name": METRIC_TIME_CHUNKING_NON_EMPTY_CHUNKS,
        "description": "Time-chunking dispatch intervals with buffered data",
        "unit": "1",
        "kind": "counter"
    },
    {
        "name": METRIC_TIME_CHUNKING_EMPTY_CHUNKS,
        "description": "Time-chunking dispatch intervals with no buffered data",
        "unit": "1",
        "kind": "counter"
    },
    {
        "name": METRIC_REID_ROLLING_AVG_MATCH_LATENCY,
        "description": "Average ReID match latency over the last N recorded matches (rolling window, default N=10), updated on every match decision. Tagged with a category attribute (e.g. person, car) to distinguish tracked categories.",
        "unit": "s",
        "kind": "gauge"
    },
    {
        "name": METRIC_REID_ROLLING_MIN_MATCH_LATENCY,
        "description": "Minimum ReID match latency over the last N recorded matches (rolling window, default N=10), updated on every match decision. Tagged with a category attribute (e.g. person, car) to distinguish tracked categories.",
        "unit": "s",
        "kind": "gauge"
    },
    {
        "name": METRIC_REID_ROLLING_MAX_MATCH_LATENCY,
        "description": "Maximum ReID match latency over the last N recorded matches (rolling window, default N=10), updated on every match decision. Tagged with a category attribute (e.g. person, car) to distinguish tracked categories.",
        "unit": "s",
        "kind": "gauge"
    },
    {
        "name": METRIC_REID_MATCH_LATENCY,
        "description": "Per-match ReID latency, from a track's first appearance to its match/no-match decision. Feeds statistically rigorous P95/P99 computed downstream (e.g. Prometheus histogram_quantile()) over whatever time range is queried, rather than a fixed sample count. Tagged with a category attribute (e.g. person, car) to distinguish tracked categories.",
        "unit": "s",
        "kind": "histogram",
        "buckets": [0.1, 0.25, 0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10, 15, 20, 30]
    },
    {
        "name": METRIC_REID_CURRENT_CAMERA_COUNT,
        "description": "Camera count (configured and confirmed producing embeddings) tagged on the most recent ReID match decision -- same value as MatchLatencyTracker.getStats()['camera_count']. Also tagged with a category attribute to distinguish tracked categories.",
        "unit": "1",
        "kind": "gauge"
    },
    {
        "name": METRIC_REID_TRACKED_OBJECT_COUNT,
        "description": "Number of currently active tracked objects/persons whose category produces ReID embeddings (excludes non-ReID categories), sampled each tracking cycle. Tagged with a category attribute to distinguish tracked categories.",
        "unit": "1",
        "kind": "gauge"
    },
    {
        "name": METRIC_REID_TOTAL_TRACKED_OBJECT_COUNT,
        "description": "Total currently active tracked objects/persons summed across every ReID-capable category (e.g. person + car combined), via TrackedObjectRegistry",
        "unit": "1",
        "kind": "gauge"
    }
]

# OpenTelemetry service configuration
CONTROLLER_SERVICE_NAME = "scene-controller"
DEFAULT_METRICS_EXPORT_INTERVAL_S = 60

# Public API functions for metric operations
def init():
  """Initialize OpenTelemetry metrics if enabled by environment variable."""

  global _metrics_instance
  if _metrics_instance is not None:
    log.warning("Metrics already initialized, ignoring subsequent init() call")
    return

  # Read configuration from environment
  enable_metrics = os.getenv("CONTROLLER_ENABLE_METRICS", "false").lower() in ("1", "true", "yes")
  metrics_endpoint = os.getenv("CONTROLLER_METRICS_ENDPOINT", "")
  export_interval_s = os.getenv("CONTROLLER_METRICS_EXPORT_INTERVAL_S", str(DEFAULT_METRICS_EXPORT_INTERVAL_S))

  if enable_metrics and not metrics_endpoint:
    log.warning("CONTROLLER_METRICS_ENDPOINT not set; disabling metrics")
    enable_metrics = False

  try:
    export_interval_s = int(export_interval_s)
    if export_interval_s <= 0:
      raise ValueError()
  except ValueError:
    log.warning(f"Invalid CONTROLLER_METRICS_EXPORT_INTERVAL_S; using default of {DEFAULT_METRICS_EXPORT_INTERVAL_S}s")
    export_interval_s = DEFAULT_METRICS_EXPORT_INTERVAL_S

  _metrics_instance = _metrics(enable_metrics, metrics_endpoint, export_interval_s)

def inc_messages(attributes=None):
  """Increment processed messages counter."""
  instance = _metrics_instance
  if instance:
    instance.counter_add(METRIC_MQTT_MESSAGES_COUNT, 1, attributes)

def inc_dropped(attributes=None):
  """Increment dropped messages counter."""
  instance = _metrics_instance
  if instance:
    instance.counter_add(METRIC_MQTT_MESSAGES_DROPPED, 1, attributes)

def record_object_count(count, attributes=None):
  """Record object count in message."""
  instance = _metrics_instance
  if instance:
    instance.histogram_record(METRIC_MQTT_MESSAGES_OBJECT_COUNT, count, attributes)

def inc_time_chunking_duplicated_cameras(attributes=None):
  """Increment count of buffered camera frames overwritten before dispatch."""
  instance = _metrics_instance
  if instance:
    instance.counter_add(METRIC_TIME_CHUNKING_DUPLICATED_CAMERAS, 1, attributes)

def add_time_chunking_unique_cameras(count, attributes=None):
  """Add the number of unique cameras dispatched in a time-chunk."""
  instance = _metrics_instance
  if instance:
    instance.counter_add(METRIC_TIME_CHUNKING_UNIQUE_CAMERAS, count, attributes)

def inc_time_chunking_non_empty_chunks(attributes=None):
  """Increment count of dispatch intervals that had buffered data."""
  instance = _metrics_instance
  if instance:
    instance.counter_add(METRIC_TIME_CHUNKING_NON_EMPTY_CHUNKS, 1, attributes)

def inc_time_chunking_empty_chunks(attributes=None):
  """Increment count of dispatch intervals that had no buffered data."""
  instance = _metrics_instance
  if instance:
    instance.counter_add(METRIC_TIME_CHUNKING_EMPTY_CHUNKS, 1, attributes)

def record_reid_rolling_avg_match_latency(latency_s, attributes=None):
  """Report the current rolling-window average ReID match latency, in seconds."""
  instance = _metrics_instance
  if instance:
    instance.gauge_set(METRIC_REID_ROLLING_AVG_MATCH_LATENCY, latency_s, attributes)

def record_reid_rolling_min_match_latency(latency_s, attributes=None):
  """Report the current rolling-window minimum ReID match latency, in seconds."""
  instance = _metrics_instance
  if instance:
    instance.gauge_set(METRIC_REID_ROLLING_MIN_MATCH_LATENCY, latency_s, attributes)

def record_reid_rolling_max_match_latency(latency_s, attributes=None):
  """Report the current rolling-window maximum ReID match latency, in seconds."""
  instance = _metrics_instance
  if instance:
    instance.gauge_set(METRIC_REID_ROLLING_MAX_MATCH_LATENCY, latency_s, attributes)

def record_reid_match_latency(latency_s, attributes=None):
  """Record a single per-match ReID latency sample, in seconds. Feeds
  statistically rigorous P95/P99 computed downstream (e.g. Prometheus
  histogram_quantile()) rather than an in-process estimate."""
  instance = _metrics_instance
  if instance:
    instance.histogram_record(METRIC_REID_MATCH_LATENCY, latency_s, attributes)

def record_reid_current_camera_count(count, attributes=None):
  """Report the camera_count tagged on the most recent ReID match decision --
  same value as MatchLatencyTracker.getStats()['camera_count']."""
  instance = _metrics_instance
  if instance:
    instance.gauge_set(METRIC_REID_CURRENT_CAMERA_COUNT, count, attributes)

def record_reid_tracked_object_count(count, attributes=None):
  """Report the number of objects/persons currently tracked (active)."""
  instance = _metrics_instance
  if instance:
    instance.gauge_set(METRIC_REID_TRACKED_OBJECT_COUNT, count, attributes)

def record_reid_total_tracked_object_count(count, attributes=None):
  """Report the total tracked-object count summed across every category
  (e.g. person + car combined) -- see TrackedObjectRegistry."""
  instance = _metrics_instance
  if instance:
    instance.gauge_set(METRIC_REID_TOTAL_TRACKED_OBJECT_COUNT, count, attributes)

@contextmanager
def time_mqtt_handler(attributes=None):
  """Time MQTT handler processing duration."""
  instance = _metrics_instance
  if instance:
    with instance._time_message(METRIC_MQTT_HANDLER_DURATION, attributes):
      yield
  else:
    yield

@contextmanager
def time_tracking(attributes=None):
  """Time tracking thread processing duration."""
  instance = _metrics_instance
  if instance:
    with instance._time_message(METRIC_TRACKING_DURATION, attributes):
      yield
  else:
    yield

# Internal implementation - do not use directly
_metrics_instance = None

class _metrics:
  """Internal metrics implementation."""

  def __init__(self, enable_metrics, otlp_endpoint, export_interval_s):
    self.enable_metrics = enable_metrics
    if enable_metrics:
      log.info(f"Exporting OpenTelemetry metrics to {otlp_endpoint} every {export_interval_s}s")
      self.meter = self.init_meter(otlp_endpoint, export_interval_s)
      self.init_metrics()
    else:
      log.info("OpenTelemetry metrics disabled.")
      self.meter = None

  def init_meter(self, otlp_endpoint, export_interval_s):
    metric_exporter = OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True)
    metric_reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=export_interval_s * 1000)
    resource = Resource(attributes={SERVICE_NAME: CONTROLLER_SERVICE_NAME})
    provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(provider)
    meter = metrics.get_meter(__name__)
    return meter

  def init_metrics(self):
    """Create metric instruments."""
    INSTRUMENT_CREATORS = {
        "counter": self.meter.create_counter,
        "histogram": self.meter.create_histogram,
        "gauge": self.meter.create_gauge,
    }

    for instrument in METRIC_INSTRUMENTS:
      try:
        creator = INSTRUMENT_CREATORS[instrument["kind"]]
        setattr(self, instrument["name"], creator(
            name=instrument["name"],
            description=instrument["description"],
            unit=instrument["unit"]
        ))
        if instrument["kind"] == "counter":
          self.counter_add(instrument["name"], 0)  # Initialize counter to zero
      except KeyError:
        raise ValueError(f"Unknown instrument kind: '{instrument['kind']}'. Supported kinds: {list(INSTRUMENT_CREATORS.keys())}")

      kwargs = dict(
          name=instrument["name"],
          description=instrument["description"],
          unit=instrument["unit"]
      )
      buckets = instrument.get("buckets")
      if instrument["kind"] == "histogram" and buckets:
        try:
          # explicit_bucket_boundaries_advisory requires a newer OTel SDK
          # (~1.24+). Fall back to default buckets on older SDKs rather
          # than failing metrics init entirely -- the histogram still
          # works, just with less accurate percentile queries downstream.
          setattr(self, instrument["name"], creator(
              **kwargs, explicit_bucket_boundaries_advisory=buckets))
          continue
        except TypeError:
          log.warning(
              f"init_metrics: OTel SDK does not support explicit bucket "
              f"boundaries for '{instrument['name']}'; using default "
              f"buckets (percentile queries on this metric may be less "
              f"accurate). Consider upgrading opentelemetry-sdk.")

      setattr(self, instrument["name"], creator(**kwargs))
      if instrument["kind"] == "counter":
        self.counter_add(instrument["name"], 0)  # Initialize counter to zero

  def counter_add(self, attr_name, value=1, attributes=None):
    """Add value to counter metric."""
    counter = getattr(self, attr_name, None)
    if counter is not None:
      counter.add(value, attributes=attributes)

  def histogram_record(self, attr_name, value, attributes=None):
    """Record value in histogram metric."""
    histogram = getattr(self, attr_name, None)
    if histogram is not None:
      histogram.record(value, attributes=attributes)

  def gauge_set(self, attr_name, value, attributes=None):
    """Set the current value of a gauge metric (last-value semantics)."""
    gauge = getattr(self, attr_name, None)
    if gauge is not None:
      gauge.set(value, attributes=attributes)

  @contextmanager
  def _time_message(self, metric_name, attributes=None):
    """Time processing duration."""
    start_time = time.time_ns()
    try:
      yield
    finally:
      if self.enable_metrics:
        duration = (time.time_ns() - start_time) / 1e6  # Convert to milliseconds
        self.histogram_record(metric_name, duration, attributes)
