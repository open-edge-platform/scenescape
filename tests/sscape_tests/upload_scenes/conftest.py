# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Shared fixtures for upload_scenes unit tests.

Adds tools/upload_scenes to sys.path so uploader.py can be imported directly
without Docker or a container install.
"""

import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_UPLOAD_SCENES_DIR = _REPO_ROOT / "tools" / "upload_scenes"

if str(_UPLOAD_SCENES_DIR) not in sys.path:
  sys.path.insert(0, str(_UPLOAD_SCENES_DIR))

from uploader import SceneScapeClient  # noqa: E402


@pytest.fixture
def scene_zip(tmp_path):
  """Factory writing a scene archive containing a single ``<name>.json``."""
  def _make(scene, filename="scene.zip", extra_files=None):
    zip_path = tmp_path / filename
    with zipfile.ZipFile(zip_path, "w") as archive:
      if scene is not None:
        archive.writestr(f"{scene.get('name', 'scene')}.json", json.dumps(scene))
      for name, content in (extra_files or {}).items():
        archive.writestr(name, content)
    return zip_path
  return _make


@pytest.fixture
def fake_client():
  """A SceneScapeClient double with the defaults most tests want."""
  client = MagicMock(spec=SceneScapeClient)
  client.asset_exists.return_value = False
  client.scene_uid.return_value = None
  client.calibration_marker_exists.return_value = False
  client.import_scene.return_value = {}
  return client
