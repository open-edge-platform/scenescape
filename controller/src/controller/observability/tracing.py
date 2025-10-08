# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""OpenTelemetry tracing for SceneScape controller.

WARNING: Experimental API, insecure OTLP only.

Environment variables:
- CONTROLLER_ENABLE_TRACING: "true"/"false" (default: "false")
- CONTROLLER_TRACING_ENDPOINT: OTLP gRPC endpoint
- CONTROLLER_TRACING_SAMPLE_RATIO: Sampling ratio 0.0-1.0 (default: 1.0 - trace all, e.g. "0.1" for 10% sampling, "0.01" for 1% sampling)
"""

from contextlib import contextmanager
import os
import functools

from scene_common import log
from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor


# Export simplified public API functions only
__all__ = ['init', 'span_decorator', 'span_context']

# OpenTelemetry service configuration
CONTROLLER_SERVICE_NAME = "scene-controller"

def init():
    """Initialize OpenTelemetry tracing if enabled by environment variable."""

    global _tracing_instance
    if _tracing_instance is not None:
        log.warning("Tracing already initialized, ignoring subsequent init() call")
        return

    # Read configuration from environment variables
    enable_tracing = os.getenv("CONTROLLER_ENABLE_TRACING", "false").lower() == "true"
    tracing_endpoint = os.getenv("CONTROLLER_TRACING_ENDPOINT", "localhost:4317")
    sample_ratio = float(os.getenv("CONTROLLER_TRACING_SAMPLE_RATIO", "1.0"))
    sample_ratio = max(0.0, min(1.0, sample_ratio)) # Clamp ratio between 0.0 and 1.0

    if enable_tracing and not tracing_endpoint:
        log.error("CONTROLLER_ENABLE_TRACING is true but CONTROLLER_TRACING_ENDPOINT is not set")
        return

    _tracing_instance = _tracing(enable_tracing, tracing_endpoint, sample_ratio)

def span_decorator(span_name=None):
  """Decorator to create a tracing span around a function."""
  def decorator(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):

      # If tracing is disabled, just call the original function
      if not _tracing_instance._enabled:
        return func(*args, **kwargs)

      # Use custom span name or function name
      name = span_name or func.__name__

      with _tracing_instance._tracer.start_as_current_span(name) as span:
        try:
          result = func(*args, **kwargs)
          return result
        except Exception as e:
          span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
          raise
    return wrapper
  return decorator

@contextmanager
def span_context(span_name):
    """Context manager to create a tracing span around a block of code."""
    if not _tracing_instance._enabled:
        yield
        return

    with _tracing_instance._tracer.start_as_current_span(span_name) as span:
        try:
            yield span
        except Exception as e:
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            raise


# Internal implementation - do not use directly
_tracing_instance = None

class _tracing:
    """Internal tracing implementation"""

    def __init__(self, enable, otlp_endpoint, sample_ratio):
        self._enabled = enable

        if not self._enabled:
            log.info("Tracing disabled")
            return

        sampler = TraceIdRatioBased(sample_ratio)
        resource = Resource(attributes={SERVICE_NAME: CONTROLLER_SERVICE_NAME})
        provider = TracerProvider(resource=resource, sampler=sampler)
        trace.set_tracer_provider(provider)

        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        span_processor = BatchSpanProcessor(otlp_exporter)
        provider.add_span_processor(span_processor)

        self._tracer = trace.get_tracer(__name__)
        log.info(f"Tracing enabled, exporting to {otlp_endpoint} with sample ratio {sample_ratio}")
