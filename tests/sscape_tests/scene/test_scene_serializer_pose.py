# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""SceneSerializer pose vectors keep stored components, defaulting only NULLs."""

from types import SimpleNamespace

import pytest

from manager.serializers import SceneSerializer


@pytest.mark.parametrize("getter, attrs, expected", [
  ("get_rotation", ("rotation_x", "rotation_y", "rotation_z"), [0.0, 90.0, 0.0]),
  ("get_rotation", ("rotation_x", "rotation_y", "rotation_z"), [0.0, 0.0, 0.0]),
  ("get_translation", ("translation_x", "translation_y", "translation_z"), [0.0, 0.0, 2.0]),
  ("get_scale", ("scale_x", "scale_y", "scale_z"), [0.0, 2.0, 1.0]),
])
def test_stored_components_are_returned_as_is(getter, attrs, expected):
  obj = SimpleNamespace(**dict(zip(attrs, expected)))
  assert getattr(SceneSerializer(), getter)(obj) == expected


@pytest.mark.parametrize("getter, attrs, stored, expected", [
  ("get_rotation", ("rotation_x", "rotation_y", "rotation_z"),
   [None, 90.0, None], [0, 90.0, 0]),
  ("get_translation", ("translation_x", "translation_y", "translation_z"),
   [None, None, None], [0, 0, 0]),
  ("get_scale", ("scale_x", "scale_y", "scale_z"),
   [None, 2.0, None], [1, 2.0, 1]),
])
def test_null_components_default_without_leaking_none(getter, attrs, stored, expected):
  obj = SimpleNamespace(**dict(zip(attrs, stored)))
  result = getattr(SceneSerializer(), getter)(obj)
  assert result == expected
  assert None not in result
