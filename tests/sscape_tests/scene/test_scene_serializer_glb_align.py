# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""REST scene create must auto-align GLB maps even when _original_map matches."""

from unittest.mock import MagicMock, patch

from manager.serializers import SceneSerializer


def _glb_map_file(name="scene.glb"):
  map_file = MagicMock()
  map_file.name = name
  return map_file


@patch.object(SceneSerializer, "handleMeshTransform")
@patch("manager.serializers.transaction.atomic")
@patch("manager.serializers.Scene")
def test_create_with_glb_calls_auto_align_when_original_map_matches(
    mock_scene_cls, _mock_atomic, _mock_mesh_xform
):
  map_file = _glb_map_file()
  instance = MagicMock()
  instance.pk = "scene-pk"
  instance.map = map_file
  # Create path: __init__ snapshots _original_map from the uploaded map.
  instance._original_map = instance.map
  instance.thumbnail = "thumb.png"
  instance.scale = 100.0
  instance.rotation_x = 0.0
  instance.rotation_y = 0.0
  instance.rotation_z = 0.0
  instance.translation_x = 0.0
  instance.translation_y = 0.0
  instance.translation_z = 0.0
  instance.parent = None

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
@patch("manager.serializers.Scene")
def test_update_with_unchanged_glb_skips_auto_align(mock_scene_cls, _mock_mesh_xform):
  map_file = _glb_map_file()
  instance = MagicMock()
  instance.pk = "scene-pk"
  instance.map = map_file
  instance._original_map = map_file
  instance.parent = None
  instance.save = MagicMock()

  mock_scene_cls.objects.filter.return_value.update = MagicMock()

  serializer = SceneSerializer()
  serializer.initial_data = {"name": "glb_scene", "map": map_file}

  serializer.create_update({"name": "glb_scene", "map": map_file}, instance=instance)

  instance.autoAlignSceneMap.assert_not_called()
  instance.saveThumbnail.assert_called_once()
