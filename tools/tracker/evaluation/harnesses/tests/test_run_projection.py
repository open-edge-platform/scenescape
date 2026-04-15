# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for run_projection.py pure-Python helpers.

``run_projection.py`` imports ``scene_common`` at module level, which is only
available inside the SceneScape Docker container.  The two helper functions
being tested here — ``_build_class_map`` and ``_apply_size_offset`` — are
pure Python and have no runtime dependency on ``scene_common``.  We mock the
module during import so the tests can run in the regular dev venv.
"""

import importlib.util
import math
import sys
from pathlib import Path
from types import ModuleType
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
_apply_size_offset = _rp._apply_size_offset
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


# ---------------------------------------------------------------------------
# Tests for _apply_size_offset
# ---------------------------------------------------------------------------

class TestApplySizeOffset:
  def test_zero_sizes_returns_unchanged(self):
    """When both sizes are zero the position is unchanged."""
    wx, wy = _apply_size_offset(5.0, 3.0, 0.0, 0.0, 0.0, 0.0)
    assert wx == pytest.approx(5.0)
    assert wy == pytest.approx(3.0)

  def test_object_north_of_camera(self):
    """Camera at origin, object directly north (+Y). Offset pushes further north."""
    # offset = (2 + 2) / 4 = 1.0 m;  direction = (0, 1)
    wx, wy = _apply_size_offset(0.0, 5.0, 0.0, 0.0, 2.0, 2.0)
    assert wx == pytest.approx(0.0)
    assert wy == pytest.approx(6.0)

  def test_object_east_of_camera(self):
    """Camera at origin, object directly east (+X). Offset pushes further east."""
    # offset = (0 + 4) / 4 = 1.0 m;  direction = (1, 0)
    wx, wy = _apply_size_offset(5.0, 0.0, 0.0, 0.0, 0.0, 4.0)
    assert wx == pytest.approx(6.0)
    assert wy == pytest.approx(0.0)

  def test_diagonal_direction(self):
    """Object at 45°; pushed along the same diagonal."""
    # Camera at origin, object at (3, 4) → dist=5, unit=(0.6, 0.8)
    # offset = (2 + 2) / 4 = 1.0 m
    wx, wy = _apply_size_offset(3.0, 4.0, 0.0, 0.0, 2.0, 2.0)
    assert wx == pytest.approx(3.0 + 0.6)
    assert wy == pytest.approx(4.0 + 0.8)

  def test_degenerate_same_position_as_camera(self):
    """Object at exact camera position: unchanged (avoids division by zero)."""
    wx, wy = _apply_size_offset(1.0, 1.0, 1.0, 1.0, 2.0, 2.0)
    assert wx == pytest.approx(1.0)
    assert wy == pytest.approx(1.0)

  def test_offset_magnitude(self):
    """Distance from camera increases by exactly the computed offset."""
    cam_tx, cam_ty = 0.0, 0.0
    x_size, y_size = 1.0, 3.0
    expected_offset = (x_size + y_size) / 4.0  # 1.0

    wx_in, wy_in = 0.0, 10.0
    wx_out, wy_out = _apply_size_offset(wx_in, wy_in, cam_tx, cam_ty, x_size, y_size)

    dist_in = math.sqrt((wx_in - cam_tx) ** 2 + (wy_in - cam_ty) ** 2)
    dist_out = math.sqrt((wx_out - cam_tx) ** 2 + (wy_out - cam_ty) ** 2)
    assert dist_out == pytest.approx(dist_in + expected_offset)
