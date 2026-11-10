# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Scene.map replacement must invalidate AprilTag registration state."""

from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Model
from django.utils import timezone

from manager.models import Scene
from scene_common.options import APRILTAG


def _scene_with_map(map_name="scene.png"):
  """Build an unsaved Scene with a named map but no MEDIA_ROOT I/O."""
  scene = Scene(name="map_invalidate_scene", scale=100.0, camera_calibration=APRILTAG)
  scene.pk = 1
  scene.id = 1
  scene.map = map_name
  scene._original_map = scene.map.name
  scene._original_polycam_data = scene.polycam_data
  return scene


def test_original_map_snapshot_does_not_follow_fieldfile_mutation():
  scene = Scene(name="snapshot", map="original.png")
  scene.map.name = "replacement.png"
  assert scene._original_map == "original.png"


@patch("manager.models.sendUpdateCommand")
@patch.object(Model, "save")
def test_replacing_map_clears_map_processed(mock_model_save, _mock_cmd):
  scene = _scene_with_map("map_a.png")
  scene.map_processed = timezone.now()
  assert scene.map_processed is not None

  new_map = MagicMock()
  new_map.name = "map_b.png"
  new_map.path = "/tmp/map_b.png"
  scene.map = new_map

  scene.save(send_update_command=False)

  assert scene.map_processed is None
  mock_model_save.assert_called()


@patch("manager.models.sendUpdateCommand")
@patch.object(Model, "save")
def test_reuploading_same_map_name_clears_map_processed(mock_model_save, _mock_cmd):
  scene = Scene(name="map_same_name_scene", scale=100.0, camera_calibration=APRILTAG)
  scene.pk = 1
  scene.id = 1
  scene.map = "Queuing.png"
  scene._original_map = scene.map.name
  scene._original_polycam_data = scene.polycam_data
  scene.map_processed = timezone.now()
  scene.default_source_map_id = 1

  scene.map = SimpleUploadedFile("Queuing.png", b"new map bytes")
  assert scene.map == scene._original_map

  with patch.object(Scene, "regenerateThumbnail", return_value=False):
    scene.save(send_update_command=False)

  assert scene.map_processed is None
  assert scene.default_source_map_id is None
  mock_model_save.assert_called()


@patch("manager.models.sendUpdateCommand")
@patch.object(Model, "save")
def test_name_only_update_keeps_map_processed(mock_model_save, _mock_cmd):
  scene = _scene_with_map("map_keep.png")
  processed_at = timezone.now()
  scene.map_processed = processed_at

  scene.name = "map_keep_processed_scene_renamed"
  scene.save(send_update_command=False)

  assert scene.map_processed == processed_at
  mock_model_save.assert_called()
