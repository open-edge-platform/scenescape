# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""OpenTelemetry metrics for SceneScape controller.

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
__all__ = ['init', 'inc_messages', 'inc_dropped', 'record_object_count', 'time_mqtt_handler', 'time_tracking']

# OpenTelemetry metric name constants
METRIC_MQTT_MESSAGES_COUNT = "scenescape_controller_mqtt_messages"
METRIC_MQTT_MESSAGES_DROPPED = "scenescape_controller_mqtt_messages_dropped"
METRIC_MQTT_HANDLER_DURATION = "scenescape_controller_mqtt_handler_duration"
METRIC_TRACKING_DURATION = "scenescape_controller_tracking_duration"
METRIC_MQTT_MESSAGES_OBJECT_COUNT = "scenescape_controller_objects_in_mqtt_message"

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
    }

    for instrument in METRIC_INSTRUMENTS:
      try:
        creator = INSTRUMENT_CREATORS[instrument["kind"]]
        setattr(self, instrument["name"], creator(
            name=instrument["name"],
            description=instrument["description"],
            unit=instrument["unit"]
        ))
      except KeyError:
        raise ValueError(f"Unknown instrument kind: '{instrument['kind']}'. Supported kinds: {list(INSTRUMENT_CREATORS.keys())}")

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
