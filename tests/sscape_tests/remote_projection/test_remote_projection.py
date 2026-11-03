# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for experimental remote projection in the scene controller."""

import math
import time
from concurrent import futures
from types import SimpleNamespace
from unittest.mock import Mock

import grpc
import numpy as np
import pytest

import robot_vision as rv
from scenescape_api.projection.v1 import projection_pb2 as pb
from scenescape_api.projection.v1 import projection_pb2_grpc as pb_grpc

from controller import remote_projection
from controller.ilabs_tracking import IntelLabsTracking, normalize_association_config
from controller.remote_projection import (GrpcProjectionClient, RemoteProjectionSettings,
                                          RemoteProjector, SceneProjection, apply_measurement,
                                          settings_from_env)
from controller.scene import Scene
from controller.tracking import Tracking
from scene_common.camera import Camera
from scene_common.geometry import Point

HEIGHT = 1.7
NOISE = np.diag([0.04, 0.04, 0.25, 0.2, 0.2, 0.2, 0.2])
WHEN = 1_700_000_000.25
LOCAL_X = -1.0


def make_camera(camera_id="cam-1"):
  camera = Camera.__new__(Camera)
  camera.cameraID = camera_id
  return camera


def make_object(camera, box=(10.0, 20.0, 30.0, 60.0), category="person", measured_z=False):
  return SimpleNamespace(
    camera=camera,
    boundingBoxPixels=SimpleNamespace(x=box[0], y=box[1], width=box[2], height=box[3]),
    category=category,
    first_seen=WHEN,
    has_measured_z=measured_z,
  )


def good_response(request):
  """Measurement k: centre (10 + k, 20 + k, HEIGHT / 2), size 0.5 x 0.6 x HEIGHT, R = NOISE."""
  response = pb.ProjectDetectionsResponse(scene_id=request.scene_id, camera_id=request.camera_id,
                                          mode=pb.CONDITIONING_MODE_FRUSTUM_ONLY)
  for k, detection in enumerate(request.detections):
    out = response.measurements.add(detection_id=detection.detection_id,
                                    status=pb.MEASUREMENT_STATUS_OK)
    out.measurement.mean.extend([10.0 + k, 20.0 + k, HEIGHT / 2.0, 0.5, 0.6, HEIGHT, 0.0])
    out.measurement.noise_covariance.extend(NOISE.flatten())
  return response


class FakeClient:
  def __init__(self, reply=None):
    self.reply = reply or (lambda request: (good_response(request), ""))
    self.requests = []
    self.error = None
    self.drop_last_reply = False

  def project(self, requests):
    self.requests.extend(requests)
    if self.error:
      raise self.error
    replies = [self.reply(request) for request in requests]
    return replies[:-1] if self.drop_last_reply else replies


@pytest.fixture
def failures(monkeypatch):
  """Captured failed-call metric attributes and warnings."""
  captured = SimpleNamespace(metrics=[], warnings=[])
  monkeypatch.setattr(remote_projection.metrics, "inc_remote_projection_failed_calls",
                      lambda attributes=None: captured.metrics.append(attributes))
  monkeypatch.setattr(remote_projection.log, "warning",
                      lambda *args: captured.warnings.append(" ".join(map(str, args))))
  return captured


def local_rv_objects(objects_per_camera):
  """robot_vision inputs as left by the local projection (x = LOCAL_X), in the same layout."""
  rv_objects_per_camera = []
  for objects in objects_per_camera:
    rv_objects = []
    for _ in objects:
      rv_object = rv.tracking.TrackedObject()
      rv_object.x = LOCAL_X
      rv_objects.append(rv_object)
    rv_objects_per_camera.append(rv_objects)
  return rv_objects_per_camera


def project(projector, objects_per_camera):
  """Run the projector over local rv inputs; return them after remote projection."""
  rv_objects_per_camera = local_rv_objects(objects_per_camera)
  projector.project("scene-uid", objects_per_camera, rv_objects_per_camera)
  return rv_objects_per_camera


def assert_remote(rv_object, k):
  """Measurement k of good_response(), with the centre z lowered to the object base."""
  assert (rv_object.x, rv_object.y) == (10.0 + k, 20.0 + k)
  assert rv_object.z == pytest.approx(0.0)
  assert (rv_object.length, rv_object.width, rv_object.height) == (0.5, 0.6, HEIGHT)
  assert rv_object.zMeasured is True
  np.testing.assert_allclose(np.array(rv_object.measurement_noise_covariance), NOISE)


def assert_local(rv_object):
  assert rv_object.x == LOCAL_X
  assert rv_object.zMeasured is False
  assert rv_object.measurement_noise_covariance is None


class TestRemoteProjector:

  def test_builds_one_request_per_camera_and_applies_measurements_in_layout(self, failures):
    client = FakeClient()
    projector = RemoteProjector(client, "auto")
    cam1, cam2 = make_camera("cam-1"), make_camera("cam-2")
    objects_per_camera = [[make_object(cam1), make_object(cam1, box=(1.5, 2.5, 3.5, 4.5))],
                          [make_object(cam2, category="person")]]

    rv_objects = project(projector, objects_per_camera)

    assert len(client.requests) == 2
    request = client.requests[0]
    assert request.scene_id == "scene-uid"
    assert request.camera_id == "cam-1"
    assert request.mode == pb.CONDITIONING_MODE_AUTO
    assert request.timestamp.seconds == 1_700_000_000
    assert request.timestamp.nanos == 250_000_000
    assert [d.detection_id for d in request.detections] == ["0", "1"]
    assert request.detections[1].category == "person"
    box = request.detections[1].bounding_box_px
    assert (box.x, box.y, box.width, box.height) == (1.5, 2.5, 3.5, 4.5)
    assert not request.detections[0].HasField("axis_aware_sizing")
    assert not request.detections[0].HasField("project_to_map")
    assert client.requests[1].camera_id == "cam-2"
    assert_remote(rv_objects[0][0], 0)
    assert_remote(rv_objects[0][1], 1)
    assert_remote(rv_objects[1][0], 0)
    assert not failures.metrics

  @pytest.mark.parametrize("when, seconds, nanos", [
    (1_700_000_000.25, 1_700_000_000, 250_000_000),
    (12.9999999999, 13, 0),
    (0.0, 0, 0),
  ])
  def test_converts_detection_time_exactly(self, when, seconds, nanos):
    client = FakeClient()
    sscape_object = make_object(make_camera())
    sscape_object.first_seen = when
    project(RemoteProjector(client), [[sscape_object]])
    assert client.requests[0].timestamp.seconds == seconds
    assert client.requests[0].timestamp.nanos == pytest.approx(nanos, abs=1)

  @pytest.mark.parametrize("mode, expected", [
    ("auto", pb.CONDITIONING_MODE_AUTO),
    ("full", pb.CONDITIONING_MODE_FULL),
    ("frustum_only", pb.CONDITIONING_MODE_FRUSTUM_ONLY),
  ])
  def test_requests_configured_mode(self, mode, expected):
    client = FakeClient()
    project(RemoteProjector(client, mode), [[make_object(make_camera())]])
    assert client.requests[0].mode == expected

  def test_sends_only_pixel_boxes_of_scene_cameras(self, failures):
    client = FakeClient()
    projector = RemoteProjector(client)
    camera = make_camera()
    no_box = make_object(camera)
    no_box.boundingBoxPixels = None
    external_source = make_object(SimpleNamespace(cameraID="drone-1"))
    objects = [
      make_object(camera, measured_z=True),
      external_source,
      no_box,
      make_object(camera, box=(math.nan, 0.0, 1.0, 1.0)),
      make_object(camera, box=(0.0, 0.0, -1.0, 1.0)),
      make_object(camera),
    ]

    rv_objects = project(projector, [objects])

    assert len(client.requests) == 1
    assert len(client.requests[0].detections) == 1
    for rv_object in rv_objects[0][:5]:
      assert_local(rv_object)
    assert_remote(rv_objects[0][5], 0)

  def test_makes_no_call_without_sendable_detections(self):
    client = FakeClient()
    rv_objects = project(RemoteProjector(client),
                         [[make_object(make_camera(), measured_z=True)], []])
    assert client.requests == []
    assert_local(rv_objects[0][0])
    assert rv_objects[1] == []

  def test_failed_call_keeps_local_projection_counts_and_rate_limits_warnings(
      self, failures, monkeypatch):
    client = FakeClient(lambda request: (None, "UNAVAILABLE"))
    projector = RemoteProjector(client)
    objects = [[make_object(make_camera())]]
    now = [1000.0]
    monkeypatch.setattr(remote_projection.time, "monotonic", lambda: now[0])

    for _ in range(3):
      assert_local(project(projector, objects)[0][0])
    now[0] += remote_projection.WARNING_INTERVAL_S
    project(projector, objects)

    assert failures.metrics == [{"scene": "scene-uid", "category": "person", "camera": "cam-1",
                                 "reason": "UNAVAILABLE"}] * 4
    assert len(failures.warnings) == 2
    assert "camera 'cam-1' (UNAVAILABLE); using local projection" in failures.warnings[0]
    assert "2 more failures since the previous warning" in failures.warnings[1]

  def test_client_exception_keeps_local_projection(self, failures):
    client = FakeClient()
    client.error = RuntimeError("transport broke")
    rv_objects = project(RemoteProjector(client),
                         [[make_object(make_camera("cam-1"))], [make_object(make_camera("cam-2"))]])
    assert_local(rv_objects[0][0])
    assert_local(rv_objects[1][0])
    assert [m["reason"] for m in failures.metrics] == ["client_error"] * 2

  def test_missing_reply_keeps_local_projection(self, failures):
    client = FakeClient()
    client.drop_last_reply = True
    rv_objects = project(RemoteProjector(client),
                         [[make_object(make_camera("cam-1"))], [make_object(make_camera("cam-2"))]])
    assert_local(rv_objects[0][0])
    assert_local(rv_objects[1][0])
    assert [m["reason"] for m in failures.metrics] == ["invalid_response"] * 2

  @pytest.mark.parametrize("corrupt", [
    lambda response: response.measurements.pop(),
    lambda response: setattr(response.measurements[0], "detection_id", "1"),
  ], ids=["count", "detection_id"])
  def test_malformed_reply_keeps_local_projection(self, failures, corrupt):
    def reply(request):
      response = good_response(request)
      corrupt(response)
      return response, ""
    camera = make_camera()
    rv_objects = project(RemoteProjector(FakeClient(reply)),
                         [[make_object(camera), make_object(camera)]])
    assert_local(rv_objects[0][0])
    assert_local(rv_objects[0][1])
    assert [m["reason"] for m in failures.metrics] == ["invalid_response"]

  def test_unobservable_depth_keeps_local_projection_without_failure(self, failures):
    def reply(request):
      response = good_response(request)
      response.measurements[0].status = pb.MEASUREMENT_STATUS_DEPTH_UNOBSERVABLE
      response.measurements[0].ClearField("measurement")
      return response, ""
    camera = make_camera()
    rv_objects = project(RemoteProjector(FakeClient(reply)),
                         [[make_object(camera), make_object(camera)]])
    assert_local(rv_objects[0][0])
    assert_remote(rv_objects[0][1], 1)
    assert not failures.metrics

  @pytest.mark.parametrize("corrupt", [
    lambda m: m.ClearField("measurement"),
    lambda m: setattr(m, "status", pb.MEASUREMENT_STATUS_UNSPECIFIED),
    lambda m: setattr(m, "status", 7),
  ], ids=["ok_without_measurement", "unspecified", "unknown_status"])
  def test_malformed_status_keeps_local_projection_and_counts(self, failures, corrupt):
    def reply(request):
      response = good_response(request)
      corrupt(response.measurements[0])
      return response, ""
    camera = make_camera()
    rv_objects = project(RemoteProjector(FakeClient(reply)),
                         [[make_object(camera), make_object(camera)]])
    assert_local(rv_objects[0][0])
    assert_remote(rv_objects[0][1], 1)
    assert [m["reason"] for m in failures.metrics] == ["invalid_measurement"]

  @pytest.mark.parametrize("corrupt", [
    lambda m: m.mean.pop(),
    lambda m: m.noise_covariance.pop(),
    lambda m: m.mean.__setitem__(0, math.nan),
    lambda m: m.mean.__setitem__(5, 0.0),
    lambda m: m.mean.__setitem__(3, -0.5),
    lambda m: m.noise_covariance.__setitem__(1, math.inf),
    lambda m: m.noise_covariance.__setitem__(0, -0.04),
    lambda m: (m.noise_covariance.__setitem__(1, 1.0), m.noise_covariance.__setitem__(7, 1.0)),
  ], ids=["mean_size", "noise_size", "nan_mean", "zero_height", "negative_length", "inf_noise",
          "negative_variance", "indefinite"])
  def test_invalid_measurement_keeps_local_projection(self, failures, corrupt):
    def reply(request):
      response = good_response(request)
      corrupt(response.measurements[0].measurement)
      return response, ""
    camera = make_camera()
    rv_objects = project(RemoteProjector(FakeClient(reply)),
                         [[make_object(camera), make_object(camera)]])
    assert_local(rv_objects[0][0])
    assert_remote(rv_objects[0][1], 1)
    assert [m["reason"] for m in failures.metrics] == ["invalid_measurement"]

  def test_symmetrizes_noise_covariance(self):
    def reply(request):
      response = good_response(request)
      response.measurements[0].measurement.noise_covariance[1] = 0.010
      response.measurements[0].measurement.noise_covariance[7] = 0.012
      return response, ""
    rv_objects = project(RemoteProjector(FakeClient(reply)), [[make_object(make_camera())]])
    noise = np.array(rv_objects[0][0].measurement_noise_covariance)
    assert noise[0, 1] == pytest.approx(0.011)
    assert noise[1, 0] == pytest.approx(0.011)

  def test_scene_projection_binds_scene(self):
    client = FakeClient()
    scene_projection = SceneProjection(RemoteProjector(client), "scene-uid")
    objects_per_camera = [[make_object(make_camera())]]
    rv_objects = local_rv_objects(objects_per_camera)
    scene_projection.project(objects_per_camera, rv_objects)
    assert scene_projection.scene_id == "scene-uid"
    assert client.requests[0].scene_id == "scene-uid"
    assert_remote(rv_objects[0][0], 0)


def measurement_message(mean, noise):
  return pb.Measurement(mean=list(mean), noise_covariance=np.asarray(noise).flatten().tolist())


class TestApplyMeasurement:

  def test_sets_base_position_size_and_noise(self):
    rv_object = rv.tracking.TrackedObject()
    rv_object.yaw = 0.3
    mean = [1.0, 2.0, HEIGHT / 2.0, 0.5, 0.6, HEIGHT, 0.0]

    assert apply_measurement(rv_object, measurement_message(mean, NOISE))

    assert (rv_object.x, rv_object.y) == (1.0, 2.0)
    assert rv_object.z == pytest.approx(0.0)
    assert (rv_object.length, rv_object.width, rv_object.height) == (0.5, 0.6, HEIGHT)
    assert rv_object.zMeasured is True
    assert rv_object.yaw == pytest.approx(0.3)
    np.testing.assert_allclose(np.array(rv_object.measurement_noise_covariance), NOISE)

  @pytest.mark.parametrize("mean, noise", [
    ([1.0, 2.0, 0.85, 0.5, 0.6, HEIGHT, 0.0], -NOISE),
    ([1.0, 2.0, math.nan, 0.5, 0.6, HEIGHT, 0.0], NOISE),
    ([1.0, 2.0, 0.85, 0.5, 0.0, HEIGHT, 0.0], NOISE),
    ([1.0, 2.0, 0.85, 0.5, 0.6, HEIGHT], NOISE),
  ], ids=["rejected_noise", "nan_mean", "zero_width", "short_mean"])
  def test_invalid_measurement_leaves_object_unchanged(self, mean, noise):
    rv_object = rv.tracking.TrackedObject()
    rv_object.x = 7.0

    assert not apply_measurement(rv_object, measurement_message(mean, noise))

    assert rv_object.x == 7.0
    assert rv_object.zMeasured is False
    assert rv_object.measurement_noise_covariance is None


class TestSettingsFromEnv:

  def test_disabled_by_default(self):
    assert settings_from_env({}) is None
    assert settings_from_env({remote_projection.ENV_ENABLED: "false",
                              remote_projection.ENV_HOST: "projection",
                              remote_projection.ENV_PORT: "50051"}) is None

  @pytest.mark.parametrize("environ", [
    {},
    {remote_projection.ENV_HOST: "projection"},
    {remote_projection.ENV_PORT: "50051"},
  ])
  def test_enabled_without_endpoint_uses_local_projection(self, environ, monkeypatch):
    warnings = []
    monkeypatch.setattr(remote_projection.log, "warning", lambda *args: warnings.append(args))
    assert settings_from_env({remote_projection.ENV_ENABLED: "true", **environ}) is None
    assert warnings

  def test_reads_all_settings(self):
    settings = settings_from_env({
      remote_projection.ENV_ENABLED: "yes",
      remote_projection.ENV_HOST: "projection",
      remote_projection.ENV_PORT: "6000",
      remote_projection.ENV_INSECURE: "true",
      remote_projection.ENV_CA_CERT: "/run/secrets/ca.pem",
      remote_projection.ENV_TIMEOUT_MS: "80",
      remote_projection.ENV_MODE: "FRUSTUM_ONLY",
    })
    assert settings == RemoteProjectionSettings(host="projection", port=6000, insecure=True,
                                                ca_cert="/run/secrets/ca.pem", timeout_ms=80,
                                                mode="frustum_only")

  def test_defaults(self):
    settings = settings_from_env({remote_projection.ENV_ENABLED: "1",
                                  remote_projection.ENV_HOST: "projection",
                                  remote_projection.ENV_PORT: "50051"})
    assert settings == RemoteProjectionSettings(host="projection", port=50051)
    assert settings.insecure is False
    assert settings.timeout_ms == remote_projection.DEFAULT_TIMEOUT_MS
    assert settings.mode == "auto"

  @pytest.mark.parametrize("name, value", [
    (remote_projection.ENV_ENABLED, "maybe"),
    (remote_projection.ENV_PORT, "0"),
    (remote_projection.ENV_PORT, "70000"),
    (remote_projection.ENV_PORT, "port"),
    (remote_projection.ENV_INSECURE, "sometimes"),
    (remote_projection.ENV_TIMEOUT_MS, "0"),
    (remote_projection.ENV_TIMEOUT_MS, "101"),
    (remote_projection.ENV_MODE, "amodal"),
  ])
  def test_invalid_values_raise(self, name, value):
    environ = {remote_projection.ENV_ENABLED: "true", remote_projection.ENV_HOST: "projection",
               remote_projection.ENV_PORT: "50051", name: value}
    with pytest.raises(ValueError):
      settings_from_env(environ)


class TestProcessProjector:

  @pytest.fixture(autouse=True)
  def clean_state(self, monkeypatch):
    for name in (remote_projection.ENV_ENABLED, remote_projection.ENV_HOST,
                 remote_projection.ENV_PORT, remote_projection.ENV_INSECURE,
                 remote_projection.ENV_CA_CERT, remote_projection.ENV_TIMEOUT_MS,
                 remote_projection.ENV_MODE):
      monkeypatch.delenv(name, raising=False)
    remote_projection.reset()
    yield
    remote_projection.reset()

  def enable(self, monkeypatch, **extra):
    monkeypatch.setenv(remote_projection.ENV_ENABLED, "true")
    monkeypatch.setenv(remote_projection.ENV_HOST, "127.0.0.1")
    monkeypatch.setenv(remote_projection.ENV_PORT, "50051")
    for name, value in extra.items():
      monkeypatch.setenv(name, value)

  def test_disabled_gives_no_scene_projection(self):
    assert remote_projection.get_projector() is None
    assert remote_projection.for_scene("scene-uid") is None

  def test_enabled_shares_one_projector_across_scenes(self, monkeypatch):
    self.enable(monkeypatch, **{remote_projection.ENV_INSECURE: "true"})

    first = remote_projection.for_scene("scene-1")
    second = remote_projection.for_scene("scene-2")

    assert isinstance(first, SceneProjection)
    assert first.scene_id == "scene-1"
    assert second._projector is first._projector
    assert remote_projection.get_projector() is first._projector

  def test_scene_without_uid_has_no_projection(self, monkeypatch):
    self.enable(monkeypatch, **{remote_projection.ENV_INSECURE: "true"})
    assert remote_projection.for_scene(None) is None
    assert remote_projection.for_scene("") is None

  @pytest.mark.parametrize("chunking_rate_fps, warns", [(15, True), (10, False), (None, False)])
  def test_warns_when_timeout_exceeds_chunk_interval(self, monkeypatch, chunking_rate_fps, warns):
    warnings = []
    monkeypatch.setattr(remote_projection.log, "warning", lambda *args: warnings.append(args))
    self.enable(monkeypatch, **{remote_projection.ENV_INSECURE: "true",
                                remote_projection.ENV_TIMEOUT_MS: "80"})

    assert remote_projection.for_scene("scene-uid", chunking_rate_fps) is not None

    assert bool(warnings) == warns
    if warns:
      assert "exceeds the time-chunking interval 66.7ms" in warnings[0][0]

  def test_reset_reads_the_environment_again(self, monkeypatch):
    assert remote_projection.get_projector() is None
    self.enable(monkeypatch, **{remote_projection.ENV_INSECURE: "true"})
    assert remote_projection.get_projector() is None
    remote_projection.reset()
    assert remote_projection.get_projector() is not None

  @pytest.mark.parametrize("extra", [
    {remote_projection.ENV_PORT: "port"},
    {remote_projection.ENV_CA_CERT: "/nonexistent/ca.pem"},
  ], ids=["invalid_setting", "unreadable_ca"])
  def test_configuration_errors_disable_remote_projection(self, monkeypatch, extra):
    errors = []
    monkeypatch.setattr(remote_projection.log, "error", lambda *args: errors.append(args))
    self.enable(monkeypatch, **extra)
    assert remote_projection.get_projector() is None
    assert errors


class FakeProjectionService(pb_grpc.ProjectionServiceServicer):
  def __init__(self):
    self.delay_s = 0.0

  def ProjectDetections(self, request, context):
    if self.delay_s:
      time.sleep(self.delay_s)
    if request.camera_id == "uncalibrated":
      context.abort(grpc.StatusCode.FAILED_PRECONDITION, "camera is not calibrated")
    return good_response(request)


class TestGrpcProjectionClient:

  @pytest.fixture
  def service(self):
    servicer = FakeProjectionService()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    pb_grpc.add_ProjectionServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    yield servicer, port
    server.stop(grace=None)

  @staticmethod
  def request(camera_id):
    request = pb.ProjectDetectionsRequest(scene_id="scene-uid", camera_id=camera_id)
    request.detections.add(detection_id="0", category="person").bounding_box_px.width = 10.0
    return request

  def test_returns_responses_and_status_names_in_request_order(self, service):
    _, port = service
    client = GrpcProjectionClient(RemoteProjectionSettings(host="127.0.0.1", port=port,
                                                           insecure=True, timeout_ms=5000))

    replies = client.project([self.request("cam-1"), self.request("uncalibrated"),
                              self.request("cam-2")])

    assert [error for _, error in replies] == ["", "FAILED_PRECONDITION", ""]
    assert replies[0][0].camera_id == "cam-1"
    assert replies[1][0] is None
    assert replies[2][0].measurements[0].measurement.mean[2] == pytest.approx(HEIGHT / 2.0)

  def test_calls_run_concurrently_under_the_deadline(self, service):
    servicer, port = service
    servicer.delay_s = 0.3
    client = GrpcProjectionClient(RemoteProjectionSettings(host="127.0.0.1", port=port,
                                                           insecure=True, timeout_ms=50))

    start = time.monotonic()
    replies = client.project([self.request("cam-1"), self.request("cam-2")])

    assert [error for _, error in replies] == ["DEADLINE_EXCEEDED"] * 2
    assert time.monotonic() - start < 0.25

  def test_unreachable_service_is_unavailable(self):
    client = GrpcProjectionClient(RemoteProjectionSettings(host="127.0.0.1", port=1,
                                                           insecure=True, timeout_ms=2000))
    assert client.project([self.request("cam-1")]) == [(None, "UNAVAILABLE")]

  def test_creates_tls_channels(self, tmp_path):
    ca_cert = tmp_path / "ca.pem"
    ca_cert.write_bytes(b"-----BEGIN CERTIFICATE-----\n-----END CERTIFICATE-----\n")
    settings = RemoteProjectionSettings(host="projection", port=50051)
    assert GrpcProjectionClient.createChannel(settings) is not None
    assert GrpcProjectionClient.createChannel(
      RemoteProjectionSettings(host="projection", port=50051, ca_cert=str(ca_cert))) is not None

  def test_unreadable_ca_certificate_raises(self):
    with pytest.raises(OSError):
      GrpcProjectionClient(RemoteProjectionSettings(host="projection", port=50051,
                                                    ca_cert="/nonexistent/ca.pem"))


def tracker_with_projection(projection):
  tracker = IntelLabsTracking.__new__(IntelLabsTracking)
  tracker.association_config = normalize_association_config()
  tracker.tracker = Mock()
  tracker.remote_projection = projection
  return tracker


def detected_object(camera):
  sscape_object = make_object(camera)
  sscape_object.sceneLoc = Point(4.0, 5.0, 0.0)
  sscape_object.size = [0.4, 0.4, 1.5]
  sscape_object.rotation = [0.0, 0.0, 0.0, 1.0]
  sscape_object.confidence = 0.9
  sscape_object.metadata = {}
  sscape_object.has_detection_rotation = False
  return sscape_object


class TestTrackerIntegration:

  @staticmethod
  def projection(unobservable_camera):
    """Scene projection with good replies, except unobservable depth for one camera."""
    def reply(request):
      response = good_response(request)
      if request.camera_id == unobservable_camera:
        response.measurements[-1].status = pb.MEASUREMENT_STATUS_DEPTH_UNOBSERVABLE
        response.measurements[-1].ClearField("measurement")
      return response, ""
    return SceneProjection(RemoteProjector(FakeClient(reply)), "scene-uid")

  def test_update_tracks_uses_remote_measurements(self):
    camera = make_camera()
    objects = [detected_object(camera), detected_object(camera)]
    tracker = tracker_with_projection(self.projection(unobservable_camera="cam-1"))

    tracker.update_tracks(objects, WHEN)

    rv_objects = tracker.tracker.track.call_args.args[0]
    assert (rv_objects[0].x, rv_objects[0].y, rv_objects[0].z) == (10.0, 20.0, pytest.approx(0.0))
    assert rv_objects[0].zMeasured is True
    assert rv_objects[0].measurement_noise_covariance is not None
    assert (rv_objects[1].x, rv_objects[1].y) == (4.0, 5.0)
    assert rv_objects[1].zMeasured is False
    assert rv_objects[1].measurement_noise_covariance is None

  def test_update_tracks_batched_uses_remote_measurements(self):
    objects_per_camera = [[detected_object(make_camera("cam-1"))],
                          [detected_object(make_camera("cam-2"))]]
    tracker = tracker_with_projection(self.projection(unobservable_camera="cam-1"))

    tracker.update_tracks_batched(objects_per_camera, WHEN)

    rv_objects_per_camera = tracker.tracker.track.call_args.args[0]
    assert rv_objects_per_camera[0][0].x == 4.0
    assert rv_objects_per_camera[0][0].measurement_noise_covariance is None
    assert rv_objects_per_camera[1][0].x == 10.0
    assert rv_objects_per_camera[1][0].measurement_noise_covariance is not None

  @pytest.mark.parametrize("batched", [False, True])
  def test_without_remote_projection_uses_local_projection(self, batched):
    objects = [detected_object(make_camera())]
    tracker = tracker_with_projection(None)

    if batched:
      tracker.update_tracks_batched([objects], WHEN)
      rv_object = tracker.tracker.track.call_args.args[0][0][0]
    else:
      tracker.update_tracks(objects, WHEN)
      rv_object = tracker.tracker.track.call_args.args[0][0]

    assert (rv_object.x, rv_object.y, rv_object.z) == (4.0, 5.0, 0.0)
    assert rv_object.measurement_noise_covariance is None

  def test_category_trackers_inherit_scene_projection(self, monkeypatch):
    parent = IntelLabsTracking.__new__(IntelLabsTracking)
    parent.reid_config_data = {}
    parent.association_config = normalize_association_config()
    parent.trackers = {}
    parent.uuid_manager = SimpleNamespace(scene_id="scene")
    parent.remote_projection = SceneProjection(Mock(), "scene-uid")

    def fake_init(self, *args, **kwargs):
      self.uuid_manager = SimpleNamespace(scene_id=None)

    monkeypatch.setattr(IntelLabsTracking, "__init__", fake_init)
    monkeypatch.setattr(IntelLabsTracking, "start", lambda self: None)
    Tracking._createTrackers(parent, ["person"], 1.0, 0.8, 1.6, 10)

    assert parent.trackers["person"].remote_projection is parent.remote_projection

  def test_scene_binds_projection_with_its_uid(self, monkeypatch):
    bound = []
    monkeypatch.setattr(remote_projection, "for_scene",
                        lambda scene_id, chunking_rate_fps=None:
                        bound.append((scene_id, chunking_rate_fps)) or f"projection:{scene_id}")
    scene = Scene.__new__(Scene)
    scene.tracker = SimpleNamespace()
    scene.time_chunking_rate_fps = 15

    scene._bindRemoteProjection()
    assert scene.tracker.remote_projection == "projection:None"

    scene.uid = "scene-uid"
    scene._bindRemoteProjection()
    assert scene.tracker.remote_projection == "projection:scene-uid"

    scene.trackerType = "time_chunked_intel_labs"
    scene._bindRemoteProjection()
    assert bound == [(None, None), ("scene-uid", None), ("scene-uid", 15)]
