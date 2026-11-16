# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""gRPC entry point for the Observation Processor service.

Exposes scenescape.observation_processor.v1.ObservationProcessorService and the standard
grpc.health.v1.Health service. The server liveness status ("") is SERVING once
the process is up; the ObservationProcessorService readiness status follows the
availability of a successfully warmed configuration snapshot.
"""

import os
import threading
from concurrent import futures

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from scene_common import log
from scene_common.mqtt import PubSub
from observation_processor.conditioning import InvalidRequestError, process_detections
from observation_processor.grpc_api import observation_processor_pb2_grpc
from observation_processor.grpc_tls import bind_server_port, insecure_requested
from observation_processor.scene_provider import (
  CameraNotCalibratedError, CameraNotFoundError, CameraResolutionUnsupportedError,
  InvalidAssetPriorError, SceneMeshMissingError, SceneMeshTooLargeError,
  SceneNotFoundError, SceneProvider, StoreUnavailableError,
)

SERVICE_NAME = "scenescape.observation_processor.v1.ObservationProcessorService"
DEFAULT_PORT = 50052
DEFAULT_READY_INTERVAL_SECONDS = 10.0
DEFAULT_BROKER = "broker.scenescape.intel.com"
BROKER_RETRY_SECONDS = 5.0


class ObservationProcessorServicer(
  observation_processor_pb2_grpc.ObservationProcessorServiceServicer
):
  """Typed frame projection with whole-frame gRPC error semantics."""

  def __init__(self, provider=None):
    self.provider = provider

  def ProcessDetections(self, request, context):
    try:
      if self.provider is None:
        raise StoreUnavailableError("configuration provider is not initialized")
      return process_detections(request, self.provider)
    except InvalidRequestError as exc:
      context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
    except (SceneNotFoundError, CameraNotFoundError):
      context.abort(grpc.StatusCode.NOT_FOUND, "scene or camera was not found in the scene")
    except (CameraNotCalibratedError, CameraResolutionUnsupportedError,
            InvalidAssetPriorError, SceneMeshMissingError, SceneMeshTooLargeError) as exc:
      context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(exc))
    except StoreUnavailableError:
      context.abort(grpc.StatusCode.UNAVAILABLE, "configuration store or cache is unavailable")
    except Exception as exc:
      log.error(f"observation-processor-service: frame processing failed ({type(exc).__name__}): {exc}")
      context.abort(grpc.StatusCode.INTERNAL, "projection or conditioning failed")


def create_server(servicer=None, max_workers=4):
  """Create the gRPC server with the Observation Processor and Health services registered.

  @param   servicer      ObservationProcessorServiceServicer instance
  @param   max_workers   thread pool size for request handling
  @return                (server, health_servicer); the caller owns start/stop and
                         flips the SERVICE_NAME readiness status on health_servicer
  """
  server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
  observation_processor_pb2_grpc.add_ObservationProcessorServiceServicer_to_server(
    servicer or ObservationProcessorServicer(), server)
  health_servicer = health.HealthServicer()
  health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
  health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
  health_servicer.set(SERVICE_NAME, health_pb2.HealthCheckResponse.NOT_SERVING)
  return server, health_servicer


def _probe_readiness(provider, was_ready, health_servicer=None):
  """Refresh configuration without withdrawing an already usable snapshot."""
  current = provider.is_ready()
  if current and provider.needs_refresh:
    if health_servicer is not None and not provider.has_snapshot:
      health_servicer.set(SERVICE_NAME, health_pb2.HealthCheckResponse.NOT_SERVING)
    try:
      provider.warm()
    except (StoreUnavailableError, SceneMeshMissingError, OSError, ValueError,
            RuntimeError) as exc:
      log.warning(f"observation-processor-service: cache warm failed: {exc}")
  return provider.has_snapshot


def start_readiness_monitor(provider, health_servicer,
                            interval=DEFAULT_READY_INTERVAL_SECONDS, stop_event=None):
  """Poll the static data store and keep the readiness status in sync.

  Startup loads configuration, meshes and reasoners before reporting readiness.
  Database events wake this worker; refreshes retain the last usable snapshot.
  Expensive loading runs here, not on the MQTT loop.

  @param   provider         SceneProvider probed with is_ready()
  @param   health_servicer  health.HealthServicer owning the per-service status
  @param   interval         seconds between probes
  @param   stop_event       optional threading.Event ending the loop (for tests)
  @return                   the started daemon thread
  """
  stop_event = stop_event or threading.Event()

  def monitor():
    ready = None
    while not stop_event.is_set():
      current = _probe_readiness(provider, ready, health_servicer)
      status = health_pb2.HealthCheckResponse.SERVING if current \
          else health_pb2.HealthCheckResponse.NOT_SERVING
      health_servicer.set(SERVICE_NAME, status)
      if current != ready:
        ready = current
        log.info(f"observation-processor-service readiness: {'SERVING' if ready else 'NOT_SERVING'}")
      if not stop_event.is_set():
        provider.wait_for_refresh(interval)

  thread = threading.Thread(target=monitor, name="readiness-monitor", daemon=True)
  thread.stop_event = stop_event
  thread.start()
  return thread


def start_database_watcher(provider, broker, auth, rootcert, stop_event=None):
  """Schedule a cache refresh when the Manager announces database changes.

  Subscribes to scenescape/cmd/database (payload "update", published by the
  Manager on every configuration save). Subscription happens in on_connect so
  it survives broker reconnects; the initial connect is retried until the
  broker is reachable.

  @param   provider    SceneProvider whose invalidate() schedules a full refresh
  @param   broker      MQTT broker host or host:port
  @param   auth        auth file shared with the REST API (user/password JSON)
  @param   rootcert    TLS root certificate path
  @param   stop_event  optional threading.Event ending the connect retry loop
  @return              the connected PubSub instance (network loop running)
  """
  stop_event = stop_event or threading.Event()
  pubsub = PubSub(auth, None, rootcert, broker)
  topic = PubSub.formatTopic(PubSub.CMD_DATABASE)

  def on_change(client, userdata, message):
    if message.payload == b"update":
      log.info("observation-processor-service: database updated; scheduling cache refresh")
      provider.invalidate()

  def on_connect(client, userdata, flags, rc):
    if rc != 0:
      log.warning(f"observation-processor-service: broker connection rejected: {rc}")
      return
    pubsub.addCallback(topic, on_change, qos=1)
    provider.invalidate()
    log.info(f"observation-processor-service: subscribed to {topic}")

  pubsub.onConnect = on_connect

  def connect_with_retry():
    while not stop_event.is_set():
      try:
        pubsub.connect()
        pubsub.loopStart()
        return
      except (OSError, ValueError) as exc:
        log.warning(f"observation-processor-service: broker connect failed, retrying: {exc}")
        stop_event.wait(BROKER_RETRY_SECONDS)

  thread = threading.Thread(target=connect_with_retry, name="database-watcher",
                            daemon=True)
  thread.start()
  return pubsub


def main():
  port = int(os.getenv("OBSERVATION_PROCESSOR_SERVICE_PORT", str(DEFAULT_PORT)))
  interval = float(os.getenv("OBSERVATION_PROCESSOR_READY_INTERVAL_SECONDS",
                             str(DEFAULT_READY_INTERVAL_SECONDS)))
  provider = SceneProvider.from_env()
  server, health_servicer = create_server(ObservationProcessorServicer(provider))
  bind_server_port(server, port)
  server.start()
  start_readiness_monitor(provider, health_servicer, interval)
  start_database_watcher(
    provider,
    broker=os.getenv("OBSERVATION_PROCESSOR_BROKER", DEFAULT_BROKER),
    auth=provider.auth,
    rootcert=provider.rootcert,
  )
  transport = "insecure" if insecure_requested() else "TLS"
  log.info(f"observation-processor-service gRPC listening on :{port} ({transport})")
  server.wait_for_termination()


if __name__ == "__main__":
  main()
