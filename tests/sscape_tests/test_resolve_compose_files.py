#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for GPU DRI compose-file resolution."""

import os
from unittest.mock import patch

from tests.utils.profiles import _host_has_dri, resolve_compose_files

TEST_NAME = "NEX-T22100"

_RETAIL = "tests/compose/dlstreamer/compose-retail_video.yml"
_QUEUING = "tests/compose/dlstreamer/compose-queuing_video.yml"
_OTHER = "tests/compose/compose-scene.yml"
_RETAIL_DRI = "tests/compose/dlstreamer/compose-gpu-dri-retail.yml"
_QUEUING_DRI = "tests/compose/dlstreamer/compose-gpu-dri-queuing.yml"

# S_IFMT / S_IFCHR as mode bits (stat.S_IFMT is a function in Python 3).
_S_IFMT = 0o170000
_S_IFCHR = 0o020000


def _fake_char_device_stat(target_path):
  """Return an os.stat stand-in that reports *target_path* as a char device."""
  real_stat = os.stat

  def fake_stat(path, *args, **kwargs):
    result = real_stat(path, *args, **kwargs)
    if os.path.abspath(path) == os.path.abspath(target_path):
      mode = (result.st_mode & ~_S_IFMT) | _S_IFCHR
      return os.stat_result((
        mode, result.st_ino, result.st_dev, result.st_nlink, result.st_uid,
        result.st_gid, result.st_size, result.st_atime, result.st_mtime,
        result.st_ctime,
      ))
    return result

  return fake_stat


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


def test_resolve_compose_files_skips_non_char_entries(tmp_path):
  """Regular files under dri_path are not usable DRM nodes."""
  dri = tmp_path / "dri"
  dri.mkdir()
  (dri / "card0").write_text("")
  assert _host_has_dri(str(dri)) is False
  files = resolve_compose_files((_RETAIL,), dri_path=str(dri))
  assert files == (_RETAIL,)
  assert _RETAIL_DRI not in files


def test_resolve_compose_files_appends_overrides_for_char_devices(tmp_path):
  """Character device nodes under dri_path enable matching GPU overrides."""
  dri = tmp_path / "dri"
  dri.mkdir()
  card = dri / "card0"
  card.write_text("")

  with patch("tests.utils.profiles.os.stat", side_effect=_fake_char_device_stat(card)):
    assert _host_has_dri(str(dri)) is True
    files = resolve_compose_files((_OTHER, _RETAIL, _QUEUING), dri_path=str(dri))

  assert _RETAIL_DRI in files
  assert _QUEUING_DRI in files
  assert files.index(_RETAIL) < files.index(_RETAIL_DRI)
