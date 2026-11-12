# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for child-scene transform output handling."""

import pytest

from manager.models import ChildScene, Scene
from manager.serializers import ChildSceneSerializer

pytestmark = pytest.mark.django_db


@pytest.fixture
def child_link():
  parent = Scene.objects.create(name="Parent scene")
  child = Scene.objects.create(name="Child scene")
  return ChildScene.objects.create(parent=parent, child=child, child_type="local")


def test_transform_is_ignored_on_input_and_returned_on_output(child_link):
  original = [getattr(child_link, f"transform{index}") for index in range(1, 17)]
  serializer = ChildSceneSerializer(
    child_link,
    data={
      "child_type": "local",
      "child": child_link.child_id,
      "transform": {"translation": [1, 2, 3], "rotation": [0, 0, 90], "scale": [2, 2, 2]},
    },
    partial=True,
  )

  serializer.is_valid(raise_exception=True)
  updated = serializer.save()

  assert [getattr(updated, f"transform{index}") for index in range(1, 17)] == original
  assert ChildSceneSerializer(updated).data["transform"] == {
    "translation": [0.0, 0.0, 0.0],
    "rotation": [0.0, 0.0, 0.0],
    "scale": [1.0, 1.0, 1.0],
  }