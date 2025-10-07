# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
SceneScape Controller Metrics Module

Provides a simplified OpenTelemetry-based metrics collection API for the SceneScape
controller service. This module enables monitoring of MQTT message processing performance
and error conditions through standardized OpenTelemetry metrics.

IMPORTANT NOTICES:
    EXPERIMENTAL FEATURE: This metrics module is currently experimental and may undergo
    significant changes in future versions. The API and behavior are not yet stable and
    should be used with caution in production environments.

    SECURITY WARNING: Currently supports ONLY INSECURE communication with OTLP endpoints.
    All metrics are transmitted without TLS encryption or authentication. This must be
    addressed before production deployment.

PUBLIC API:
    Simplified functions for common metric operations:
    - init(): Initialize the metrics system (call once at startup)
    - inc_messages(attributes=None): Increment processed messages counter
    - inc_dropped_fellbehind(attributes=None): Increment fell-behind dropped messages counter
    - inc_dropped_trackerbusy(attributes=None): Increment tracker-busy dropped messages counter
    - set_object_count(count, attributes=None): Record object count in messages
    - time_message(attributes=None): Context manager for timing message processing

    All functions accept optional attributes dict for metric labels/dimensions.

METRICS EXPORTED:
    - scenescape_controller_mqtt_messages: Counter of total processed messages
    - scenescape_controller_mqtt_message_duration: Histogram of processing duration (ms)
    - scenescape_controller_mqtt_messages_dropped_fellbehind: Counter of fell-behind drops
    - scenescape_controller_mqtt_messages_dropped_trackerbusy: Counter of tracker-busy drops
    - scenescape_controller_objects_in_mqtt_message: Histogram of object counts per message

CONFIGURATION:
    Environment variables:
    - CONTROLLER_ENABLE_METRICS: "true"/"false" (default: "false")
    - CONTROLLER_METRICS_ENDPOINT: OTLP gRPC endpoint (e.g., "otel-collector:4317")
    - CONTROLLER_METRICS_EXPORT_INTERVAL_S: Export interval in seconds (default: 60)

USAGE EXAMPLE:
    # Initialize once at startup
    metrics.init()
    
    # Use throughout application
    metrics.inc_messages({"camera": "cam1", "topic": "detection"})
    
    with metrics.time_message({"processing_type": "detection"}):
        # Process message - duration automatically recorded
        process_detection_message()
    
    metrics.set_object_count(len(objects), {"scene": "warehouse1"})

LIMITATIONS:
    - Insecure OTLP connections only (no TLS/authentication)
    - Singleton pattern - initialize once per process
    - Automatic shutdown via atexit (may not work in all exit scenarios)
"""


import time
import os
from contextlib import contextmanager

from scene_common import log

from opentelemetry import metrics
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

# Export simplified public API functions only
__all__ = ['init', 'inc_messages', 'time_message',
           'inc_dropped_fellbehind', 'inc_dropped_trackerbusy', 'record_object_count', 'time_execution']

# OpenTelemetry metric name constants
METRIC_MQTT_MESSAGES_COUNT = "scenescape_controller_mqtt_messages"
METRIC_MQTT_MESSAGES_DURATION = "scenescape_controller_mqtt_message_duration"
METRIC_MQTT_MESSAGES_DROPPED_FELLBEHIND = "scenescape_controller_mqtt_messages_dropped_fellbehind"
METRIC_MQTT_MESSAGES_DROPPED_TRACKERBUSY = "scenescape_controller_mqtt_messages_dropped_trackerbusy"
METRIC_MQTT_MESSAGES_OBJECT_COUNT = "scenescape_controller_objects_in_mqtt_message"

METRIC_INSTRUMENTS = [
    {
        "name": METRIC_MQTT_MESSAGES_COUNT,
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
    },
    {
        "name": METRIC_MQTT_MESSAGES_OBJECT_COUNT,
        "description": "Histogram of the objects count contained in MQTT messages",
        "unit": "1",
        "kind": "histogram"
    }
]  

# OpenTelemetry service configuration
CONTROLLER_SERVICE_NAME = "scene-controller"
DEFAULT_METRICS_EXPORT_INTERVAL_S = 60

# Public API functions for metric operations
def init():
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
  """Increment the processed messages counter.
  
  Args:
      attributes (dict, optional): Metric labels/dimensions (e.g., {"camera": "cam1"}).
  """
  instance = _metrics_instance
  if instance:
    instance.counter_add(METRIC_MQTT_MESSAGES_COUNT, 1, attributes)

def inc_dropped_fellbehind(attributes=None):
  """Increment counter for messages dropped due to falling behind processing.
  
  Args:
      attributes (dict, optional): Metric labels/dimensions (e.g., {"reason": "overload"}).
  """
  instance = _metrics_instance
  if instance:
    instance.counter_add(METRIC_MQTT_MESSAGES_DROPPED_FELLBEHIND, 1, attributes)

def inc_dropped_trackerbusy(attributes=None):
  """Increment counter for messages dropped due to busy tracker work queue.
  
  Args:
      attributes (dict, optional): Metric labels/dimensions (e.g., {"tracker_type": "kalman"}).
  """
  instance = _metrics_instance
  if instance:
    instance.counter_add(METRIC_MQTT_MESSAGES_DROPPED_TRACKERBUSY, 1, attributes)

def record_object_count(count, attributes=None):
  """Record the number of objects contained in a processed message.
  
  Args:
      count (int): Number of objects in the message.
      attributes (dict, optional): Metric labels/dimensions (e.g., {"scene": "warehouse1"}).
  """
  instance = _metrics_instance
  if instance:
    instance.histogram_record(METRIC_MQTT_MESSAGES_OBJECT_COUNT, count, attributes)

@contextmanager
def time_message(attributes=None):
  """Context manager for timing message processing duration.
  
  Automatically records the execution time in milliseconds when the context exits.
  Works regardless of whether the code completes normally or raises an exception.
  
  Args:
      attributes (dict, optional): Metric labels/dimensions (e.g., {"message_type": "detection"}).
      
  Example:
      with time_message({"camera": "cam1"}):
          process_detection_message()
  """
  start_time = time.time_ns()
  try:
    yield
  finally:
    duration = (time.time_ns() - start_time) / 1e6  # Convert to milliseconds
    instance = _metrics_instance
    if instance and instance.enable_metrics:
      instance.histogram_record(METRIC_MQTT_MESSAGES_DURATION, duration, attributes)

# Internal implementation - do not use directly
_metrics_instance = None

class _metrics:
  """Internal metrics management class.
  
  Handles OpenTelemetry setup, metric instrument creation, and metric recording.
  This class should not be used directly - use the module-level functions instead.
  """

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
    """Create OpenTelemetry metric instruments based on METRIC_INSTRUMENTS configuration."""    
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
    """Add value to a counter metric if it exists.
    
    Args:
        attr_name (str): Name of the counter metric attribute.
        value (int): Value to add (default: 1).
        attributes (dict): Metric labels/dimensions.
    """
    counter = getattr(self, attr_name, None)
    if counter is not None:
      counter.add(value, attributes=attributes)

  def histogram_record(self, attr_name, value, attributes=None):
    """Record a value in a histogram metric if it exists.
    
    Args:
        attr_name (str): Name of the histogram metric attribute.
        value (float): Value to record.
        attributes (dict): Metric labels/dimensions.
    """
    histogram = getattr(self, attr_name, None)
    if histogram is not None:
      histogram.record(value, attributes=attributes)
