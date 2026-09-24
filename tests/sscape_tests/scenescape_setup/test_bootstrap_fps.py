# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for file-source FPS probing and chunk-rate mapping."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

TEST_NAME = "NEX-T22103"


@pytest.mark.parametrize(
  ("raw", "expected"),
  [
    ("25/1", 25.0),
    ("30000/1001", pytest.approx(30000 / 1001)),
    ("29.97", 29.97),
    ("0/0", None),
    ("N/A", None),
    ("", None),
    ("1/0", None),
    ("-5/1", None),
    ("not-a-rate", None),
  ],
)
def test_parse_frame_rate(bootstrap_deploy, raw, expected):
  assert bootstrap_deploy._parse_frame_rate(raw) == expected


@pytest.mark.parametrize(
  ("rates", "expected"),
  [
    ([2.0], 2),
    ([2.4], 2),
    ([2.5], 2),  # Python round-half-even: 2.5 -> 2
    ([2.6], 3),
    ([29.97], 30),
    ([120.0], 100),
    ([0.4], 1),
    ([5.0, 12.0, 8.0], 12),
  ],
)
def test_chunk_fps_from_probed_rates(bootstrap_deploy, rates, expected):
  assert bootstrap_deploy.chunk_fps_from_probed_rates(rates) == expected


def test_chunk_fps_from_probed_rates_rejects_empty(bootstrap_deploy):
  with pytest.raises(ValueError):
    bootstrap_deploy.chunk_fps_from_probed_rates([])


def test_apply_file_source_tracker_defaults_clamps_and_warns_partial(
  bootstrap_deploy, tmp_path, capsys,
):
  controller = tmp_path / "controller"
  controller.mkdir()
  cfg_path = controller / "tracker-config.json"
  cfg_path.write_text(json.dumps({"time_chunking_rate_fps": 10}) + "\n", encoding="utf-8")

  payload = {
    "source_type": "file",
    "video_paths": ["/videos/high.mp4", "/videos/missing.mp4"],
  }

  def fake_probe(path: Path):
    return 120.0 if path.name == "high.mp4" else None

  with patch.object(bootstrap_deploy, "probe_video_fps", side_effect=fake_probe):
    bootstrap_deploy.apply_file_source_tracker_defaults(tmp_path, payload)

  cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
  assert cfg["time_chunking_rate_fps"] == 100
  captured = capsys.readouterr()
  assert "could not probe FPS for 1/2" in captured.err
  assert "missing.mp4" in captured.err
  assert "clamped to max 100" in captured.out
  assert "time_chunking_rate_fps=100" in captured.out


def test_apply_file_source_tracker_defaults_skips_non_file(bootstrap_deploy, tmp_path):
  controller = tmp_path / "controller"
  controller.mkdir()
  cfg_path = controller / "tracker-config.json"
  cfg_path.write_text(json.dumps({"time_chunking_rate_fps": 10}) + "\n", encoding="utf-8")

  bootstrap_deploy.apply_file_source_tracker_defaults(
    tmp_path, {"source_type": "rtsp", "video_paths": ["/videos/a.mp4"]},
  )
  cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
  assert cfg["time_chunking_rate_fps"] == 10
