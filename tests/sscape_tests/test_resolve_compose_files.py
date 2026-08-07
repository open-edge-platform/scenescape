#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for GPU DRI compose-file resolution."""

from unittest.mock import patch

from tests.utils.profiles import resolve_compose_files

TEST_NAME = "NEX-T22100"

_RETAIL = "tests/compose/dlstreamer/compose-retail_video.yml"
_QUEUING = "tests/compose/dlstreamer/compose-queuing_video.yml"
_OTHER = "tests/compose/compose-scene.yml"
_RETAIL_DRI = "tests/compose/dlstreamer/compose-gpu-dri-retail.yml"
_QUEUING_DRI = "tests/compose/dlstreamer/compose-gpu-dri-queuing.yml"


def test_resolve_compose_files_skips_missing_dri(tmp_path):
  """No DRI overrides when the DRM path does not exist."""
  missing = tmp_path / "missing-dri"
  files = resolve_compose_files((_RETAIL, _QUEUING, _OTHER), dri_path=str(missing))
  assert files == (_RETAIL, _QUEUING, _OTHER)


def test_resolve_compose_files_skips_empty_dri_directory(tmp_path):
  """Empty /dev/dri (common on WSL) must not enable GPU device mounts."""
  empty = tmp_path / "dri"
  empty.mkdir()
  files = resolve_compose_files((_RETAIL, _QUEUING), dri_path=str(empty))
  assert files == (_RETAIL, _QUEUING)
  assert _RETAIL_DRI not in files
  assert _QUEUING_DRI not in files


def test_resolve_compose_files_appends_overrides_for_char_devices(tmp_path):
  """When usable DRM nodes exist, matching GPU overrides are appended."""
  dri = tmp_path / "dri"
  dri.mkdir()
  with patch("tests.utils.profiles._host_has_dri", return_value=True):
    files = resolve_compose_files((_OTHER, _RETAIL, _QUEUING), dri_path=str(dri))

  assert _RETAIL_DRI in files
  assert _QUEUING_DRI in files
  assert files.index(_RETAIL) < files.index(_RETAIL_DRI)
