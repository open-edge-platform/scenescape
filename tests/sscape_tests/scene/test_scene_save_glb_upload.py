# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Scene.save() for direct GLB uploads applies the y-up to z-up auto-align only when the map changes."""

from unittest.mock import MagicMock, patch

import pytest
from django.db import models as django_models
from django.db.models.fields.files import FieldFile

from manager.models import Scene


def _map_file(name, path, committed=False):
  map_file = MagicMock()
  map_file.name = name
  map_file.path = path
  map_file._committed = committed
  return map_file


def _save_scene(scene):
  with patch.object(Scene, "autoAlignSceneMap") as auto_align, \
       patch.object(Scene, "saveThumbnail") as save_thumbnail, \
       patch.object(django_models.Model, "save"):
    scene.save(send_update_command=False)
  return auto_align, save_thumbnail


def test_direct_glb_upload_auto_aligns():
  scene = Scene(name="glb_scene")
  scene.map = _map_file("scene.glb", "/media/maps/scene.glb")

  auto_align, save_thumbnail = _save_scene(scene)

  auto_align.assert_called_once_with()
  save_thumbnail.assert_called_once()


def test_saving_unchanged_glb_scene_skips_align_and_thumbnail():
  glb = FieldFile(None, Scene._meta.get_field("map"), "scene.glb")
  scene = Scene(name="glb_scene", map=glb)

  auto_align, save_thumbnail = _save_scene(scene)

  auto_align.assert_not_called()
  save_thumbnail.assert_not_called()


@pytest.mark.django_db
def test_polycam_zip_upload_still_auto_aligns():
  zip_map = _map_file("dataset.zip", "/media/maps/dataset.zip")
  zip_map.save.side_effect = lambda *args, **kwargs: setattr(zip_map, "path", "/media/maps/glb_scene.glb")
  zip_archive = MagicMock()
  zip_archive.namelist.return_value = ["dataset/mesh_info.json"]
  zip_archive.read.return_value = b"glb-bytes"
  scene = Scene(name="glb_scene")
  scene.map = zip_map

  with patch("manager.models.zipfile.ZipFile") as zip_cls:
    zip_cls.return_value.__enter__.return_value = zip_archive
    auto_align, save_thumbnail = _save_scene(scene)

  auto_align.assert_called()
  save_thumbnail.assert_called_once()
