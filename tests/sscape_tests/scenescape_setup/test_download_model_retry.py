# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for detection-model download retry behavior."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

TEST_NAME = "NEX-T22104"


def test_main_retries_when_start_downloader_raises(download_model):
  calls = {"start": 0}

  def start_once(*_args, **_kwargs):
    calls["start"] += 1
    if calls["start"] == 1:
      raise subprocess.CalledProcessError(1, ["docker", "run"])

  with (
    patch.object(download_model, "compose_project_name", return_value="demo"),
    patch.object(download_model, "model_present", side_effect=[False, True]),
    patch.object(download_model, "ensure_volume"),
    patch.object(download_model, "start_downloader", side_effect=start_once),
    patch.object(download_model, "wait_for_api"),
    patch.object(download_model, "request_download", return_value=["job-1"]),
    patch.object(download_model, "wait_for_jobs"),
    patch.object(download_model, "stop_downloader"),
    patch.object(download_model.time, "sleep"),
    patch("sys.argv", ["download_model.py", "/tmp/deploy"]),
  ):
    assert download_model.main() == 0

  assert calls["start"] == 2


def test_main_fails_after_exhausted_retries(download_model):
  with (
    patch.object(download_model, "compose_project_name", return_value="demo"),
    patch.object(download_model, "model_present", return_value=False),
    patch.object(download_model, "ensure_volume"),
    patch.object(
      download_model,
      "start_downloader",
      side_effect=subprocess.CalledProcessError(1, ["docker", "run"]),
    ),
    patch.object(download_model, "stop_downloader") as stop,
    patch.object(download_model.time, "sleep"),
    patch("sys.argv", ["download_model.py", "/tmp/deploy"]),
  ):
    assert download_model.main() == 1

  assert stop.call_count == download_model.DOWNLOAD_ATTEMPTS
