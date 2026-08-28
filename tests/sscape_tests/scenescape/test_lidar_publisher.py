# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for LiDAR demo publisher helpers.

Modules under test live in ``sample_data/lidar_intersection/`` (not on the
Django/controller path). Checked ``tests/sscape_tests/conftest.py`` and
``tests/sscape_tests/scenescape/conftest.py`` — no shared bootstrap for these
sample scripts; ``sys.path`` is extended once to that directory so the split
modules import as they do under ``user_scripts/`` in the container.
"""

import math
import sys
from pathlib import Path

import pytest

pytest.importorskip("paho.mqtt.client")

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SAMPLE = _REPO_ROOT / "sample_data" / "lidar_intersection"
if str(_SAMPLE) not in sys.path:
  sys.path.insert(0, str(_SAMPLE))

import lidar_file_playback as playback  # noqa: E402
import lidar_sensor_contract as contract  # noqa: E402

TEST_NAME = "NEX-T22104"


# ── playback_index / index_span_delta (file-playback only) ────────────────────


def test_playback_index_zero_count_returns_start():
  assert playback.playback_index(0, 10699, 10949, True) == 10699


def test_playback_index_loops_within_span():
  start, stop = 10699, 10949
  span = stop - start + 1
  assert playback.playback_index(1, start, stop, True) == start
  assert playback.playback_index(span, start, stop, True) == stop
  assert playback.playback_index(span + 1, start, stop, True) == start


def test_playback_index_without_loop_clamps_at_stop():
  assert playback.playback_index(10000, 10699, 10949, False) == 10949


def test_index_span_delta_zero_when_aligned():
  assert playback.index_span_delta(10700, 10700, 10699, 10949, True) == 0


def test_index_span_delta_wraps_forward_when_looping():
  start, stop = 10699, 10949
  span = stop - start + 1
  assert playback.index_span_delta(stop, start, start, stop, True) == 1
  assert playback.index_span_delta(start, stop, start, stop, True) == span - 1


def test_index_span_delta_without_loop_does_not_wrap():
  assert playback.index_span_delta(10949, 10699, 10699, 10949, False) == 0
  assert playback.index_span_delta(10699, 10710, 10699, 10949, False) == 11


# ── bbox3d_to_quaternion (sensor contract) ────────────────────────────────────


@pytest.mark.parametrize("yaw,scene_yaw", [
  (0.0, 0.0),
  (math.pi / 2.0, -math.pi / 2.0),
  (math.pi, -math.pi),
  (-math.pi / 4.0, math.pi / 4.0),
])
def test_bbox3d_to_quaternion_applies_negated_yaw_as_z_w(yaw, scene_yaw):
  q = contract.bbox3d_to_quaternion(yaw)
  assert q[0] == 0.0
  assert q[1] == 0.0
  half = scene_yaw / 2.0
  expected_z = math.sin(half)
  expected_w = math.cos(half)
  if expected_w < 0.0:
    expected_z, expected_w = -expected_z, -expected_w
  assert q[2] == pytest.approx(expected_z)
  assert q[3] == pytest.approx(expected_w)


def test_bbox3d_to_quaternion_flips_hemisphere_when_w_negative():
  # scene_yaw = 5*pi/4 => cos(half) < 0 before the w-sign flip.
  yaw = -5.0 * math.pi / 4.0
  q = contract.bbox3d_to_quaternion(yaw)
  assert q[3] > 0.0
  assert abs(q[2]) < 1.0 - 1e-8
  assert abs(q[3]) < 1.0 - 1e-8


# ── LidarCatchUp (file-playback only) ─────────────────────────────────────────


@pytest.fixture
def catchup_sandbox(tmp_path):
  """Stage fake .bin frames for LidarCatchUp."""
  data = tmp_path / "velodyne"
  data.mkdir()
  feed = tmp_path / "feed"
  start, stop = 100, 110
  for idx in range(start, stop + 1):
    (data / f"{idx:06d}.bin").write_bytes(b"\x00")

  cam_count = {"n": 0}

  def camera_index_fn():
    return playback.playback_index(cam_count["n"], start, stop, True)

  def set_camera_published(count: int) -> None:
    cam_count["n"] = count

  catchup = playback.LidarCatchUp(
    data_path=str(data / "%06d.bin"),
    feed_dir=str(feed),
    start_index=start,
    cam_start=start,
    cam_stop=stop,
    cam_loop=True,
    camera_index_fn=camera_index_fn,
  )
  yield {
    "catchup": catchup,
    "feed": feed,
    "data": data,
    "start": start,
    "set_camera_published": set_camera_published,
  }


def test_lidar_catchup_prime_installs_slots_at_camera_now(catchup_sandbox):
  sb = catchup_sandbox
  sb["set_camera_published"](3)  # latest index = start + 2 = 102
  catchup = sb["catchup"]
  catchup.prime()

  feed = sb["feed"]
  assert (feed / "00000000.bin").is_file()
  assert (feed / "00000001.bin").is_file()
  assert catchup._slot_index[0] == 102
  assert catchup._slot_index[1] == 102
  assert catchup._next_json_slot == 0
  assert catchup._next_create_slot == 2
  assert catchup.skipped_total == 0


def test_lidar_catchup_on_lidar_done_skips_to_camera_now(catchup_sandbox):
  sb = catchup_sandbox
  sb["set_camera_published"](1)  # index 100
  catchup = sb["catchup"]
  catchup.prime()

  sb["set_camera_published"](6)  # index 105
  inferred, skipped = catchup.on_lidar_done()

  assert inferred == 100
  assert skipped == 5
  assert catchup.skipped_total == 5
  assert catchup._next_json_slot == 1
  assert catchup._slot_index[2] == 105
  assert (sb["feed"] / "00000002.bin").is_file()


def test_lidar_catchup_successive_done_calls_stay_slot_aligned(catchup_sandbox):
  """Simulate JSON-error then good frame: two on_lidar_done advances without publish."""
  sb = catchup_sandbox
  sb["set_camera_published"](1)
  catchup = sb["catchup"]
  catchup.prime()

  sb["set_camera_published"](4)  # 103
  first_idx, _ = catchup.on_lidar_done()
  second_idx, _ = catchup.on_lidar_done()

  assert first_idx == 100
  assert second_idx == 100
  assert catchup._next_json_slot == 2
  assert catchup._slot_index[3] == 103


def test_lidar_catchup_nudge_lookahead_rewrites_unread_slot(catchup_sandbox):
  sb = catchup_sandbox
  sb["set_camera_published"](1)
  catchup = sb["catchup"]
  catchup.prime()
  assert catchup._slot_index[1] == 100

  sb["set_camera_published"](8)  # 107
  catchup.nudge_lookahead()
  assert catchup._slot_index[1] == 107


def test_lidar_catchup_link_missing_frame_raises(catchup_sandbox):
  catchup = catchup_sandbox["catchup"]
  catchup.reset_feed_dir()
  with pytest.raises(FileNotFoundError, match="LiDAR frame missing"):
    catchup._link_slot(0, 999)


# ── build_*_message (sensor contract) ─────────────────────────────────────────


def test_build_lidar_message_empty_objects_still_well_formed():
  msg = contract.build_lidar_message({"objects": []}, "intersection-lidar1", 10.0)
  assert msg["id"] == "intersection-lidar1"
  assert "timestamp" in msg and msg["timestamp"].endswith("Z")
  assert msg["rate"] == 10.0
  assert msg["objects"] == {}


def test_build_lidar_message_maps_vehicle_with_quaternion_and_scene_offset():
  raw = {
    "objects": [{
      "label": "vehicle",
      "confidence": 0.9,
      "bbox_3d": {"x": 1.0, "y": 2.0, "z": 3.0, "l": 4.0, "w": 5.0, "h": 6.0, "yaw": 0.0},
    }],
  }
  msg = contract.build_lidar_message(raw, "intersection-lidar1", 5.5)
  assert list(msg["objects"].keys()) == ["vehicle"]
  det = msg["objects"]["vehicle"][0]
  assert det["translation"] == [-2.0, -1.0, 0.0]
  assert det["size"] == [4.0, 5.0, 6.0]
  assert det["rotation"] == contract.bbox3d_to_quaternion(0.0)
  assert det["source"] == "lidar"


def test_build_lidar_message_skips_unknown_label_and_incomplete_bbox():
  raw = {
    "objects": [
      {"label": "person", "bbox_3d": {"x": 0, "y": 0, "z": 0, "l": 1, "w": 1, "h": 1, "yaw": 0}},
      {"label": "vehicle", "bbox_3d": {"x": 0, "y": 0}},  # missing yaw
      {"label_id": 2, "confidence": 0.8,
       "bbox_3d": {"x": 0, "y": 0, "z": 0, "l": 1, "w": 1, "h": 1, "yaw": 0.1}},
    ],
  }
  msg = contract.build_lidar_message(raw, "intersection-lidar1", 1.0)
  assert "person" not in msg["objects"]
  assert len(msg["objects"].get("vehicle", [])) == 1


def test_build_camera_message_empty_objects_still_well_formed():
  msg = contract.build_camera_message(
    {"objects": []}, "intersection-cam1", 10.0, ["vehicle", "cyclist"],
  )
  assert msg["id"] == "intersection-cam1"
  assert msg["objects"] == {}
  assert "timestamp" in msg


def test_build_camera_message_filters_labels_not_in_allowlist():
  raw = {
    "objects": [
      {"x": 1, "y": 2, "w": 3, "h": 4,
       "detection": {"label": "person", "confidence": 0.99}},
      {"x": 5, "y": 6, "w": 7, "h": 8,
       "detection": {"label": "vehicle", "confidence": 0.88}},
    ],
  }
  msg = contract.build_camera_message(raw, "intersection-cam1", 8.0, ["vehicle"])
  assert list(msg["objects"].keys()) == ["vehicle"]
  assert msg["objects"]["vehicle"][0]["bounding_box_px"]["width"] == 7
  assert msg["objects"]["vehicle"][0]["source"] == "camera"
