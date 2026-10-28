#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import orjson
import pytest

from scene_common import positioning_reasons as reasons
from scene_common.camera import Camera
from scene_common.mqtt import PubSub
from scene_common.positioning_config import ConsumerPositioningConfig
from scene_common.positioning_dwell import NS_PER_S, parse_timestamp_ns
from scene_common.schema import SchemaValidation
from tests.utils.ptz_pose import IDENTITY_MATRIX, iso, pose_context, status_payload
from controller.ptz import provider
from controller.ptz.config import MODE_ENFORCE, MODE_SHADOW, PTZSettings
from controller.ptz.registry import PTZPoseRegistry, is_ptz_camera
from controller.ptz.projection import ProjectedCamera

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "controller" / "src" / "schema" \
  / "metadata.schema.json"

SOURCE = "ptz-cam-1"
RESOLVER = "positioning-a"
SCENE_UID = "scene-uid-1"
FRAME = f"scene:{SCENE_UID}"
VERSION = "ptz-cam-1-v1"
T0 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)
POSE_TOPIC = PubSub.formatTopic(PubSub.POSITIONING_POSE, source_id=SOURCE)
STATUS_TOPIC = PubSub.formatTopic(PubSub.POSITIONING_STATUS, resolver_id=RESOLVER)

CONSUMER = ConsumerPositioningConfig(
  max_pose_age_s=0.5, max_clock_offset_s=0.05, max_detection_pipeline_latency_s=1.0,
  max_detection_timestamp_uncertainty_s=0.05)
IDENTITY = IDENTITY_MATRIX


def _ns(offset_s):
  return parse_timestamp_ns(iso(T0 + timedelta(seconds=offset_s)))


def pose(sequence, offset_s, valid=True, motion="stationary", frame=FRAME, version=VERSION,
         matrix=None, source=SOURCE, detail="moving"):
  return pose_context(source, sequence, T0 + timedelta(seconds=offset_s), frame, version,
                      matrix=matrix, valid=valid, motion_state=motion, reason_detail=detail)


def encode(payload):
  return orjson.dumps(payload)


def status(timestamp_offset_s=-100.0, state="online", resolver=RESOLVER):
  return encode(status_payload(resolver, T0 + timedelta(seconds=timestamp_offset_s), state))


def make_camera(camera_id=SOURCE, calibration=None, ptz=True):
  info = {"intrinsics": 70, "width": 640, "height": 480}
  if ptz:
    info["ptz_calibration"] = {"calibration_version": VERSION} if calibration is None \
      else calibration
  return Camera(camera_id, info)


def make_scene(*cameras, uid=SCENE_UID):
  return SimpleNamespace(uid=uid, cameras={camera.cameraID: camera for camera in cameras})


class Clock:
  def __init__(self, now_s=0.0, synchronized=True):
    self.now_s = now_s
    self.synchronized = synchronized

  def __call__(self):
    return int(round(self.now_s * NS_PER_S)) + _ns(0), self.synchronized


@pytest.fixture(scope="module")
def schema():
  return SchemaValidation(str(SCHEMA_PATH), is_multi_message=True)


@pytest.fixture
def clock():
  return Clock()


@pytest.fixture
def camera():
  return make_camera()


@pytest.fixture
def registry(schema, clock, camera):
  registry = make_registry(schema, clock)
  registry.reconcile([make_scene(camera)])
  return registry


def make_registry(schema, clock, mode=MODE_ENFORCE, assignments=None):
  settings = PTZSettings(
    mode=mode, consumer=CONSUMER,
    assignments={SOURCE: RESOLVER} if assignments is None else assignments)
  return PTZPoseRegistry(settings, schema, clock)


def feed_dwell(registry, count=30, start=0.0, step=0.1, first_sequence=1):
  """Stationary poses long enough to complete the dwell (>= 1 s plus uncertainty)."""
  registry.on_status_message(STATUS_TOPIC, status())
  for index in range(count):
    assert registry.on_pose_message(
      POSE_TOPIC, encode(pose(first_sequence + index, start + index * step))) is None
  return start + (count - 1) * step


class TestReconcile:
  def test_managed_ptz_camera_gets_a_subscription_source_and_resolver(self, registry):
    assert registry.pose_source_ids() == [SOURCE]
    assert registry.resolver_ids() == [RESOLVER]

  def test_static_cameras_are_never_managed(self, schema, clock):
    registry = make_registry(schema, clock, assignments={"static-1": RESOLVER, SOURCE: RESOLVER})
    registry.reconcile([make_scene(make_camera("static-1", ptz=False))])
    assert registry.pose_source_ids() == []
    assert registry.resolver_ids() == []

  def test_unassigned_ptz_camera_is_not_subscribed(self, schema, clock):
    registry = make_registry(schema, clock, assignments={})
    registry.reconcile([make_scene(make_camera())])
    assert registry.pose_source_ids() == []

  def test_removed_camera_is_dropped(self, registry):
    registry.reconcile([make_scene()])
    assert registry.pose_source_ids() == []
    assert registry.on_pose_message(POSE_TOPIC, encode(pose(1, 0))) == "unmanaged"

  def test_calibration_version_change_resets_dwell(self, registry, camera, clock):
    last = feed_dwell(registry)
    clock.now_s = last + 0.05
    assert registry.admit(camera, _ns(last - 0.5)).admitted
    new_camera = make_camera(calibration={"calibration_version": "v2"})
    registry.reconcile([make_scene(new_camera)])
    admission = registry.admit(new_camera, _ns(last - 0.5))
    assert (admission.admitted, admission.reason_detail) == (
      False, reasons.DETAIL_CALIBRATION_CHANGED)

  def test_unchanged_reconcile_keeps_dwell(self, registry, camera, clock):
    last = feed_dwell(registry)
    registry.reconcile([make_scene(make_camera())])
    clock.now_s = last + 0.05
    assert registry.admit(camera, _ns(last - 0.5)).admitted

  def test_moving_a_camera_to_another_scene_recreates_state(self, registry, camera, clock):
    last = feed_dwell(registry)
    registry.reconcile([make_scene(camera, uid="other-scene")])
    clock.now_s = last + 0.05
    admission = registry.admit(camera, _ns(last - 0.5))
    assert not admission.admitted
    assert admission.reason_detail == reasons.DETAIL_NO_SAMPLE

  def test_is_ptz_camera(self):
    assert is_ptz_camera(make_camera())
    assert not is_ptz_camera(make_camera(ptz=False))
    assert not is_ptz_camera(SimpleNamespace(cameraID="x"))


class TestPoseMessages:
  @pytest.mark.parametrize("raw,stage", [
    (b"x" * 5000, "size"),
    (b"{not json", "json"),
    (b"[]", "schema"),
    (b'{"schema_version": 1}', "schema"),
  ])
  def test_malformed_payloads_are_dropped(self, registry, raw, stage):
    with patch("controller.ptz.registry.metrics.inc_ptz_pose_rejected") as counter:
      assert registry.on_pose_message(POSE_TOPIC, raw) == stage
    counter.assert_called_once_with({"stage": stage})

  def test_valid_message_is_applied_without_counting(self, registry):
    with patch("controller.ptz.registry.metrics.inc_ptz_pose_rejected") as counter:
      assert registry.on_pose_message(POSE_TOPIC, encode(pose(1, 0))) is None
    counter.assert_not_called()

  @pytest.mark.parametrize("matrix", [
    [[2, 0, 0, 0], [0, 2, 0, 0], [0, 0, 2, 4], [0, 0, 0, 1]],
    [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 4], [0, 0, 0, 2]],
    [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, -1, 4], [0, 0, 0, 1]],
  ])
  def test_non_rigid_matrix_is_dropped(self, registry, matrix):
    assert registry.on_pose_message(POSE_TOPIC, encode(pose(1, 0, matrix=matrix))) == "guard"

  def test_oversized_matrix_is_dropped_by_the_schema(self, registry):
    payload = pose(1, 0)
    payload["pose"]["matrix_4x4"] = IDENTITY + [[0, 0, 0, 1]]
    assert registry.on_pose_message(POSE_TOPIC, encode(payload)) == "schema"

  def test_bad_timestamp_format_is_dropped(self, registry):
    payload = pose(1, 0)
    payload["timestamp"] = "yesterday"
    assert registry.on_pose_message(POSE_TOPIC, encode(payload)) == "schema"

  @pytest.mark.parametrize("topic", ["scenescape/other/topic", "scenescape/positioning/pose"])
  def test_unparseable_topic_is_dropped(self, registry, topic):
    assert registry.on_pose_message(topic, encode(pose(1, 0))) == "topic"

  def test_unmanaged_source_is_dropped(self, registry):
    topic = PubSub.formatTopic(PubSub.POSITIONING_POSE, source_id="someone-else")
    assert registry.on_pose_message(topic, encode(pose(1, 0, source="someone-else"))) == "unmanaged"

  def test_payload_naming_another_source_resets_the_dwell(self, registry, camera, clock):
    last = feed_dwell(registry)
    other = pose(31, last + 0.1, source="someone-else")
    assert registry.on_pose_message(POSE_TOPIC, encode(other)) is None
    clock.now_s = last + 0.15
    assert not registry.admit(camera, _ns(last - 0.5)).admitted


class TestStatusMessages:
  @pytest.mark.parametrize("raw,stage", [
    (b"x" * 2000, "size"),
    (b"{", "json"),
    (b'{"resolver_id": "r"}', "schema"),
    (encode({"resolver_id": RESOLVER, "status": "unknown", "timestamp": iso(T0)}), "schema"),
    (encode({"resolver_id": RESOLVER, "status": "online", "timestamp": "never"}), "schema"),
  ])
  def test_malformed_status_is_dropped(self, registry, raw, stage):
    assert registry.on_status_message(STATUS_TOPIC, raw) == stage

  def test_topic_must_match_the_resolver(self, registry):
    other = PubSub.formatTopic(PubSub.POSITIONING_STATUS, resolver_id="another")
    assert registry.on_status_message(other, status()) == "topic"

  def test_session_change_resets_dwell(self, registry, camera, clock):
    last = feed_dwell(registry)
    clock.now_s = last + 0.05
    assert registry.admit(camera, _ns(last - 0.5)).admitted
    assert registry.on_status_message(STATUS_TOPIC, status(timestamp_offset_s=last)) is None
    admission = registry.admit(camera, _ns(last - 0.5))
    assert (admission.admitted, admission.reason_detail) == (
      False, reasons.DETAIL_DWELL_INCOMPLETE)

  def test_offline_status_resets_dwell(self, registry, camera, clock):
    last = feed_dwell(registry)
    clock.now_s = last + 0.05
    registry.on_status_message(STATUS_TOPIC, status(state="offline"))
    assert not registry.admit(camera, _ns(last - 0.5)).admitted

  def test_same_session_status_keeps_dwell(self, registry, camera, clock):
    last = feed_dwell(registry)
    clock.now_s = last + 0.05
    registry.on_status_message(STATUS_TOPIC, status())
    assert registry.admit(camera, _ns(last - 0.5)).admitted


class TestAdmit:
  def test_admitted_detection_carries_the_projection_context(self, registry, camera, clock):
    last = feed_dwell(registry)
    clock.now_s = last + 0.05
    admission = registry.admit(camera, _ns(last - 0.5))
    assert admission.admitted and admission.managed
    context = admission.context
    assert (context.source_id, context.sequence) == (SOURCE, 30)
    assert (context.calibration_version, context.frame_id) == (VERSION, FRAME)
    assert context.dwell_elapsed_s == pytest.approx(2.9)
    assert admission.pose_age_s == pytest.approx(0.05)
    assert admission.timestamp_uncertainty_s == pytest.approx(0.01)
    np.testing.assert_allclose(context.camera.pose.pose_mat, IDENTITY)
    assert context.camera.cameraID == SOURCE
    assert context.camera.static_camera is camera

  def test_stored_camera_pose_is_never_modified(self, registry, camera, clock):
    before = camera.pose.pose_mat.copy()
    moved = [[0, -1, 0, 1], [1, 0, 0, 2], [0, 0, 1, 3], [0, 0, 0, 1]]
    registry.on_status_message(STATUS_TOPIC, status())
    for index in range(30):
      registry.on_pose_message(POSE_TOPIC, encode(pose(1 + index, index * 0.1, matrix=moved)))
    clock.now_s = 2.95
    context = registry.admit(camera, _ns(2.4)).context
    np.testing.assert_allclose(context.camera.pose.pose_mat, moved)
    np.testing.assert_array_equal(camera.pose.pose_mat, before)
    assert context.camera.pose.intrinsics is camera.pose.intrinsics
    assert not context.camera.pose.pose_mat.flags.writeable

  def test_context_is_cached_per_sequence_and_rebuilt_for_a_new_camera_object(
      self, registry, camera, clock):
    last = feed_dwell(registry)
    clock.now_s = last + 0.05
    first = registry.admit(camera, _ns(last - 0.5)).context.camera
    assert registry.admit(camera, _ns(last - 0.4)).context.camera is first
    registry.on_pose_message(POSE_TOPIC, encode(pose(31, last + 0.1)))
    clock.now_s = last + 0.15
    second = registry.admit(camera, _ns(last - 0.4)).context.camera
    assert second is not first and second.sequence == 31
    replacement = make_camera()
    assert registry.admit(replacement, _ns(last - 0.4)).context.camera is not second

  def test_rejection_reports_pose_metadata(self, registry, camera, clock):
    registry.on_status_message(STATUS_TOPIC, status())
    registry.on_pose_message(POSE_TOPIC, encode(pose(1, 0)))
    clock.now_s = 0.1
    admission = registry.admit(camera, _ns(0))
    assert (admission.admitted, admission.reason_detail) == (False, "dwell_incomplete")
    assert admission.invalid_reason == "invalid_pose"
    assert admission.context is None and admission.sequence == 1
    assert admission.calibration_version == VERSION
    assert admission.pose_age_s == pytest.approx(0.1)

  def test_no_pose_yet(self, registry, camera):
    admission = registry.admit(camera, _ns(0))
    assert (admission.reason_detail, admission.invalid_reason) == ("no_sample", "no_pose_available")
    assert admission.sequence is None

  def test_unassigned_ptz_camera_fails_closed_and_logs_once(self, schema, clock):
    registry = make_registry(schema, clock, assignments={})
    camera = make_camera()
    registry.reconcile([make_scene(camera)])
    with patch("controller.ptz.registry.log.error") as error:
      first = registry.admit(camera, _ns(0))
      second = registry.admit(camera, _ns(0))
    assert (first.admitted, first.managed, first.reason_detail) == (False, False, "no_sample")
    assert second.managed is False
    error.assert_called_once()

  def test_unsynchronized_clock_rejects_an_otherwise_admissible_detection(
      self, registry, camera, clock):
    last = feed_dwell(registry)
    clock.now_s = last + 0.05
    assert registry.admit(camera, _ns(last - 0.5)).admitted
    clock.synchronized = False
    admission = registry.admit(camera, _ns(last - 0.5))
    assert (admission.admitted, admission.reason_detail, admission.invalid_reason) == (
      False, "sample_stale", "pose_expired")

  def test_explicit_local_time_overrides_the_clock(self, registry, camera, clock):
    last = feed_dwell(registry)
    clock.now_s = last + 10
    assert not registry.admit(camera, _ns(last - 0.5)).admitted
    assert registry.admit(camera, _ns(last - 0.5), local_now_ns=_ns(last + 0.05)).admitted

  def test_stale_pose_is_rejected(self, registry, camera, clock):
    last = feed_dwell(registry)
    clock.now_s = last + 0.6
    assert registry.admit(camera, _ns(last - 0.5)).reason_detail == "sample_stale"


class TestVisibility:
  def test_static_camera_is_returned_unchanged(self, registry):
    static = make_camera("static-1", ptz=False)
    assert registry.visibility_camera(static) is static

  def test_ptz_camera_without_pose_sees_nothing(self, registry, camera):
    assert registry.visibility_camera(camera) is None

  def test_fresh_valid_pose_gives_a_per_frame_view(self, registry, camera, clock):
    last = feed_dwell(registry)
    clock.now_s = last + 0.1
    view = registry.visibility_camera(camera)
    assert isinstance(view, ProjectedCamera)
    assert view.cameraID == SOURCE and view.static_camera is camera
    assert view.pose.regionOfView is not None

  def test_view_needs_a_valid_pose_not_a_complete_dwell(self, registry, camera, clock):
    registry.on_pose_message(POSE_TOPIC, encode(pose(1, 0)))
    clock.now_s = 0.1
    assert registry.visibility_camera(camera) is not None

  @pytest.mark.parametrize("offset", [0.5, 0.6])
  def test_expired_pose_sees_nothing(self, registry, camera, clock, offset):
    registry.on_pose_message(POSE_TOPIC, encode(pose(1, 0)))
    clock.now_s = offset
    assert registry.visibility_camera(camera) is None

  def test_invalid_pose_sees_nothing(self, registry, camera, clock):
    registry.on_pose_message(POSE_TOPIC, encode(pose(1, 0)))
    registry.on_pose_message(POSE_TOPIC, encode(pose(2, 0.1, valid=False, motion="slewing")))
    clock.now_s = 0.15
    assert registry.visibility_camera(camera) is None

  @pytest.mark.parametrize("frame,version", [("scene:other", VERSION), (FRAME, "other-version")])
  def test_mismatching_pose_sees_nothing(self, registry, camera, clock, frame, version):
    registry.on_pose_message(POSE_TOPIC, encode(pose(1, 0, frame=frame, version=version)))
    clock.now_s = 0.1
    assert registry.visibility_camera(camera) is None

  def test_unsynchronized_clock_sees_nothing(self, registry, camera, clock):
    registry.on_pose_message(POSE_TOPIC, encode(pose(1, 0)))
    clock.now_s = 0.1
    clock.synchronized = False
    assert registry.visibility_camera(camera) is None

  def test_unassigned_ptz_camera_sees_nothing(self, schema, clock):
    registry = make_registry(schema, clock, assignments={})
    camera = make_camera()
    registry.reconcile([make_scene(camera)])
    assert registry.visibility_camera(camera) is None

  def test_shadow_mode_keeps_the_static_view(self, schema, clock, camera):
    registry = make_registry(schema, clock, mode=MODE_SHADOW)
    registry.reconcile([make_scene(camera)])
    assert registry.visibility_camera(camera) is camera


class TestSharedDwellAccessors:
  def test_latest_pose_is_exposed_read_only_and_tracks_the_newest_message(self):
    from scene_common.positioning_dwell import DwellConfig, DwellTracker, PoseSnapshot
    tracker = DwellTracker(SOURCE, RESOLVER, DwellConfig.from_consumer_config(CONSUMER))
    assert tracker.latest_pose is None
    first = PoseSnapshot.from_payload(pose(1, 0))
    tracker.on_pose(first)
    assert tracker.latest_pose is first
    second = PoseSnapshot.from_payload(pose(2, 0.1, valid=False, motion="slewing"))
    tracker.on_pose(second)
    assert tracker.latest_pose is second
    with pytest.raises(AttributeError):
      tracker.latest_pose = first

  def test_camera_exposes_its_ptz_calibration(self):
    assert make_camera().ptz_calibration == {"calibration_version": VERSION}
    assert make_camera(ptz=False).ptz_calibration is None
    invalid = Camera("c", {"intrinsics": 70, "width": 640, "height": 480,
                           "ptz_calibration": "invalid"})
    assert invalid.ptz_calibration is None


class TestProvider:
  def teardown_method(self):
    provider.set_active_registry(None)

  def test_without_a_registry_the_camera_is_unchanged(self, camera):
    provider.set_active_registry(None)
    assert provider.active_registry() is None
    assert provider.visibility_camera(camera) is camera

  def test_with_a_registry_a_ptz_camera_needs_a_pose(self, registry, camera):
    provider.set_active_registry(registry)
    assert provider.active_registry() is registry
    assert provider.visibility_camera(camera) is None
