# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for run_projection.py pure-Python helpers.

``run_projection.py`` imports ``scene_common`` at module level, which is only
available inside the SceneScape Docker container.  The helper function tested
here — ``_build_class_map`` — is pure Python and has no runtime dependency on
``scene_common``.  We mock the module during import so the tests can run in
the regular dev venv.

Note: the size-offset step previously lived in a custom ``_apply_size_offset``
helper.  It is now implemented directly via ``scene_common.geometry.Line`` —
the exact same production code used by ``MovingObject.mapObjectDetectionToWorld``
— so there is no custom math to unit-test here.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Import run_projection with scene_common stubbed out
# ---------------------------------------------------------------------------

def _load_run_projection():
  """Load run_projection.py with scene_common faked out."""
  for mod_name in ("scene_common", "scene_common.transform", "scene_common.geometry"):
    sys.modules.setdefault(mod_name, MagicMock())

  script_path = (
    Path(__file__).parent.parent
    / "camera_projection_harness"
    / "run_projection.py"
  )
  spec = importlib.util.spec_from_file_location("run_projection", script_path)
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)
  return mod


_rp = _load_run_projection()
_build_class_map = _rp._build_class_map
TYPE_1 = _rp.TYPE_1
TYPE_2 = _rp.TYPE_2
DEFAULT_SHIFT_TYPE = _rp.DEFAULT_SHIFT_TYPE
DEFAULT_X_SIZE = _rp.DEFAULT_X_SIZE
DEFAULT_Y_SIZE = _rp.DEFAULT_Y_SIZE


# ---------------------------------------------------------------------------
# Tests for _build_class_map
# ---------------------------------------------------------------------------

class TestBuildClassMap:
  def test_empty_list_returns_empty_dict(self):
    assert _build_class_map([]) == {}

  def test_single_entry_full_fields(self):
    classes = [{"name": "person", "shift_type": 2, "x_size": 0.5, "y_size": 0.3}]
    result = _build_class_map(classes)
    assert result == {"person": {"shift_type": 2, "x_size": 0.5, "y_size": 0.3}}

  def test_name_is_case_folded_to_lowercase(self):
    classes = [{"name": "PERSON"}]
    result = _build_class_map(classes)
    assert "person" in result
    assert "PERSON" not in result

  def test_missing_optional_fields_use_defaults(self):
    classes = [{"name": "thing"}]
    result = _build_class_map(classes)
    assert result["thing"]["shift_type"] == DEFAULT_SHIFT_TYPE
    assert result["thing"]["x_size"] == DEFAULT_X_SIZE
    assert result["thing"]["y_size"] == DEFAULT_Y_SIZE

  def test_entry_without_name_is_skipped(self):
    classes = [{"shift_type": 1, "x_size": 0.5, "y_size": 0.5}]
    result = _build_class_map(classes)
    assert result == {}

  def test_multiple_entries(self):
    classes = [
      {"name": "person", "shift_type": 1, "x_size": 0.5, "y_size": 0.5},
      {"name": "FW190D", "shift_type": 2, "x_size": 1.0, "y_size": 1.0},
    ]
    result = _build_class_map(classes)
    assert set(result.keys()) == {"person", "fw190d"}
    assert result["person"]["shift_type"] == TYPE_1
    assert result["fw190d"]["shift_type"] == TYPE_2

  def test_numeric_types_coerced(self):
    """shift_type is cast to int, sizes to float."""
    classes = [{"name": "obj", "shift_type": "2", "x_size": "1.5", "y_size": "0.5"}]
    result = _build_class_map(classes)
    assert isinstance(result["obj"]["shift_type"], int)
    assert isinstance(result["obj"]["x_size"], float)
    assert isinstance(result["obj"]["y_size"], float)
