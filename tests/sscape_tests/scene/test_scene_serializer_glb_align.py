# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""REST scene create/update GLB auto-align and explicit mesh transform handling."""

from unittest.mock import MagicMock, patch

from manager.serializers import SceneSerializer


def _glb_map_file(name="scene.glb", committed=True):
  map_file = MagicMock()
  map_file.name = name
  map_file._committed = committed
  return map_file


def _scene_instance(map_file):
  instance = MagicMock()
  instance.pk = "scene-pk"
  instance.map = map_file
  instance._original_map = map_file
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
  instance._original_map = instance.map

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
  serializer.initial_data = {"name": "glb_scene", "map": map_file}
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
def test_update_with_unchanged_glb_skips_auto_align(mock_scene_cls, _mock_mesh_xform):
  map_file = _glb_map_file()
  instance = _scene_instance(map_file)

  mock_scene_cls.objects.filter.return_value.update = MagicMock()

  serializer = SceneSerializer()
  serializer.initial_data = {"name": "glb_scene", "map": map_file}

  serializer.create_update({"name": "glb_scene", "map": map_file}, instance=instance)

  instance.autoAlignSceneMap.assert_not_called()
  instance.saveThumbnail.assert_called_once()
  # Unchanged map still goes through save(); _original_map sync only on change.
  instance.save.assert_called_once()


@patch.object(SceneSerializer, "handleMeshTransform")
@patch("manager.serializers.Scene")
def test_update_with_new_glb_assigns_map_and_auto_aligns(
    mock_scene_cls, _mock_mesh_xform
):
  old_map = _glb_map_file("old.glb")
  new_map = _glb_map_file("new.glb", committed=False)
  instance = _scene_instance(old_map)
  instance._original_map = old_map

  mock_scene_cls.objects.filter.return_value.update = MagicMock()

  serializer = SceneSerializer()
  serializer.initial_data = {"name": "glb_scene", "map": new_map}

  serializer.create_update({"name": "glb_scene", "map": new_map}, instance=instance)

  assert instance.map is new_map
  instance.autoAlignSceneMap.assert_called_once()
  instance.saveThumbnail.assert_called_once()
  # Prevent model.save() from aligning again after explicit handling.
  assert instance._original_map is instance.map
  instance.save.assert_called_once()


@patch.object(SceneSerializer, "handleMeshTransform")
@patch("manager.serializers.Scene")
def test_update_with_new_glb_preserves_explicit_mesh_transforms(
    mock_scene_cls, _mock_mesh_xform
):
  old_map = _glb_map_file("old.glb")
  new_map = _glb_map_file("new.glb", committed=False)
  instance = _scene_instance(old_map)
  instance._original_map = old_map

  mock_scene_cls.objects.filter.return_value.update = MagicMock()

  serializer = SceneSerializer()
  serializer.initial_data = {"name": "glb_scene", "map": new_map}
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
  assert instance._original_map is instance.map
