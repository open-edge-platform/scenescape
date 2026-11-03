# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Experimental remote projection of camera detections.

When CONTROLLER_EXPERIMENTAL_REMOTE_PROJECTION is true and CONTROLLER_REMOTE_PROJECTION_HOST and
CONTROLLER_REMOTE_PROJECTION_PORT are set, the tracker threads send the pixel boxes of camera
detections to the remote projection service (api/projection/v1/projection.proto) and replace the
local projection of their robot_vision inputs with its world measurement and measurement noise
covariance R.

A detection keeps the local projection when it is not a pixel box from a calibrated scene camera,
when the call fails, or when its measurement is unobservable or invalid. R is validated by the
robot_vision measurement_noise_covariance setter (finite, symmetrized, positive definite). Failed
calls and invalid
replies are counted (scenescape_controller_remote_projection_failed_calls) and logged at most once
per WARNING_INTERVAL_S per scene and category; they never raise into the tracker thread.

The gRPC stubs are generated at build time into the scenescape_api package and imported only
when remote projection is enabled.
"""

import math
import os
import threading
import time
from dataclasses import dataclass

import numpy as np

from controller.observability import metrics
from scene_common import log
from scene_common.camera import Camera

ENV_ENABLED = "CONTROLLER_EXPERIMENTAL_REMOTE_PROJECTION"
ENV_HOST = "CONTROLLER_REMOTE_PROJECTION_HOST"
ENV_PORT = "CONTROLLER_REMOTE_PROJECTION_PORT"
ENV_INSECURE = "CONTROLLER_REMOTE_PROJECTION_INSECURE"
ENV_CA_CERT = "CONTROLLER_REMOTE_PROJECTION_CA_CERT"
ENV_TIMEOUT_MS = "CONTROLLER_REMOTE_PROJECTION_TIMEOUT_MS"
ENV_MODE = "CONTROLLER_REMOTE_PROJECTION_MODE"

MODES = ("auto", "full", "frustum_only")
DEFAULT_MODE = "auto"
DEFAULT_TIMEOUT_MS = 50
# Upper bound of the call deadline; it should also stay below the time-chunking interval.
MAX_TIMEOUT_MS = 100
WARNING_INTERVAL_S = 10.0
MEASUREMENT_SIZE = 7

REASON_INVALID_RESPONSE = "invalid_response"
REASON_INVALID_MEASUREMENT = "invalid_measurement"
REASON_CLIENT_ERROR = "client_error"

_TRUE_VALUES = ("1", "true", "yes", "on")
_FALSE_VALUES = ("0", "false", "no", "off")


@dataclass(frozen=True)
class RemoteProjectionSettings:
  host: str
  port: int
  insecure: bool = False
  ca_cert: str = ""
  timeout_ms: int = DEFAULT_TIMEOUT_MS
  mode: str = DEFAULT_MODE


def _env_bool(environ, name, default):
  raw = environ.get(name, "").strip().lower()
  if not raw:
    return default
  if raw in _TRUE_VALUES:
    return True
  if raw in _FALSE_VALUES:
    return False
  raise ValueError(f"{name} must be true or false, got {raw!r}")


def _env_int(environ, name, default, minimum, maximum):
  raw = environ.get(name, "").strip()
  if not raw:
    return default
  try:
    value = int(raw)
  except ValueError:
    raise ValueError(f"{name} must be an integer, got {raw!r}") from None
  if not minimum <= value <= maximum:
    raise ValueError(f"{name} must be in [{minimum}, {maximum}], got {value}")
  return value


def settings_from_env(environ=None):
  """Remote projection settings when enabled and the endpoint is set, else None.

  @raises ValueError for an invalid value
  """
  environ = os.environ if environ is None else environ
  if not _env_bool(environ, ENV_ENABLED, False):
    return None
  host = environ.get(ENV_HOST, "").strip()
  port = _env_int(environ, ENV_PORT, 0, 1, 65535)
  if not host or not port:
    log.warning(f"{ENV_ENABLED} is set, but {ENV_HOST} and {ENV_PORT} are not; "
                "using local projection")
    return None
  mode = environ.get(ENV_MODE, "").strip().lower() or DEFAULT_MODE
  if mode not in MODES:
    raise ValueError(f"{ENV_MODE} must be one of {', '.join(MODES)}, got {mode!r}")
  return RemoteProjectionSettings(
    host=host,
    port=port,
    insecure=_env_bool(environ, ENV_INSECURE, False),
    ca_cert=environ.get(ENV_CA_CERT, "").strip(),
    timeout_ms=_env_int(environ, ENV_TIMEOUT_MS, DEFAULT_TIMEOUT_MS, 1, MAX_TIMEOUT_MS),
    mode=mode,
  )


def _proto_modules():
  from scenescape_api.projection.v1 import projection_pb2, projection_pb2_grpc
  return projection_pb2, projection_pb2_grpc


class GrpcProjectionClient:
  """Sends ProjectDetections requests concurrently; each call has the configured deadline."""

  def __init__(self, settings, channel=None):
    import grpc
    self._grpc = grpc
    _, projection_pb2_grpc = _proto_modules()
    if channel is None:
      channel = self.createChannel(settings)
    self._stub = projection_pb2_grpc.ProjectionServiceStub(channel)
    self._timeout_s = settings.timeout_ms / 1000.0

  @staticmethod
  def createChannel(settings):
    """TLS channel verified with ca_cert (or the system roots); plaintext when insecure.

    HTTP proxies are not used. Connects lazily.
    @raises OSError if ca_cert cannot be read
    """
    import grpc
    target = f"{settings.host}:{settings.port}"
    options = [("grpc.enable_http_proxy", 0)]
    if settings.insecure:
      return grpc.insecure_channel(target, options=options)
    root_certificates = None
    if settings.ca_cert:
      with open(settings.ca_cert, "rb") as ca_file:
        root_certificates = ca_file.read()
    credentials = grpc.ssl_channel_credentials(root_certificates=root_certificates)
    return grpc.secure_channel(target, credentials, options=options)

  def project(self, requests):
    """Return one (response, error) per request; error is the gRPC status name or ''."""
    futures = [self._stub.ProjectDetections.future(request, timeout=self._timeout_s)
               for request in requests]
    replies = []
    for future in futures:
      try:
        replies.append((future.result(), ""))
      except self._grpc.RpcError as error:
        replies.append((None, error.code().name))
    return replies


def _pixel_box(sscape_object):
  """Pixel box (x, y, width, height) of a camera detection the service can project, else None."""
  if getattr(sscape_object, 'has_measured_z', False):
    return None
  if not isinstance(getattr(sscape_object, 'camera', None), Camera):
    return None
  box = getattr(sscape_object, 'boundingBoxPixels', None)
  if box is None:
    return None
  values = (box.x, box.y, box.width, box.height)
  if not all(math.isfinite(value) for value in values) or box.width < 0 or box.height < 0:
    return None
  return values


class RemoteProjector:
  """Projects camera detections with the remote projection service; shared by all scenes."""

  def __init__(self, client, mode=DEFAULT_MODE, timeout_ms=DEFAULT_TIMEOUT_MS):
    self._client = client
    self.timeout_ms = timeout_ms  # the client's call deadline, for configuration checks
    projection_pb2, _ = _proto_modules()
    self._pb = projection_pb2
    self._mode = {
      "auto": projection_pb2.CONDITIONING_MODE_AUTO,
      "full": projection_pb2.CONDITIONING_MODE_FULL,
      "frustum_only": projection_pb2.CONDITIONING_MODE_FRUSTUM_ONLY,
    }[mode]
    self._warning_lock = threading.Lock()
    self._warnings = {}

  def project(self, scene_id, objects_per_camera, rv_objects_per_camera):
    """Replace the local projection of rv_objects_per_camera with valid remote measurements.

    rv_objects_per_camera holds the robot_vision inputs of objects_per_camera, in the same
    layout; objects without a valid remote measurement are left unchanged.
    """
    frames = self._buildFrames(scene_id, objects_per_camera)
    if not frames:
      return
    replies = self._call(scene_id, [request for request, _, _ in frames.values()])
    for (camera_id, (request, indices, category)), (response, error) in \
        zip(frames.items(), replies):
      self._applyReply(scene_id, category, camera_id, request, indices, response, error,
                       rv_objects_per_camera)

  def _buildFrames(self, scene_id, objects_per_camera):
    """One request per camera: {camera_id: (request, [(i, j) per detection], category)}."""
    frames = {}
    for i, objects in enumerate(objects_per_camera):
      for j, sscape_object in enumerate(objects):
        box = _pixel_box(sscape_object)
        if box is None:
          continue
        camera_id = sscape_object.camera.cameraID
        if camera_id not in frames:
          frames[camera_id] = (self._newRequest(scene_id, camera_id, sscape_object.first_seen),
                               [], sscape_object.category)
        request, indices, _ = frames[camera_id]
        detection = request.detections.add(detection_id=str(len(indices)),
                                           category=sscape_object.category)
        detection.bounding_box_px.x, detection.bounding_box_px.y, \
          detection.bounding_box_px.width, detection.bounding_box_px.height = box
        indices.append((i, j))
    return frames

  def _call(self, scene_id, requests):
    """One (response, error) per request; client errors become failed replies."""
    try:
      replies = self._client.project(requests)
    except Exception as error:  # never raise into the tracker thread
      log.debug(f"Remote projection client error for scene {scene_id}: {error}")
      return [(None, REASON_CLIENT_ERROR)] * len(requests)
    if len(replies) != len(requests):
      return [(None, REASON_INVALID_RESPONSE)] * len(requests)
    return replies

  def _newRequest(self, scene_id, camera_id, when):
    request = self._pb.ProjectDetectionsRequest(scene_id=scene_id, camera_id=camera_id,
                                                mode=self._mode)
    # Split before scaling: epoch seconds * 1e9 exceeds the float64 integer precision.
    seconds = math.floor(when)
    nanos = int(round((when - seconds) * 1e9))
    if nanos >= 1_000_000_000:
      seconds, nanos = seconds + 1, nanos - 1_000_000_000
    request.timestamp.seconds = int(seconds)
    request.timestamp.nanos = nanos
    return request

  def _applyReply(self, scene_id, category, camera_id, request, indices, response, error,
                  rv_objects_per_camera):
    if error:
      self._reportFailure(scene_id, category, camera_id, error)
      return
    measurements = response.measurements
    if len(measurements) != len(request.detections) or \
       any(m.detection_id != str(k) for k, m in enumerate(measurements)):
      self._reportFailure(scene_id, category, camera_id, REASON_INVALID_RESPONSE)
      return
    ok_status = self._pb.MEASUREMENT_STATUS_OK
    unobservable_status = self._pb.MEASUREMENT_STATUS_DEPTH_UNOBSERVABLE
    invalid = False
    for (i, j), detection_measurement in zip(indices, measurements):
      if detection_measurement.status == unobservable_status:
        continue  # depth unobservable: keep the local projection
      # OK without a measurement, UNSPECIFIED and unknown statuses break the contract.
      if detection_measurement.status != ok_status or \
         not detection_measurement.HasField('measurement') or \
         not apply_measurement(rv_objects_per_camera[i][j], detection_measurement.measurement):
        invalid = True
    if invalid:
      self._reportFailure(scene_id, category, camera_id, REASON_INVALID_MEASUREMENT)

  def _reportFailure(self, scene_id, category, camera_id, reason):
    metrics.inc_remote_projection_failed_calls(
      {"scene": scene_id, "category": category, "camera": camera_id, "reason": reason})
    key = (scene_id, category)
    now = time.monotonic()
    with self._warning_lock:
      last, suppressed = self._warnings.get(key, (None, 0))
      if last is not None and now - last < WARNING_INTERVAL_S:
        self._warnings[key] = (last, suppressed + 1)
        return
      self._warnings[key] = (now, 0)
    more = f" ({suppressed} more failures since the previous warning)" if suppressed else ""
    log.warning(f"Remote projection failed for scene {scene_id}, category {category}, "
                f"camera '{camera_id}' ({reason}); using local projection{more}")


class SceneProjection:
  """The process-wide RemoteProjector bound to one scene."""

  def __init__(self, projector, scene_id):
    self._projector = projector
    self.scene_id = scene_id

  def project(self, objects_per_camera, rv_objects_per_camera):
    self._projector.project(self.scene_id, objects_per_camera, rv_objects_per_camera)


def apply_measurement(rv_object, measurement):
  """Set a remote measurement (projection.v1 Measurement) on a robot_vision TrackedObject.

  Requires a finite 7-value mean with a positive size and 49 R values; the tracker's
  measurement_noise_covariance setter symmetrizes R and rejects it unless finite and positive
  definite. The centre z is lowered by half the height, to the object base used by the tracker.
  @return False, leaving the object unchanged, for an invalid measurement
  """
  mean = tuple(measurement.mean)
  covariance_size = MEASUREMENT_SIZE * MEASUREMENT_SIZE
  if len(mean) != MEASUREMENT_SIZE or len(measurement.noise_covariance) != covariance_size:
    return False
  if not all(map(math.isfinite, mean)) or not (mean[3] > 0.0 and mean[4] > 0.0 and mean[5] > 0.0):
    return False
  covariance = np.fromiter(measurement.noise_covariance, float, covariance_size)
  try:
    rv_object.measurement_noise_covariance = covariance.reshape(MEASUREMENT_SIZE, MEASUREMENT_SIZE)
  except ValueError:
    return False
  rv_object.x = mean[0]
  rv_object.y = mean[1]
  rv_object.z = mean[2] - mean[5] / 2.0
  rv_object.length = mean[3]
  rv_object.width = mean[4]
  rv_object.height = mean[5]
  rv_object.zMeasured = True
  return True


_state_lock = threading.Lock()
_projector = None
_configured = False


def _create_projector():
  try:
    settings = settings_from_env()
  except ValueError as error:
    log.error(f"Experimental remote projection disabled, using local projection: {error}")
    return None
  if settings is None:
    return None
  try:
    projector = RemoteProjector(GrpcProjectionClient(settings), settings.mode, settings.timeout_ms)
  except (OSError, ImportError) as error:
    log.error(f"Experimental remote projection disabled, using local projection: {error}")
    return None
  log.info(f"Experimental remote projection enabled: {settings.host}:{settings.port} "
           f"(mode={settings.mode}, timeout={settings.timeout_ms}ms, tls={not settings.insecure})")
  return projector


def get_projector():
  """Process-wide RemoteProjector, created from the environment on first use; None if disabled."""
  global _projector, _configured
  with _state_lock:
    if not _configured:
      _projector = _create_projector()
      _configured = True
    return _projector


def reset():
  """Forget the process-wide projector, so that the next get_projector() reads the environment."""
  global _projector, _configured
  with _state_lock:
    _projector = None
    _configured = False


def for_scene(scene_id, chunking_rate_fps=None):
  """SceneProjection for a scene UID, or None when remote projection is disabled.

  Warns when the call deadline exceeds the time-chunking interval of the scene
  (chunking_rate_fps; None when the scene does not use time chunking).
  """
  if not scene_id:
    return None
  projector = get_projector()
  if projector is None:
    return None
  if chunking_rate_fps and projector.timeout_ms > 1000.0 / chunking_rate_fps:
    log.warning(f"{ENV_TIMEOUT_MS}={projector.timeout_ms} exceeds the time-chunking interval "
                f"{1000.0 / chunking_rate_fps:.1f}ms of scene {scene_id} "
                f"({chunking_rate_fps} fps); a slow projection service delays tracking")
  return SceneProjection(projector, scene_id)
