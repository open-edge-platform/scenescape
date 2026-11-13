# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for experimental observation processor in the scene controller."""

import math
import threading
import time
from concurrent import futures
from types import SimpleNamespace
from unittest.mock import Mock

import grpc
import numpy as np
import pytest

import robot_vision as rv
from scenescape_api.observation_processor.v1 import observation_processor_pb2 as pb
from scenescape_api.observation_processor.v1 import observation_processor_pb2_grpc as pb_grpc

from controller import observation_processor
from controller.ilabs_tracking import IntelLabsTracking, normalize_association_config
from controller.moving_object import MovingObject
from controller.observation_processor import (GrpcObservationProcessorClient,
                                              RemoteObservationProcessor,
                                              RemoteObservationProcessorSettings,
                                              SceneObservationProcessor, apply_measurement,
                                              settings_from_env)
from controller.scene import Scene
from controller.tracking import (MAX_UNRELIABLE_TIME, NON_MEASUREMENT_TIME_DYNAMIC,
                                 NON_MEASUREMENT_TIME_STATIC, Tracking)
from scene_common.camera import Camera
from scene_common.geometry import Point

HEIGHT = 1.7
# Dense SPD R: position cross terms plus x-length, y-width, z-height and length-yaw terms.
NOISE = np.array([
  [0.040, 0.015, -0.008, 0.002, 0.000, 0.000, 0.000],
  [0.015, 0.040, -0.006, 0.000, 0.001, 0.000, 0.000],
  [-0.008, -0.006, 0.250, 0.000, 0.000, -0.030, 0.000],
  [0.002, 0.000, 0.000, 0.200, 0.000, 0.000, 0.010],
  [0.000, 0.001, 0.000, 0.000, 0.200, 0.000, 0.000],
  [0.000, 0.000, -0.030, 0.000, 0.000, 0.200, 0.000],
  [0.000, 0.000, 0.000, 0.010, 0.000, 0.000, 0.200],
])
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
    metric_distance=None,
  )


def good_response(request):
  """Measurement k: centre (10 + k, 20 + k, HEIGHT / 2), size 0.5 x 0.6 x HEIGHT, R = NOISE."""
  response = pb.ProcessDetectionsResponse(scene_id=request.scene_id, camera_id=request.camera_id,
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

  def process(self, requests):
    self.requests.extend(requests)
    if self.error:
      raise self.error
    replies = [self.reply(request) for request in requests]
    return replies[:-1] if self.drop_last_reply else replies


@pytest.fixture
def failures(monkeypatch):
  """Captured failed-call metric attributes and warnings."""
  captured = SimpleNamespace(metrics=[], warnings=[])
  monkeypatch.setattr(observation_processor.metrics, "inc_observation_processor_failed_calls",
                      lambda attributes=None: captured.metrics.append(attributes))
  monkeypatch.setattr(observation_processor.log, "warning",
                      lambda *args: captured.warnings.append(" ".join(map(str, args))))
  return captured


def local_rv_objects(objects_per_camera):
  """robot_vision inputs as left by the local processing (x = LOCAL_X), in the same layout."""
  rv_objects_per_camera = []
  for objects in objects_per_camera:
    rv_objects = []
    for _ in objects:
      rv_object = rv.tracking.TrackedObject()
      rv_object.x = LOCAL_X
      rv_objects.append(rv_object)
    rv_objects_per_camera.append(rv_objects)
  return rv_objects_per_camera


def process(processor, objects_per_camera):
  """Run the processor over local rv inputs; return them after observation processing."""
  rv_objects_per_camera = local_rv_objects(objects_per_camera)
  processor.process("scene-uid", objects_per_camera, rv_objects_per_camera)
  return rv_objects_per_camera


def assert_remote(rv_object, k):
  """Measurement k of good_response(), with the centre-of-mass z as received."""
  assert (rv_object.x, rv_object.y) == (10.0 + k, 20.0 + k)
  assert rv_object.z == HEIGHT / 2.0
  assert (rv_object.length, rv_object.width, rv_object.height) == (0.5, 0.6, HEIGHT)
  assert rv_object.z_measured is True
  np.testing.assert_array_equal(np.array(rv_object.measurement_noise_covariance), NOISE)


def assert_local(rv_object):
  assert rv_object.x == LOCAL_X
  assert rv_object.z_measured is False
  assert rv_object.measurement_noise_covariance is None


class TestRemoteObservationProcessor:

  def test_builds_one_request_per_camera_and_applies_measurements_in_layout(self, failures):
    client = FakeClient()
    processor = RemoteObservationProcessor(client, "auto")
    cam1, cam2 = make_camera("cam-1"), make_camera("cam-2")
    objects_per_camera = [[make_object(cam1), make_object(cam1, box=(1.5, 2.5, 3.5, 4.5))],
                          [make_object(cam2, category="person")]]

    rv_objects = process(processor, objects_per_camera)

    assert len(client.requests) == 2
    request = client.requests[0]
    assert request.scene_id == "scene-uid"
    assert request.camera_id == "cam-1"
    assert request.mode == pb.CONDITIONING_MODE_AUTO
    assert not request.include_diagnostics
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
    process(RemoteObservationProcessor(client), [[sscape_object]])
    assert client.requests[0].timestamp.seconds == seconds
    assert client.requests[0].timestamp.nanos == pytest.approx(nanos, abs=1)

  @pytest.mark.parametrize("mode, expected", [
    ("auto", pb.CONDITIONING_MODE_AUTO),
    ("full", pb.CONDITIONING_MODE_FULL),
    ("frustum_only", pb.CONDITIONING_MODE_FRUSTUM_ONLY),
  ])
  def test_requests_configured_mode(self, mode, expected):
    client = FakeClient()
    process(RemoteObservationProcessor(client, mode), [[make_object(make_camera())]])
    assert client.requests[0].mode == expected

  def test_sends_only_pixel_boxes_of_scene_cameras(self, failures):
    client = FakeClient()
    processor = RemoteObservationProcessor(client)
    camera = make_camera()
    no_box = make_object(camera)
    no_box.boundingBoxPixels = None
    external_source = make_object(SimpleNamespace(cameraID="drone-1"))
    depth_box = make_object(camera)
    depth_box.metric_distance = 2.0  # sensor-measured depth: keeps the local depth placement
    objects = [
      make_object(camera, measured_z=True),
      external_source,
      no_box,
      make_object(camera, box=(math.nan, 0.0, 1.0, 1.0)),
      make_object(camera, box=(0.0, 0.0, -1.0, 1.0)),
      depth_box,
      make_object(camera),
    ]

    rv_objects = process(processor, [objects])

    assert len(client.requests) == 1
    assert len(client.requests[0].detections) == 1
    for rv_object in rv_objects[0][:6]:
      assert_local(rv_object)
    assert_remote(rv_objects[0][6], 0)

  def test_makes_no_call_without_sendable_detections(self):
    client = FakeClient()
    rv_objects = process(RemoteObservationProcessor(client),
                         [[make_object(make_camera(), measured_z=True)], []])
    assert client.requests == []
    assert_local(rv_objects[0][0])
    assert rv_objects[1] == []

  def test_failed_call_keeps_local_processing_counts_and_rate_limits_warnings(
      self, failures, monkeypatch):
    client = FakeClient(lambda request: (None, "UNAVAILABLE"))
    processor = RemoteObservationProcessor(client)
    objects = [[make_object(make_camera())]]
    now = [1000.0]
    monkeypatch.setattr(observation_processor.time, "monotonic", lambda: now[0])

    for _ in range(3):
      assert_local(process(processor, objects)[0][0])
    now[0] += observation_processor.WARNING_INTERVAL_S
    process(processor, objects)

    assert failures.metrics == [{"scene": "scene-uid", "category": "person", "camera": "cam-1",
                                 "reason": "UNAVAILABLE"}] * 4
    assert len(failures.warnings) == 2
    assert "camera 'cam-1' (UNAVAILABLE); using local processing" in failures.warnings[0]
    assert "2 more failures since the previous warning" in failures.warnings[1]

  def test_client_exception_keeps_local_processing(self, failures):
    client = FakeClient()
    client.error = RuntimeError("transport broke")
    rv_objects = process(RemoteObservationProcessor(client),
                         [[make_object(make_camera("cam-1"))], [make_object(make_camera("cam-2"))]])
    assert_local(rv_objects[0][0])
    assert_local(rv_objects[1][0])
    assert [m["reason"] for m in failures.metrics] == ["client_error"] * 2

  def test_missing_reply_keeps_local_processing(self, failures):
    client = FakeClient()
    client.drop_last_reply = True
    rv_objects = process(RemoteObservationProcessor(client),
                         [[make_object(make_camera("cam-1"))], [make_object(make_camera("cam-2"))]])
    assert_local(rv_objects[0][0])
    assert_local(rv_objects[1][0])
    assert [m["reason"] for m in failures.metrics] == ["invalid_response"] * 2

  @pytest.mark.parametrize("corrupt", [
    lambda response: response.measurements.pop(),
    lambda response: setattr(response.measurements[0], "detection_id", "1"),
  ], ids=["count", "detection_id"])
  def test_malformed_reply_keeps_local_processing(self, failures, corrupt):
    def reply(request):
      response = good_response(request)
      corrupt(response)
      return response, ""
    camera = make_camera()
    rv_objects = process(RemoteObservationProcessor(FakeClient(reply)),
                         [[make_object(camera), make_object(camera)]])
    assert_local(rv_objects[0][0])
    assert_local(rv_objects[0][1])
    assert [m["reason"] for m in failures.metrics] == ["invalid_response"]

  def test_unobservable_depth_keeps_local_processing_without_failure(self, failures):
    def reply(request):
      response = good_response(request)
      response.measurements[0].status = pb.MEASUREMENT_STATUS_DEPTH_UNOBSERVABLE
      response.measurements[0].ClearField("measurement")
      return response, ""
    camera = make_camera()
    rv_objects = process(RemoteObservationProcessor(FakeClient(reply)),
                         [[make_object(camera), make_object(camera)]])
    assert_local(rv_objects[0][0])
    assert_remote(rv_objects[0][1], 1)
    assert not failures.metrics

  @pytest.mark.parametrize("corrupt", [
    lambda m: m.ClearField("measurement"),
    lambda m: setattr(m, "status", pb.MEASUREMENT_STATUS_UNSPECIFIED),
    lambda m: setattr(m, "status", 7),
  ], ids=["ok_without_measurement", "unspecified", "unknown_status"])
  def test_malformed_status_keeps_local_processing_and_counts(self, failures, corrupt):
    def reply(request):
      response = good_response(request)
      corrupt(response.measurements[0])
      return response, ""
    camera = make_camera()
    rv_objects = process(RemoteObservationProcessor(FakeClient(reply)),
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
  def test_invalid_measurement_keeps_local_processing(self, failures, corrupt):
    def reply(request):
      response = good_response(request)
      corrupt(response.measurements[0].measurement)
      return response, ""
    camera = make_camera()
    rv_objects = process(RemoteObservationProcessor(FakeClient(reply)),
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
    rv_objects = process(RemoteObservationProcessor(FakeClient(reply)),
                         [[make_object(make_camera())]])
    noise = np.array(rv_objects[0][0].measurement_noise_covariance)
    assert noise[0, 1] == pytest.approx(0.011)
    assert noise[1, 0] == pytest.approx(0.011)
    assert (noise[2, 5], noise[6, 3]) == (NOISE[2, 5], NOISE[6, 3]), "other cross terms unchanged"

  def test_scene_processor_binds_scene(self):
    client = FakeClient()
    scene_processor = SceneObservationProcessor(RemoteObservationProcessor(client), "scene-uid")
    objects_per_camera = [[make_object(make_camera())]]
    rv_objects = local_rv_objects(objects_per_camera)
    scene_processor.process(objects_per_camera, rv_objects)
    assert scene_processor.scene_id == "scene-uid"
    assert client.requests[0].scene_id == "scene-uid"
    assert_remote(rv_objects[0][0], 0)


def measurement_message(mean, noise):
  return pb.Measurement(mean=list(mean), noise_covariance=np.asarray(noise).flatten().tolist())


class TestApplyMeasurement:

  def test_sets_centre_position_size_and_noise(self):
    rv_object = rv.tracking.TrackedObject()
    rv_object.yaw = 0.3
    mean = [1.0, 2.0, HEIGHT / 2.0, 0.5, 0.6, HEIGHT, 0.0]

    assert apply_measurement(rv_object, measurement_message(mean, NOISE))

    assert (rv_object.x, rv_object.y) == (1.0, 2.0)
    assert rv_object.z == HEIGHT / 2.0
    assert (rv_object.length, rv_object.width, rv_object.height) == (0.5, 0.6, HEIGHT)
    assert rv_object.z_measured is True
    assert rv_object.yaw == pytest.approx(0.3)
    np.testing.assert_array_equal(np.array(rv_object.measurement_noise_covariance), NOISE)

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
    assert rv_object.z_measured is False
    assert rv_object.measurement_noise_covariance is None


class TestSettingsFromEnv:

  def test_disabled_by_default(self):
    assert settings_from_env({}) is None
    assert settings_from_env({observation_processor.ENV_ENABLED: "false",
                              observation_processor.ENV_HOST: "processor",
                              observation_processor.ENV_PORT: "50051"}) is None

  @pytest.mark.parametrize("environ", [
    {},
    {observation_processor.ENV_HOST: "processor"},
    {observation_processor.ENV_PORT: "50051"},
  ])
  def test_enabled_without_endpoint_uses_local_processing(self, environ, monkeypatch):
    warnings = []
    monkeypatch.setattr(observation_processor.log, "warning", lambda *args: warnings.append(args))
    assert settings_from_env({observation_processor.ENV_ENABLED: "true", **environ}) is None
    assert warnings

  def test_reads_all_settings(self):
    settings = settings_from_env({
      observation_processor.ENV_ENABLED: "yes",
      observation_processor.ENV_HOST: "processor",
      observation_processor.ENV_PORT: "6000",
      observation_processor.ENV_INSECURE: "true",
      observation_processor.ENV_CA_CERT: "/run/secrets/ca.pem",
      observation_processor.ENV_TIMEOUT_MS: "80",
      observation_processor.ENV_MODE: "FRUSTUM_ONLY",
    })
    assert settings == RemoteObservationProcessorSettings(
      host="processor", port=6000, insecure=True, ca_cert="/run/secrets/ca.pem", timeout_ms=80,
      mode="frustum_only")

  def test_defaults(self):
    settings = settings_from_env({observation_processor.ENV_ENABLED: "1",
                                  observation_processor.ENV_HOST: "processor",
                                  observation_processor.ENV_PORT: "50051"})
    assert settings == RemoteObservationProcessorSettings(host="processor", port=50051)
    assert settings.insecure is False
    assert settings.timeout_ms == observation_processor.DEFAULT_TIMEOUT_MS
    assert settings.mode == "auto"

  @pytest.mark.parametrize("name, value", [
    (observation_processor.ENV_ENABLED, "maybe"),
    (observation_processor.ENV_PORT, "0"),
    (observation_processor.ENV_PORT, "70000"),
    (observation_processor.ENV_PORT, "port"),
    (observation_processor.ENV_INSECURE, "sometimes"),
    (observation_processor.ENV_TIMEOUT_MS, "0"),
    (observation_processor.ENV_TIMEOUT_MS, "101"),
    (observation_processor.ENV_MODE, "amodal"),
  ])
  def test_invalid_values_raise(self, name, value):
    environ = {observation_processor.ENV_ENABLED: "true",
               observation_processor.ENV_HOST: "processor",
               observation_processor.ENV_PORT: "50051", name: value}
    with pytest.raises(ValueError):
      settings_from_env(environ)


class TestProcessWideObservationProcessor:

  @pytest.fixture(autouse=True)
  def clean_state(self, monkeypatch):
    for name in (observation_processor.ENV_ENABLED, observation_processor.ENV_HOST,
                 observation_processor.ENV_PORT, observation_processor.ENV_INSECURE,
                 observation_processor.ENV_CA_CERT, observation_processor.ENV_TIMEOUT_MS,
                 observation_processor.ENV_MODE):
      monkeypatch.delenv(name, raising=False)
    observation_processor.reset()
    yield
    observation_processor.reset()

  def enable(self, monkeypatch, **extra):
    monkeypatch.setenv(observation_processor.ENV_ENABLED, "true")
    monkeypatch.setenv(observation_processor.ENV_HOST, "127.0.0.1")
    monkeypatch.setenv(observation_processor.ENV_PORT, "50051")
    for name, value in extra.items():
      monkeypatch.setenv(name, value)

  def test_disabled_gives_no_scene_processor(self):
    assert observation_processor.get_processor() is None
    assert observation_processor.for_scene("scene-uid") is None

  def test_enabled_shares_one_processor_across_scenes(self, monkeypatch):
    self.enable(monkeypatch, **{observation_processor.ENV_INSECURE: "true"})

    first = observation_processor.for_scene("scene-1")
    second = observation_processor.for_scene("scene-2")

    assert isinstance(first, SceneObservationProcessor)
    assert first.scene_id == "scene-1"
    assert second._processor is first._processor
    assert observation_processor.get_processor() is first._processor

  def test_scene_without_uid_has_no_processor(self, monkeypatch):
    self.enable(monkeypatch, **{observation_processor.ENV_INSECURE: "true"})
    assert observation_processor.for_scene(None) is None
    assert observation_processor.for_scene("") is None

  @pytest.mark.parametrize("chunking_rate_fps, warns", [(15, True), (10, False), (None, False)])
  def test_warns_when_timeout_exceeds_chunk_interval(self, monkeypatch, chunking_rate_fps, warns):
    warnings = []
    monkeypatch.setattr(observation_processor.log, "warning", lambda *args: warnings.append(args))
    self.enable(monkeypatch, **{observation_processor.ENV_INSECURE: "true",
                                observation_processor.ENV_TIMEOUT_MS: "80"})

    assert observation_processor.for_scene("scene-uid", chunking_rate_fps) is not None

    assert bool(warnings) == warns
    if warns:
      assert "exceeds the time-chunking interval 66.7ms" in warnings[0][0]

  def test_reset_reads_the_environment_again(self, monkeypatch):
    assert observation_processor.get_processor() is None
    self.enable(monkeypatch, **{observation_processor.ENV_INSECURE: "true"})
    assert observation_processor.get_processor() is None
    observation_processor.reset()
    assert observation_processor.get_processor() is not None

  @pytest.mark.parametrize("extra", [
    {observation_processor.ENV_PORT: "port"},
    {observation_processor.ENV_CA_CERT: "/nonexistent/ca.pem"},
  ], ids=["invalid_setting", "unreadable_ca"])
  def test_configuration_errors_disable_observation_processor(self, monkeypatch, extra):
    errors = []
    monkeypatch.setattr(observation_processor.log, "error", lambda *args: errors.append(args))
    self.enable(monkeypatch, **extra)
    assert observation_processor.get_processor() is None
    assert errors


class FakeObservationProcessorService(pb_grpc.ObservationProcessorServiceServicer):
  def __init__(self):
    self.delay_s = 0.0

  def ProcessDetections(self, request, context):
    if self.delay_s:
      time.sleep(self.delay_s)
    if request.camera_id == "uncalibrated":
      context.abort(grpc.StatusCode.FAILED_PRECONDITION, "camera is not calibrated")
    return good_response(request)


class TestGrpcObservationProcessorClient:

  @pytest.fixture
  def service(self):
    servicer = FakeObservationProcessorService()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    pb_grpc.add_ObservationProcessorServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    yield servicer, port
    server.stop(grace=None)

  @staticmethod
  def request(camera_id):
    request = pb.ProcessDetectionsRequest(scene_id="scene-uid", camera_id=camera_id)
    request.detections.add(detection_id="0", category="person").bounding_box_px.width = 10.0
    return request

  def test_returns_responses_and_status_names_in_request_order(self, service):
    _, port = service
    client = GrpcObservationProcessorClient(RemoteObservationProcessorSettings(
      host="127.0.0.1", port=port, insecure=True, timeout_ms=5000))

    replies = client.process([self.request("cam-1"), self.request("uncalibrated"),
                              self.request("cam-2")])

    assert [error for _, error in replies] == ["", "FAILED_PRECONDITION", ""]
    assert replies[0][0].camera_id == "cam-1"
    assert replies[1][0] is None
    assert replies[2][0].measurements[0].measurement.mean[2] == pytest.approx(HEIGHT / 2.0)
    assert list(replies[2][0].measurements[0].measurement.noise_covariance) == \
      NOISE.flatten().tolist(), "R arrives row-major with its cross terms"

  def test_calls_run_concurrently_under_the_deadline(self, service):
    servicer, port = service
    servicer.delay_s = 0.3
    client = GrpcObservationProcessorClient(RemoteObservationProcessorSettings(
      host="127.0.0.1", port=port, insecure=True, timeout_ms=50))

    start = time.monotonic()
    replies = client.process([self.request("cam-1"), self.request("cam-2")])

    assert [error for _, error in replies] == ["DEADLINE_EXCEEDED"] * 2
    assert time.monotonic() - start < 0.25

  def test_unreachable_service_is_unavailable(self):
    client = GrpcObservationProcessorClient(RemoteObservationProcessorSettings(
      host="127.0.0.1", port=1, insecure=True, timeout_ms=2000))
    assert client.process([self.request("cam-1")]) == [(None, "UNAVAILABLE")]

  def test_starts_connecting_its_own_channel(self, monkeypatch):
    started = []
    monkeypatch.setattr(grpc, "channel_ready_future", started.append)
    settings = RemoteObservationProcessorSettings(host="127.0.0.1", port=1, insecure=True)

    GrpcObservationProcessorClient(settings)
    assert len(started) == 1 and isinstance(started[0], grpc.Channel)

    GrpcObservationProcessorClient(settings, channel=grpc.insecure_channel("127.0.0.1:1"))
    assert len(started) == 1, "an injected channel is left as it is"

  def test_creates_tls_channels(self, tmp_path):
    ca_cert = tmp_path / "ca.pem"
    ca_cert.write_bytes(b"-----BEGIN CERTIFICATE-----\n-----END CERTIFICATE-----\n")
    settings = RemoteObservationProcessorSettings(host="processor", port=50051)
    assert GrpcObservationProcessorClient.createChannel(settings) is not None
    assert GrpcObservationProcessorClient.createChannel(
      RemoteObservationProcessorSettings(host="processor", port=50051,
                                         ca_cert=str(ca_cert))) is not None

  def test_unreadable_ca_certificate_raises(self):
    with pytest.raises(OSError):
      GrpcObservationProcessorClient(RemoteObservationProcessorSettings(
        host="processor", port=50051, ca_cert="/nonexistent/ca.pem"))


def tracker_with_processor(processor):
  tracker = IntelLabsTracking.__new__(IntelLabsTracking)
  tracker.association_config = normalize_association_config()
  tracker.tracker = Mock()
  tracker.observation_processor = processor
  return tracker


DETECTED_HEIGHT = 1.5
MEASURED_Z = 0.9

def detected_object(camera, z=0.0, measured_z=False):
  sscape_object = make_object(camera, measured_z=measured_z)
  sscape_object.sceneLoc = Point(4.0, 5.0, z)
  sscape_object.size = [0.4, 0.4, DETECTED_HEIGHT]
  sscape_object.rotation = [0.0, 0.0, 0.0, 1.0]
  sscape_object.confidence = 0.9
  sscape_object.metadata = {}
  sscape_object.has_detection_rotation = False
  return sscape_object


class TestTrackerIntegration:

  @staticmethod
  def processor(unobservable_camera):
    """Scene observation processor with good replies, except unobservable depth for one camera."""
    def reply(request):
      response = good_response(request)
      if request.camera_id == unobservable_camera:
        response.measurements[-1].status = pb.MEASUREMENT_STATUS_DEPTH_UNOBSERVABLE
        response.measurements[-1].ClearField("measurement")
      return response, ""
    return SceneObservationProcessor(RemoteObservationProcessor(FakeClient(reply)), "scene-uid")

  def test_update_tracks_uses_remote_measurements(self):
    camera = make_camera()
    objects = [detected_object(camera), detected_object(camera),
               detected_object(camera, z=MEASURED_Z, measured_z=True)]
    tracker = tracker_with_processor(self.processor(unobservable_camera="cam-1"))

    tracker.update_tracks(objects, WHEN)

    rv_objects = tracker.tracker.track.call_args.args[0]
    assert (rv_objects[0].x, rv_objects[0].y, rv_objects[0].z) == (10.0, 20.0, HEIGHT / 2.0)
    assert rv_objects[0].z_measured is True
    assert rv_objects[0].measurement_noise_covariance is not None
    assert (rv_objects[1].x, rv_objects[1].y) == (4.0, 5.0)
    assert rv_objects[1].z == DETECTED_HEIGHT / 2.0, "local base raised to the centre"
    assert rv_objects[1].z_measured is False
    assert rv_objects[1].measurement_noise_covariance is None
    assert rv_objects[2].z == MEASURED_Z, "measured z is already the centre"

  def test_update_tracks_batched_uses_remote_measurements(self):
    cam1, cam2 = make_camera("cam-1"), make_camera("cam-2")
    objects_per_camera = [
      [detected_object(cam1), detected_object(cam1, z=MEASURED_Z, measured_z=True)],
      [detected_object(cam2)],
    ]
    tracker = tracker_with_processor(self.processor(unobservable_camera="cam-1"))

    tracker.update_tracks_batched(objects_per_camera, WHEN)

    rv_objects_per_camera = tracker.tracker.track.call_args.args[0]
    assert rv_objects_per_camera[0][0].x == 4.0
    assert rv_objects_per_camera[0][0].z == DETECTED_HEIGHT / 2.0
    assert rv_objects_per_camera[0][0].measurement_noise_covariance is None
    assert rv_objects_per_camera[0][1].z == MEASURED_Z
    assert rv_objects_per_camera[1][0].x == 10.0
    assert rv_objects_per_camera[1][0].z == HEIGHT / 2.0
    assert rv_objects_per_camera[1][0].measurement_noise_covariance is not None

  @pytest.mark.parametrize("batched", [False, True])
  def test_without_observation_processor_uses_local_processing(self, batched):
    camera = make_camera()
    objects = [detected_object(camera), detected_object(camera, z=0.3),
               detected_object(camera, z=MEASURED_Z, measured_z=True)]
    tracker = tracker_with_processor(None)

    if batched:
      tracker.update_tracks_batched([objects], WHEN)
      rv_objects = tracker.tracker.track.call_args.args[0][0]
    else:
      tracker.update_tracks(objects, WHEN)
      rv_objects = tracker.tracker.track.call_args.args[0]

    assert (rv_objects[0].x, rv_objects[0].y) == (4.0, 5.0)
    assert [rv_object.z for rv_object in rv_objects] == [0.0, 0.3, MEASURED_Z]
    assert all(rv_object.measurement_noise_covariance is None for rv_object in rv_objects)

  @pytest.mark.parametrize("processor", [None, Mock()], ids=["legacy", "experimental"])
  def test_from_tracked_object_publishes_footprint_base_only_with_processor(self, processor):
    tracker = tracker_with_processor(processor)
    tracker.all_tracker_objects = []
    tracker.uuid_manager = Mock()
    sscape_object = detected_object(make_camera())
    sscape_object.uuid = "detection-uuid"
    sscape_object.location = [SimpleNamespace(point=None)]
    sscape_object.setGID = Mock()
    sscape_object.inferRotationFromVelocity = Mock()
    tracked = rv.tracking.TrackedObject()
    tracked.x, tracked.y, tracked.z, tracked.vz = 1.0, 2.0, 1.2, 0.3
    tracked.height = 1.8
    tracked.attributes = {"info": "detection-uuid"}

    published = tracker.from_tracked_object(tracked, [sscape_object])

    point = published.location[0].point
    assert (point.x, point.y) == (1.0, 2.0)
    assert point.z == (tracked.z if processor is None else tracked.z - tracked.height / 2)
    assert published.velocity.z == 0.3

  def test_category_trackers_inherit_scene_processor(self, monkeypatch):
    parent = IntelLabsTracking.__new__(IntelLabsTracking)
    parent.reid_config_data = {}
    parent.association_config = normalize_association_config()
    parent.trackers = {}
    parent._joined = False
    parent._lifecycle_lock = threading.Lock()
    parent.uuid_manager = SimpleNamespace(scene_id="scene")
    parent.observation_processor = SceneObservationProcessor(Mock(), "scene-uid")

    def fake_init(self, *args, **kwargs):
      self.uuid_manager = SimpleNamespace(scene_id=None)

    monkeypatch.setattr(IntelLabsTracking, "__init__", fake_init)
    monkeypatch.setattr(IntelLabsTracking, "start", lambda self: None)
    Tracking._createTrackers(parent, ["person"], 1.0, 0.8, 1.6, 10)

    assert parent.trackers["person"].observation_processor is parent.observation_processor

  def test_scene_binds_processor_with_its_uid(self, monkeypatch):
    bound = []
    monkeypatch.setattr(observation_processor, "for_scene",
                        lambda scene_id, chunking_rate_fps=None:
                        bound.append((scene_id, chunking_rate_fps)) or f"processor:{scene_id}")
    scene = Scene.__new__(Scene)
    scene.tracker = SimpleNamespace()
    scene.time_chunking_rate_fps = 15

    scene._bindObservationProcessor()
    assert scene.tracker.observation_processor == "processor:None"

    scene.uid = "scene-uid"
    scene._bindObservationProcessor()
    assert scene.tracker.observation_processor == "processor:scene-uid"

    scene.trackerType = "time_chunked_intel_labs"
    scene._bindObservationProcessor()
    assert bound == [(None, None), ("scene-uid", None), ("scene-uid", 15)]

  def test_scene_binds_processor_before_tracking_and_rebinds_new_tracker(self, monkeypatch):
    monkeypatch.setattr(observation_processor, "for_scene",
                        lambda scene_id, chunking_rate_fps=None:
                        f"processor:{scene_id}" if scene_id else None)

    scene = Scene.deserialize({"uid": "scene-uid", "name": "scene", "map": None,
                               "tracker_config": [1.0, 2.0, 3.0]})
    first_tracker = scene.tracker

    assert first_tracker.observation_processor == "processor:scene-uid"
    assert first_tracker.trackers == {}, "category trackers are created later and inherit it"

    scene._setTracker(scene.trackerType)

    assert scene.tracker is not first_tracker
    assert scene.tracker.observation_processor == "processor:scene-uid"


FPS = 15
FRAMES = 30 * FPS


def scene_camera(translation, rotation):
  return Camera("cam-1", {
    "intrinsics": {"fx": 905.0, "fy": 905.0, "cx": 640.0, "cy": 360.0},
    "translation": translation, "rotation": rotation, "scale": [1.0, 1.0, 1.0],
    "width": 1280, "height": 720,
  })


def planar_objects(heights):
  """Two pixel boxes moving along x, ending below the horizon; heights[n][k] is object k's."""
  camera = scene_camera([0.0, 0.0, 3.0], [-90.0, 0.0, 0.0])

  def make(n, when):
    return [MovingObject({"id": k + 1, "category": "person", "confidence": 0.9,
                          "bounding_box_px": {"x": 100.0 + 300.0 * k + 1.5 * n, "y": 400.0,
                                              "width": 55.0, "height": 150.0},
                          "size": [0.5, 0.5, heights[n][k]]}, when, camera)
            for k in range(2)]
  return make


def translation_objects(n, when):
  """World z 0.9 is the centre of a 1.8 m tall object (identity camera pose)."""
  camera = scene_camera([0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
  return [MovingObject({"id": 1, "category": "person", "confidence": 0.9,
                        "translation": [1.0, 2.0, 0.9], "size": [0.5, 0.5, 1.8]}, when, camera)]


def run_tracker(make_objects, experimental):
  """Track FRAMES frames with production robot_vision; return (rv_id, x, y, z, vz) per frame."""
  tracker = IntelLabsTracking(MAX_UNRELIABLE_TIME, NON_MEASUREMENT_TIME_DYNAMIC,
                              NON_MEASUREMENT_TIME_STATIC, FPS)
  tracker.uuid_manager.scene_id = "scene"
  # Experimental mode where every remote call falls back to the local processing.
  tracker.observation_processor = \
    SimpleNamespace(process=lambda *args: None) if experimental else None
  published = []
  for n in range(FRAMES):
    when = WHEN + n / FPS
    tracker.trackCategory(make_objects(n, when), when, [])
    published.append([(obj.rv_id, obj.location[0].point.x, obj.location[0].point.y,
                       obj.location[0].point.z, obj.velocity.z)
                      for obj in tracker.all_tracker_objects])
  tracker.uuid_manager.shutdown()
  return published


def published_values(published, index):
  return np.array([track[index] for frame in published for track in frame])


class TestZReferenceWithRobotVision:

  @pytest.mark.parametrize("experimental", [False, True], ids=["legacy", "experimental"])
  def test_planar_constant_height_publishes_ground_z(self, experimental):
    published = run_tracker(planar_objects(np.full((FRAMES, 2), 1.7)), experimental)

    assert published[-1], "no reliable tracks"
    assert np.abs(published_values(published, 3)).max() < 1e-9
    assert np.abs(published_values(published, 4)).max() < 1e-9

  @pytest.mark.parametrize("experimental, expected_z", [(False, 0.9), (True, 0.0)],
                           ids=["legacy", "experimental"])
  def test_translation_is_centre_of_mass_only_in_experimental_mode(self, experimental,
                                                                  expected_z):
    published = run_tracker(translation_objects, experimental)

    assert published[-1], "no reliable tracks"
    np.testing.assert_allclose(published_values(published, 3), expected_z, rtol=0, atol=1e-9)

  def test_planar_fallback_does_not_pull_a_measured_z_track(self):
    """A track that measured z (centre 0.9) keeps it through pixel boxes whose centre would be 0.6."""
    pixel_camera = scene_camera([0.0, 0.0, 3.0], [-90.0, 0.0, 0.0])
    box = {"x": 100.0, "y": 400.0, "width": 55.0, "height": 150.0}

    def pixel_object(when):
      return MovingObject({"id": 1, "category": "person", "confidence": 0.9,
                           "bounding_box_px": box, "size": [0.5, 0.5, 1.2]}, when, pixel_camera)

    # Where the box lands (legacy run, first reliable frames), so the 3D detection sits at the same XY.
    landed = run_tracker(lambda n, when: [pixel_object(when)], experimental=False)[-1][0]
    measured_camera = scene_camera([0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
    tracker = IntelLabsTracking(MAX_UNRELIABLE_TIME, NON_MEASUREMENT_TIME_DYNAMIC,
                                NON_MEASUREMENT_TIME_STATIC, FPS)
    tracker.uuid_manager.scene_id = "scene"
    tracker.observation_processor = SimpleNamespace(process=lambda *args: None)
    for n in range(FRAMES):
      when = WHEN + n / FPS
      if n < FRAMES // 2:
        obj = MovingObject({"id": 1, "category": "person", "confidence": 0.9,
                            "translation": [landed[1], landed[2], 0.9], "size": [0.5, 0.5, 1.2]},
                           when, measured_camera)
      else:
        obj = pixel_object(when)
      tracker.trackCategory([obj], when, [])
    tracks = tracker.tracker.get_reliable_tracks()
    tracker.uuid_manager.shutdown()

    assert len(tracks) == 1
    assert tracks[0].z_measured
    assert tracks[0].z == pytest.approx(0.9, abs=0.05), "the pixel boxes (centre 0.6) did not pull z"

  def test_planar_noisy_height_characterization(self):
    rng = np.random.default_rng(2149)
    t = np.arange(FRAMES)[:, None] / FPS
    heights = 1.7 + 0.12 * np.sin(2 * np.pi * t / 8) + rng.normal(0.0, 0.08, (FRAMES, 2))

    legacy = run_tracker(planar_objects(heights), experimental=False)
    experimental = run_tracker(planar_objects(heights), experimental=True)

    assert np.abs(published_values(experimental, 3)).max() < 0.25
    assert np.abs(published_values(experimental, 4)).max() < 0.3
    assert [[track[0] for track in frame] for frame in experimental] \
      == [[track[0] for track in frame] for frame in legacy]
    for index in (1, 2):
      np.testing.assert_allclose(published_values(experimental, index),
                                 published_values(legacy, index), rtol=0, atol=1e-9)
    assert len(set(published_values(experimental, 0))) == 2, "one track per object"
