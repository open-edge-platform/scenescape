# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import math
from types import SimpleNamespace

import pytest

from controller.ilabs_tracking import (IntelLabsTracking, _quaternion_to_yaw,
                                       _yaw_to_quaternion)
from scene_common.geometry import Point


@pytest.mark.parametrize("yaw", [
  -math.pi,
  -math.pi / 2.0,
  0.0,
  math.pi / 2.0,
  math.pi,
])
def test_quaternion_to_yaw_for_z_axis_rotation(yaw):
  quaternion = [0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0)]

  actual = _quaternion_to_yaw(quaternion)

  assert math.cos(actual) == pytest.approx(math.cos(yaw))
  assert math.sin(actual) == pytest.approx(math.sin(yaw))


def test_quaternion_to_yaw_does_not_treat_y_component_as_yaw():
  pitch = math.pi / 4.0
  quaternion = [0.0, math.sin(pitch / 2.0), 0.0, math.cos(pitch / 2.0)]

  assert _quaternion_to_yaw(quaternion) == pytest.approx(0.0)


@pytest.mark.parametrize("rotation", [None, [], [0.0, 0.0, 0.0, 0.0], [0.0, math.nan, 0.0, 1.0]])
def test_quaternion_to_yaw_returns_zero_for_invalid_rotation(rotation):
  assert _quaternion_to_yaw(rotation) == 0.0


def test_to_rv_object_converts_quaternion_to_yaw():
  yaw = math.pi / 2.0
  detected_object = SimpleNamespace(
    sceneLoc=Point(1.0, 2.0, 3.0),
    size=[4.0, 2.0, 1.5],
    rotation=[0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0)],
    confidence=0.9,
    info={},
    frameCount=1,
  )
  tracker = IntelLabsTracking.__new__(IntelLabsTracking)

  rv_object = tracker.to_rv_object(detected_object)

  assert rv_object.yaw == pytest.approx(yaw)


@pytest.mark.parametrize("yaw", [
  -math.pi,
  -math.pi / 2.0,
  0.0,
  math.pi / 2.0,
  math.pi,
])
def test_yaw_to_quaternion_produces_z_axis_only_quaternion(yaw):
  quaternion = _yaw_to_quaternion(yaw)

  assert quaternion == pytest.approx([0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0)])


def _make_tracked_object(uuid_value, yaw=0.0):
  return SimpleNamespace(
    attributes={'info': uuid_value},
    x=1.0, y=2.0, z=0.0,
    vx=0.1, vy=0.2,
    yaw=yaw,
    id=42,
  )


def _make_sscape_object(uuid_value, has_detection_rotation, rotation=None):
  return SimpleNamespace(
    uuid=uuid_value,
    has_detection_rotation=has_detection_rotation,
    location=[SimpleNamespace(point=None)],
    rotation=rotation if rotation is not None else [0.0, 0.0, 0.0, 1.0],
    velocity=None,
    setGID=lambda gid: None,
  )


def test_from_tracked_object_overwrites_rotation_when_detection_rotation_present():
  yaw = math.pi / 2.0
  tracked_object = _make_tracked_object("uuid-1", yaw=yaw)
  sscape_object = _make_sscape_object("uuid-1", has_detection_rotation=True)

  tracker = IntelLabsTracking.__new__(IntelLabsTracking)
  tracker.all_tracker_objects = []
  tracker.uuid_manager = SimpleNamespace(assignID=lambda obj: None)

  result = tracker.from_tracked_object(tracked_object, [sscape_object])

  assert result.rotation == pytest.approx(_yaw_to_quaternion(yaw))


def test_from_tracked_object_does_not_overwrite_rotation_for_velocity_inferred_rotation():
  original_rotation = [0.0, 0.0, 0.1, 0.9]
  tracked_object = _make_tracked_object("uuid-2", yaw=math.pi / 2.0)
  sscape_object = _make_sscape_object("uuid-2", has_detection_rotation=False,
                                      rotation=original_rotation)

  tracker = IntelLabsTracking.__new__(IntelLabsTracking)
  tracker.all_tracker_objects = []
  tracker.uuid_manager = SimpleNamespace(assignID=lambda obj: None)

  result = tracker.from_tracked_object(tracked_object, [sscape_object])

  assert result.rotation == original_rotation
