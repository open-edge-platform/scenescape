# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Observability module for the scene controller. This module sets up OpenTelemetry metrics
for the scene controller service. It provides functions to initialize, retrieve, and shut down the observability
instance. The observability instance is a singleton that manages the meter.

Usage:
    from controller.observability import initialize_observability, get_observability, shutdown_observability
    obs = initialize_observability(enable_metrics=True, otlp_endpoint="http://localhost:4317")
    meter = obs.meter
    # Use meter as needed
"""
import functools
import time

from opentelemetry import metrics
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from scene_common import log

# Only export the public functions, not the class
__all__ = [
    'initialize_observability',
    'get_observability',
    'shutdown_observability',
    'count',
    'time_duration']

# Name of the service for OpenTelemetry
CONTROLLER_SERVICE_NAME = "scene-controller"
EXPORT_INTERVAL_MS = 5000  # Export metrics every 5 seconds

# Metric name constants
METRIC_MQTT_MESSAGES_TOTAL = "scenescape_controller_mqtt_messages_total"
METRIC_MQTT_MESSAGES_DURATION = "scenescape_controller_mqtt_message_duration"
METRIC_MQTT_MESSAGES_DROPPED_FELLBEHIND = "scenescape_controller_mqtt_messages_dropped_fellbehind_total"
METRIC_MQTT_MESSAGES_DROPPED_TRACKERBUSY = "scenescape_controller_mqtt_messages_dropped_trackerbusy_total"

# Global singleton instance
_observability_instance = None


def initialize_observability(
        enable_metrics=False,
        otlp_endpoint=None):
  global _observability_instance
  if _observability_instance is None:
    _observability_instance = _Observability(
        enable_metrics, otlp_endpoint)
  else:
    raise RuntimeError("Observability has already been initialized")
  return _observability_instance


def get_observability():
  global _observability_instance
  if _observability_instance is None:
    raise RuntimeError("Observability has not been initialized")
  return _observability_instance

# TODO: shutdown handling
def shutdown_observability():
  global _observability_instance
  if _observability_instance is not None:
    # Perform any necessary cleanup here
    _observability_instance = None

# Decorators for metrics

def count(attr_name="mqtt_messages_total"):
  """
  Generic decorator to increment counters for function calls.

  Args:
      attr_name: Name of the Observability attribute to increment (default: "mqtt_messages_total").
                 Available attributes: mqtt_messages_total,
                 mqtt_messages_dropped_fellbehind, mqtt_messages_dropped_trackerbusy
  """
  def decorator(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
      o11y = get_observability()

      # If metrics are disabled, just call the original function
      if not o11y.enable_metrics:
        return func(*args, **kwargs)

      # Get the counter attribute by name and increment it
      counter = getattr(o11y, attr_name, None)
      if counter is not None:
        counter.add(1)

      return func(*args, **kwargs)
    return wrapper
  return decorator


def time_duration(histogram_name="mqtt_message_duration"):
  """
  Decorator to measure and record function execution duration.

  Args:
      histogram_name: Name of the histogram attribute to record duration in (default: "mqtt_message_duration")
                     Available histograms: mqtt_message_duration
  """
  def decorator(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
      o11y = get_observability()

      # If metrics are disabled, just call the original function
      if not o11y.enable_metrics:
        return func(*args, **kwargs)

      # Start timing
      start_time = time.time_ns()

      try:
        # Execute the original function
        result = func(*args, **kwargs)
        return result
      finally:
        # Record duration regardless of success/failure
        duration = (time.time_ns() - start_time) / 1e6 # Convert to milliseconds
        histogram = getattr(o11y, histogram_name, None)
        if histogram is not None:
          histogram.record(duration)
    return wrapper
  return decorator

# TODO: secure communication with OTLP endpoint
# TODO: ratio-based sampling (e.g., 1 out of N requests)


# Internal class to manage observability (metrics and tracing)
class _Observability:

  def __init__(self, enable_metrics, otlp_endpoint):
    # Store flags for decorator checks
    self.enable_metrics = enable_metrics

    if enable_metrics :
      if otlp_endpoint is None or otlp_endpoint == "":
        raise ValueError(
            "OTLP endpoint must be provided when metrics are enabled")

    if enable_metrics:
      self.meter = self.createMeter(otlp_endpoint)
      self.mqtt_messages_total = self.meter.create_counter(
        name=METRIC_MQTT_MESSAGES_TOTAL,
        description="Total number of MQTT messages processed by the scene controller",
        unit="1")
      self.mqtt_message_duration = self.meter.create_histogram(
        name=METRIC_MQTT_MESSAGES_DURATION,
        description="Histogram of MQTT message processing duration for the scene controller (ms)",
        unit="ms")
      self.mqtt_messages_dropped_fellbehind = self.meter.create_counter(
        name=METRIC_MQTT_MESSAGES_DROPPED_FELLBEHIND,
        description="Total number of MQTT messages dropped due to 'FELL BEHIND' in the scene controller",
        unit="1")
      self.mqtt_messages_dropped_trackerbusy = self.meter.create_counter(
        name=METRIC_MQTT_MESSAGES_DROPPED_TRACKERBUSY,
        description="Total number of MQTT messages dropped due to 'Tracker work queue is not empty' in the scene controller",
        unit="1")
      log.info("OpenTelemetry metrics enabled for scene controller")
      log.info(f"Metrics will be exported to OTLP endpoint: {otlp_endpoint}")
      log.info(f"Metric names: {METRIC_MQTT_MESSAGES_TOTAL}, {METRIC_MQTT_MESSAGES_DURATION}, {METRIC_MQTT_MESSAGES_DROPPED_FELLBEHIND}, {METRIC_MQTT_MESSAGES_DROPPED_TRACKERBUSY}")

  def createMeter(self, otlp_endpoint):
    # Set up the OTLP metric exporter and meter provider
    metric_exporter = OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True)
    metric_reader = PeriodicExportingMetricReader(
        metric_exporter, export_interval_millis=EXPORT_INTERVAL_MS)
    resource = Resource(attributes={SERVICE_NAME: CONTROLLER_SERVICE_NAME})
    provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(provider)
    meter = metrics.get_meter(__name__)
    return meter
