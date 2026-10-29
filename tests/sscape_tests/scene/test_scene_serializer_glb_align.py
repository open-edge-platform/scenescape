# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""REST scene create/update GLB auto-align and explicit mesh transform handling."""

from unittest.mock import MagicMock, patch

import pytest
from django.http import QueryDict
from rest_framework.exceptions import ValidationError

from manager.serializers import SceneSerializer


@pytest.mark.parametrize("value", [[1, 2.5, -3], (1, 2.5, -3), "[1, 2.5, -3]"])
def test_mesh_transform_accepts_json_vector_forms(value):
  data = {"mesh_translation": value, "name": "untouched"}
  validated = {}
  SceneSerializer().handleMeshTransform(data, validated)
  assert validated == {"translation_x": 1.0, "translation_y": 2.5, "translation_z": -3.0}
  assert data == {"name": "untouched"}


def test_mesh_transform_accepts_multipart_vector():
  data = QueryDict("mesh_rotation=%5B1%2C2%2C3%5D", mutable=True)
  validated = {}
  SceneSerializer().handleMeshTransform(data, validated)
  assert validated == {"rotation_x": 1.0, "rotation_y": 2.0, "rotation_z": 3.0}


@pytest.mark.parametrize("value", [
  None, "not-json", "[1,2]", {"x": 1}, [1, 2, 3, 4], [True, 2, 3], [1, "2", 3],
  [float("nan"), 2, 3], [1, float("inf"), 3],
])
def test_mesh_transform_rejects_malformed_vectors(value):
  with pytest.raises(ValidationError) as exc:
    SceneSerializer().handleMeshTransform({"mesh_scale": value}, {})
  assert "mesh_scale" in exc.value.detail


def test_mesh_transform_omission_preserves_validated_data():
  validated = {"name": "unchanged"}
  SceneSerializer().handleMeshTransform({}, validated)
  assert validated == {"name": "unchanged"}


@pytest.fixture(autouse=True)
def _skip_source_map_storage(monkeypatch):
  monkeypatch.setattr(SceneSerializer, "_record_source_map", MagicMock())


def _glb_map_file(name="scene.glb", committed=True):
  map_file = MagicMock()
  map_file.name = name
  map_file._committed = committed
  return map_file


def _scene_instance(map_file):
  instance = MagicMock()
  instance.pk = "scene-pk"
  instance.map = map_file
  instance._original_map = map_file.name
  map_file.save.side_effect = lambda name, upload, save=False: setattr(map_file, "name", upload.name)
  instance.thumbnail = "thumb.png"
  instance.scale = 100.0
  instance.rotation_x = 0.0
  instance.rotation_y = 0.0
  instance.rotation_z = 0.0
  instance.translation_x = 0.0
  instance.translation_y = 0.0
  instance.translation_z = 0.0
  instance.parent = None
  instance.save = MagicMock()
  return instance


@patch.object(SceneSerializer, "handleMeshTransform")
@patch("manager.serializers.transaction.atomic")
@patch("manager.serializers.Scene")
def test_create_with_glb_calls_auto_align_when_original_map_matches(
    mock_scene_cls, _mock_atomic, _mock_mesh_xform
):
  map_file = _glb_map_file()
  instance = _scene_instance(map_file)
  # Create path: __init__ snapshots _original_map from the uploaded map.
  instance._original_map = instance.map.name

  mock_scene_cls.return_value = instance
  mock_scene_cls.objects.bulk_create = MagicMock()
  mock_scene_cls.objects.filter.return_value.update = MagicMock()

  serializer = SceneSerializer()
  serializer.initial_data = {"name": "glb_scene", "map": map_file}

  result = serializer.create_update({"name": "glb_scene", "map": map_file})

  assert result is instance
  instance.autoAlignSceneMap.assert_called_once()
  instance.saveThumbnail.assert_called_once()
  mock_scene_cls.objects.filter.assert_called_with(pk=instance.pk)
  mock_scene_cls.objects.filter.return_value.update.assert_called_once()


@patch.object(SceneSerializer, "handleMeshTransform")
@patch("manager.serializers.transaction.atomic")
@patch("manager.serializers.Scene")
def test_create_with_glb_preserves_explicit_mesh_transforms(
    mock_scene_cls, _mock_atomic, _mock_mesh_xform
):
  map_file = _glb_map_file()
  instance = _scene_instance(map_file)
  mock_scene_cls.return_value = instance
  mock_scene_cls.objects.bulk_create = MagicMock()
  mock_scene_cls.objects.filter.return_value.update = MagicMock()

  serializer = SceneSerializer()
  serializer.initial_data = {
    "name": "glb_scene", "map": map_file,
    "mesh_rotation": [12, 0, 0], "mesh_translation": [0, 3.5, 0],
  }
  validated = {
      "name": "glb_scene",
      "map": map_file,
      "rotation_x": 12.0,
      "translation_y": 3.5,
  }

  serializer.create_update(validated)

  instance.autoAlignSceneMap.assert_not_called()
  assert instance.rotation_x == 12.0
  assert instance.translation_y == 3.5
  instance.saveThumbnail.assert_called_once()


@patch.object(SceneSerializer, "handleMeshTransform")
@patch("manager.serializers.Scene")
def test_update_with_same_name_glb_reupload_auto_aligns(mock_scene_cls, _mock_mesh_xform):
  map_file = _glb_map_file()
  instance = _scene_instance(map_file)

  mock_scene_cls.objects.filter.return_value.update = MagicMock()

  serializer = SceneSerializer()
  serializer.initial_data = {"name": "glb_scene", "map": map_file}

  serializer.create_update({"name": "glb_scene", "map": map_file}, instance=instance)

  instance.autoAlignSceneMap.assert_called_once()
  instance.saveThumbnail.assert_called_once()
  # A same-name upload is still a map replacement.
  instance.save.assert_called_once()


@patch.object(SceneSerializer, "handleMeshTransform")
@patch("manager.serializers.Scene")
def test_update_with_new_glb_assigns_map_and_auto_aligns(
    mock_scene_cls, _mock_mesh_xform
):
  old_map = _glb_map_file("old.glb")
  new_map = _glb_map_file("new.glb", committed=False)
  instance = _scene_instance(old_map)
  instance._original_map = old_map.name

  mock_scene_cls.objects.filter.return_value.update = MagicMock()

  serializer = SceneSerializer()
  serializer.initial_data = {"name": "glb_scene", "map": new_map}

  serializer.create_update({"name": "glb_scene", "map": new_map}, instance=instance)

  assert instance.map.name == new_map.name
  instance.autoAlignSceneMap.assert_called_once()
  instance.saveThumbnail.assert_called_once()
  # Prevent model.save() from aligning again after explicit handling.
  assert instance._original_map == instance.map.name
  instance.save.assert_called_once()


@patch.object(SceneSerializer, "handleMeshTransform")
@patch("manager.serializers.Scene")
def test_update_with_new_glb_preserves_explicit_mesh_transforms(
    mock_scene_cls, _mock_mesh_xform
):
  old_map = _glb_map_file("old.glb")
  new_map = _glb_map_file("new.glb", committed=False)
  instance = _scene_instance(old_map)
  instance._original_map = old_map.name

  mock_scene_cls.objects.filter.return_value.update = MagicMock()

  serializer = SceneSerializer()
  serializer.initial_data = {
    "name": "glb_scene", "map": new_map,
    "mesh_rotation": [45, 0, 0], "mesh_translation": [1.25, 0, 0],
  }
  validated = {
      "name": "glb_scene",
      "map": new_map,
      "rotation_x": 45.0,
      "translation_x": 1.25,
  }

  serializer.create_update(validated, instance=instance)

  instance.autoAlignSceneMap.assert_not_called()
  assert instance.rotation_x == 45.0
  assert instance.translation_x == 1.25
  assert instance._original_map == instance.map.name
