#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for MAVLink → external_source adapter pure helpers."""

import importlib.util
import math
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Adapter imports pymavlink at module load; keep unit tests free of that dep.
sys.modules.setdefault("pymavlink", MagicMock())
sys.modules.setdefault("pymavlink.mavutil", MagicMock())

_ADAPTER_PATH = (
  Path(__file__).resolve().parents[2]
  / "tools" / "external_source_adapters" / "mavlink_to_external_source.py"
)
_SPEC = importlib.util.spec_from_file_location(
  "mavlink_to_external_source", _ADAPTER_PATH)
_ADAPTER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_ADAPTER)

IDENTITY_QUAT = _ADAPTER.IDENTITY_QUAT
MavlinkState = _ADAPTER.MavlinkState
build_payload = _ADAPTER.build_payload
euler_zyx_to_quaternion = _ADAPTER.euler_zyx_to_quaternion

TEST_NAME = "NEX-T22102"


def test_euler_zyx_to_quaternion_identity_at_zero():
  quat = euler_zyx_to_quaternion(0.0, 0.0, 0.0)
  assert quat == pytest.approx(IDENTITY_QUAT)


def test_euler_zyx_to_quaternion_yaw_90_degrees():
  quat = euler_zyx_to_quaternion(0.0, 0.0, math.pi / 2)
  assert quat[0] == pytest.approx(0.0, abs=1e-9)
  assert quat[1] == pytest.approx(0.0, abs=1e-9)
  assert abs(quat[2]) == pytest.approx(math.sqrt(0.5), abs=1e-9)
  assert abs(quat[3]) == pytest.approx(math.sqrt(0.5), abs=1e-9)


def test_mavlink_state_updates_from_global_position_and_attitude():
  state = MavlinkState()
  assert state.have_position is False

  assert state.update(SimpleNamespace(
    get_type=lambda: "GLOBAL_POSITION_INT",
    lat=374000000, lon=-1221000000, alt=12500,
  )) is True
  assert state.have_position is True
  assert state.lat == pytest.approx(37.4)
  assert state.lon == pytest.approx(-122.1)
  assert state.alt_m == pytest.approx(12.5)

  assert state.update(SimpleNamespace(
    get_type=lambda: "ATTITUDE",
    roll=0.0, pitch=0.0, yaw=0.0,
  )) is True
  assert state.have_attitude is True
  assert state.rotation == pytest.approx(IDENTITY_QUAT)


def test_mavlink_state_ignores_gps_raw_once_position_known():
  state = MavlinkState()
  state.update(SimpleNamespace(
    get_type=lambda: "GLOBAL_POSITION_INT",
    lat=10000000, lon=20000000, alt=1000,
  ))
  assert state.update(SimpleNamespace(
    get_type=lambda: "GPS_RAW_INT",
    fix_type=3, lat=99999999, lon=99999999, alt=9999,
  )) is False
  assert state.lat == pytest.approx(1.0)


def test_build_payload_includes_self_object_and_wgs84_pose():
  state = MavlinkState()
  state.lat, state.lon, state.alt_m = 37.4, -122.1, 10.0
  state.rotation = list(IDENTITY_QUAT)
  state.have_attitude = True

  payload = build_payload(
    state, source_id="drone-1", category="vehicle",
    publish_self=True, include_pose=True)

  assert payload["source_id"] == "drone-1"
  assert payload["objects"] == [{
    "id": "drone-1",
    "category": "vehicle",
    "translation": [0.0, 0.0, 0.0],
    "rotation": IDENTITY_QUAT,
    "size": [0.6, 0.6, 0.3],
  }]
  assert payload["pose"]["reference_frame"] == "wgs84"
  assert payload["pose"]["lat_long_alt"] == [37.4, -122.1, 10.0]
  assert "timestamp" in payload


def test_build_payload_pose_only_when_publish_self_disabled():
  state = MavlinkState()
  state.lat, state.lon, state.alt_m = 1.0, 2.0, 3.0

  payload = build_payload(
    state, source_id="drone-1", category="vehicle",
    publish_self=False, include_pose=True)

  assert payload["objects"] == []
  assert "pose" in payload


def test_build_payload_omits_pose_without_position_or_when_disabled():
  state = MavlinkState()
  payload = build_payload(
    state, source_id="drone-1", category="vehicle",
    publish_self=True, include_pose=True)
  assert "pose" not in payload
  assert payload["objects"][0]["id"] == "drone-1"

  state.lat, state.lon, state.alt_m = 1.0, 2.0, 3.0
  payload = build_payload(
    state, source_id="drone-1", category="vehicle",
    publish_self=False, include_pose=False)
  assert payload["objects"] == []
  assert "pose" not in payload
