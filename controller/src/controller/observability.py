# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
SceneScape Controller Observability Module

This module provides OpenTelemetry-based metrics collection and export capabilities for the
SceneScape controller service. It enables monitoring of MQTT message processing performance
and error conditions through standardized metrics.

IMPORTANT NOTICES:
    EXPERIMENTAL FEATURE: This observability module is currently experimental and may
    undergo significant changes in future versions. The API and behavior are not yet
    stable and should be used with caution in production environments.

    SECURITY WARNING: At the current moment, this module supports ONLY INSECURE
    communication with the OTLP (OpenTelemetry Protocol) endpoint. All metrics are
    transmitted without TLS encryption or authentication. This should be addressed
    before production deployment.

PUBLIC API:
    This module exports the following functions for metrics collection:
    - init(): Initialize the observability system
    - inc_processed_messages_metric_decorator(): Decorator for counting processed messages
    - time_message_duration_metric_decorator(): Decorator for timing message processing
    - inc_dropped_fellbehind_metric(): Count messages dropped due to falling behind
    - inc_dropped_trackerbusy_metric(): Count messages dropped due to busy tracker

    See individual function docstrings for detailed usage information.

METRICS EXPORTED:
    - scenescape_controller_mqtt_messages_total: Counter of total processed messages
    - scenescape_controller_mqtt_message_duration: Histogram of processing duration (ms)
    - scenescape_controller_mqtt_messages_dropped_fellbehind_total: Counter of messages
      dropped due to falling behind
    - scenescape_controller_mqtt_messages_dropped_trackerbusy_total: Counter of messages
      dropped due to busy tracker

CONFIGURATION:
    The module is configured via environment variables:
    - CONTROLLER_ENABLE_METRICS: "true"/"false"
    - CONTROLLER_METRICS_ENDPOINT: OTLP gRPC endpoint (e.g., "http://otel-collector:4317")
    - CONTROLLER_METRICS_EXPORT_INTERVAL_S: Positive integer (default: 60)

USAGE PATTERN:
    1. Call init() once during application startup
    2. Apply decorators to functions that process messages
    3. Call increment functions when error conditions occur
    4. Metrics are automatically exported to the configured endpoint

LIMITATIONS:
    - Only supports insecure OTLP connections (no TLS/authentication)
    - Singleton pattern - can only be initialized once per process
"""

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
DEFAULT_METRICS_EXPORT_INTERVAL_S = 60

# public API to the singleton instance
def init():
  """Initialize the observability system.

  Must be called once before using any other functions. Reads configuration from
  environment variables:
  - CONTROLLER_ENABLE_METRICS: Enable/disable metrics ("true"/"false", default: "false")
  - CONTROLLER_METRICS_ENDPOINT: OTLP endpoint URL (required if metrics enabled)
  - CONTROLLER_METRICS_EXPORT_INTERVAL_S: Export interval in seconds (default: 15)

  Raises:
      RuntimeError: If called multiple times.
  """
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
  """Return a decorator that increments the 'scenescape_controller_mqtt_messages_total' counter.

  This decorator specifically operates on the MQTT messages total counter metric.
  Use this decorator on functions that process MQTT messages to automatically track
  message throughput. The counter is incremented each time the decorated function
  is called.

  Returns:
      Callable: A decorator function that increments the scenescape_controller_mqtt_messages_total counter.

  Example:
      @inc_processed_messages_metric_decorator()
      def process_mqtt_message(msg):
          # Process the MQTT message
          pass
  """
  return _count_messages_decorator(METRIC_MQTT_MESSAGES_TOTAL)

def time_message_duration_metric_decorator():
  """Return a decorator that records execution time in the 'scenescape_controller_mqtt_message_duration' histogram.

  This decorator specifically operates on the MQTT message processing duration histogram metric.
  Measures the duration of function execution in milliseconds and records it in
  the histogram for MQTT message processing performance monitoring.

  Returns:
      Callable: A decorator function that records timing data in the scenescape_controller_mqtt_message_duration histogram.

  Example:
      @time_message_duration_metric_decorator()
      def handle_mqtt_message(msg):
          # Handle the MQTT message - duration will be automatically recorded
          pass
  """
  return _time_duration_decorator(METRIC_MQTT_MESSAGES_DURATION)

def inc_dropped_fellbehind_metric():
  """Increment the counter for messages dropped due to 'FELL BEHIND' condition.

  Call this function when the controller drops messages because it's falling
  behind processing and cannot keep up with the incoming message rate.
  """
  _observability_instance.counter_add(METRIC_MQTT_MESSAGES_DROPPED_FELLBEHIND)

def inc_dropped_trackerbusy_metric():
  """Increment the counter for messages dropped due to 'Tracker work queue is not empty'.

  Call this function when messages are dropped because the tracker is busy and
  its work queue is not empty, preventing new message processing.
  """
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
