# SPDX-FileCopyrightText: (C) 2026 Nokia
# SPDX-License-Identifier: Apache-2.0

import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock
import unittest


sys.modules.setdefault("robot_vision", types.SimpleNamespace(tracking=types.SimpleNamespace()))
sys.modules.setdefault("cv2", types.SimpleNamespace())
sys.modules.setdefault("open3d", types.SimpleNamespace())
sys.modules.setdefault("vdms", types.SimpleNamespace())
if "scipy" not in sys.modules:
  scipy_module = types.ModuleType("scipy")
  spatial_module = types.ModuleType("scipy.spatial")
  transform_module = types.ModuleType("scipy.spatial.transform")

  class _DummyRotation:
    pass

  transform_module.Rotation = _DummyRotation
  spatial_module.transform = transform_module
  scipy_module.spatial = spatial_module
  sys.modules["scipy"] = scipy_module
  sys.modules["scipy.spatial"] = spatial_module
  sys.modules["scipy.spatial.transform"] = transform_module
if "fast_geometry" not in sys.modules:
  fast_geometry = types.ModuleType("fast_geometry")

  class _DummyPoint:
    def __init__(self, *args):
      if len(args) == 1 and isinstance(args[0], (tuple, list)):
        args = args[0]
      padded = list(args) + [0.0, 0.0, 0.0]
      self.x, self.y, self.z = padded[:3]

  class _DummyShape:
    def __init__(self, *args, **kwargs):
      pass

  fast_geometry.Point = _DummyPoint
  fast_geometry.Line = _DummyShape
  fast_geometry.Rectangle = _DummyShape
  fast_geometry.Polygon = _DummyShape
  fast_geometry.Size = _DummyShape
  sys.modules["fast_geometry"] = fast_geometry

from controller.ilabs_tracking import IntelLabsTracking


def _make_tracker():
  tracker = IntelLabsTracking.__new__(IntelLabsTracking)
  tracker.uuid_manager = SimpleNamespace(active_ids={}, assignID=Mock())
  tracker.all_tracker_objects = []
  return tracker


class TestIntelLabsTrackingFromTrackedObject(unittest.TestCase):

  def test_uses_previous_track_when_rv_id_matches(self):
    tracker = _make_tracker()
    prev_obj = SimpleNamespace(rv_id=10, uuid="prev")
    tracker.all_tracker_objects = [prev_obj]

    current_obj = SimpleNamespace(
        uuid="obj-1",
        location=[SimpleNamespace(point=None)],
        velocity=None,
        rv_id=None,
        setPrevious=Mock(),
        inferRotationFromVelocity=Mock(),
        setGID=Mock()
    )
    tracked_object = SimpleNamespace(
        id=10, x=1.0, y=2.0, z=3.0, vx=0.1, vy=0.2,
        attributes={"info": "obj-1"}
    )

    out = tracker.from_tracked_object(tracked_object, [current_obj])

    self.assertIs(out, current_obj)
    current_obj.setPrevious.assert_called_once_with(prev_obj)
    current_obj.inferRotationFromVelocity.assert_called_once()
    current_obj.setGID.assert_not_called()
    tracker.uuid_manager.assignID.assert_called_once_with(current_obj)
    self.assertEqual(current_obj.location[0].point.x, 1.0)
    self.assertEqual(current_obj.velocity.x, 0.1)

  def test_returns_existing_tracker_object_when_not_in_current_frame(self):
    tracker = _make_tracker()
    existing = SimpleNamespace(uuid="obj-2")
    tracker.all_tracker_objects = [existing]

    tracked_object = SimpleNamespace(
        id=22, x=0.0, y=0.0, z=0.0, vx=0.0, vy=0.0,
        attributes={"info": "obj-2"}
    )

    out = tracker.from_tracked_object(tracked_object, [])
    self.assertIs(out, existing)
    tracker.uuid_manager.assignID.assert_not_called()

  def test_preserves_existing_gid_mapping(self):
    tracker = _make_tracker()
    tracker.uuid_manager.active_ids = {33: ["gid-33"]}

    current_obj = SimpleNamespace(
        uuid="obj-3",
        location=[SimpleNamespace(point=None)],
        velocity=None,
        rv_id=None,
        setPrevious=Mock(),
        inferRotationFromVelocity=Mock(),
        setGID=Mock()
    )
    tracked_object = SimpleNamespace(
        id=33, x=4.0, y=5.0, z=6.0, vx=0.3, vy=0.4,
        attributes={"info": "obj-3"}
    )

    out = tracker.from_tracked_object(tracked_object, [current_obj])
    self.assertIs(out, current_obj)
    current_obj.setPrevious.assert_not_called()
    current_obj.setGID.assert_called_once_with("gid-33")
    tracker.uuid_manager.assignID.assert_called_once_with(current_obj)

  def test_returns_none_when_uuid_not_found(self):
    tracker = _make_tracker()
    tracked_object = SimpleNamespace(
        id=99, x=0.0, y=0.0, z=0.0, vx=0.0, vy=0.0,
        attributes={"info": "missing"}
    )
    out = tracker.from_tracked_object(tracked_object, [])
    self.assertIsNone(out)
    tracker.uuid_manager.assignID.assert_not_called()
