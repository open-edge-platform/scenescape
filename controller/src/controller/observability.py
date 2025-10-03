# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0


# TODO: secure communication with OTLP endpoint
# TODO: clean shutdown of metric exporter

import functools
import time
import os

from scene_common import log

from opentelemetry import metrics
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

# Only export the public functions, not the class
__all__ = ['init', 'inc_processed_messages_metric_decorator', 'time_message_duration_metric_decorator', 'inc_dropped_fellbehind_metric', 'inc_dropped_trackerbusy_metric']

# Metric definition
METRIC_MQTT_MESSAGES_TOTAL = "scenescape_controller_mqtt_messages_total"
METRIC_MQTT_MESSAGES_DURATION = "scenescape_controller_mqtt_message_duration"
METRIC_MQTT_MESSAGES_DROPPED_FELLBEHIND = "scenescape_controller_mqtt_messages_dropped_fellbehind_total"
METRIC_MQTT_MESSAGES_DROPPED_TRACKERBUSY = "scenescape_controller_mqtt_messages_dropped_trackerbusy_total"

METRIC_INSTRUMENTS = [
    {
        "name": METRIC_MQTT_MESSAGES_TOTAL,
        "description": "Total number of MQTT messages processed by the scene controller",
        "unit": "1",
        "kind": "counter"
    },
    {
        "name": METRIC_MQTT_MESSAGES_DURATION,
        "description": "Histogram of MQTT message processing duration for the scene controller (ms)",
        "unit": "ms",
        "kind": "histogram"
    },
    {
        "name": METRIC_MQTT_MESSAGES_DROPPED_FELLBEHIND,
        "description": "Total number of MQTT messages dropped due to 'FELL BEHIND' in the scene controller",
        "unit": "1",
        "kind": "counter"
    },
    {
        "name": METRIC_MQTT_MESSAGES_DROPPED_TRACKERBUSY,
        "description": "Total number of MQTT messages dropped due to 'Tracker work queue is not empty' in the scene controller",
        "unit": "1",
        "kind": "counter"
    }
]

# Name of the service for OpenTelemetry
CONTROLLER_SERVICE_NAME = "scene-controller"
DEFAULT_METRICS_EXPORT_INTERVAL_S = 15

# public API to the singleton instance
def init():
  global _observability_instance
  if _observability_instance is not None:
    raise RuntimeError("Observability has already been initialized")

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

  _observability_instance = _observability(enable_metrics, metrics_endpoint, export_interval_s)

def inc_processed_messages_metric_decorator():
  return _count_messages_decorator(METRIC_MQTT_MESSAGES_TOTAL)

def time_message_duration_metric_decorator():
  return _time_duration_decorator(METRIC_MQTT_MESSAGES_DURATION)

def inc_dropped_fellbehind_metric():
  _observability_instance.counter_add(METRIC_MQTT_MESSAGES_DROPPED_FELLBEHIND)

def inc_dropped_trackerbusy_metric():
  _observability_instance.counter_add(METRIC_MQTT_MESSAGES_DROPPED_TRACKERBUSY)

# implementation details below
_observability_instance = None

def _count_messages_decorator(attr_name):
  def decorator(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
      o11y = _observability_instance
      # If metrics are disabled, just call the original function
      if not o11y.enable_metrics:
        return func(*args, **kwargs)
      # Increment the counter
      o11y.counter_add(attr_name)
      # Call the original function
      return func(*args, **kwargs)
    return wrapper
  return decorator

def _time_duration_decorator(histogram_name):
  def decorator(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
      o11y = _observability_instance
      # If metrics are disabled, just call the original function
      if not o11y.enable_metrics:
        return func(*args, **kwargs)
      # Start timing
      start_time = time.time_ns()
      try:
        # Call the original function
        return func(*args, **kwargs)
      finally:
        # Record duration regardless of success/failure
        duration = (time.time_ns() - start_time) / 1e6 # Convert to milliseconds
        o11y.histogram_record(histogram_name, duration)
    return wrapper
  return decorator

# Internal class to manage observability
class _observability:

  def __init__(self, enable_metrics, otlp_endpoint, export_interval_s):
    self.enable_metrics = enable_metrics
    if enable_metrics:
      log.info(f"OpenTelemetry metrics enabled for scene controller; exporting to: {otlp_endpoint}")
      self.meter = self.init_meter(otlp_endpoint, export_interval_s)
      self.init_metrics()
    else:
      log.info("OpenTelemetry metrics disabled for scene controller")
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
    for instrument in METRIC_INSTRUMENTS:
      if instrument["kind"] == "counter":
        setattr(self, instrument["name"], self.meter.create_counter(
            name=instrument["name"],
            description=instrument["description"],
            unit=instrument["unit"]))
      elif instrument["kind"] == "histogram":
        setattr(self, instrument["name"], self.meter.create_histogram(
            name=instrument["name"],
            description=instrument["description"],
            unit=instrument["unit"]))

  def counter_add(self, attr_name, value=1):
    counter = getattr(self, attr_name, None)
    if counter is not None:
      counter.add(value)

  def histogram_record(self, attr_name, value):
    histogram = getattr(self, attr_name, None)
    if histogram is not None:
      histogram.record(value)
