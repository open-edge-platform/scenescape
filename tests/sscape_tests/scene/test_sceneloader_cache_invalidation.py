# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.test import TestCase

from manager.models import Cam, Scene
from scene_common.options import QUATERNION
from scene_common.scenescape import SceneLoader

# [tx, ty, tz, qx, qy, qz, qw, sx, sy, sz]
INITIAL_TRANSFORMS = [1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0]
TRANSLATION_DELTA = 5.0


class SceneCameraCacheTestCase(TestCase):
  """Scene cache must reflect camera pose changes from the database."""

  def setUp(self):
    SceneLoader.scenes.clear()
    self.scene = Scene.objects.create(name="camera_cache_scene", scale=100.0)
    self.cam = Cam.objects.create(
      sensor_id="camera_cache_cam",
      name="Camera Cache Cam",
      type="camera",
      scene=self.scene,
      transforms=list(INITIAL_TRANSFORMS),
      transform_type=QUATERNION,
    )
    return

  def tearDown(self):
    SceneLoader.scenes.clear()
    return

  def cachedTranslation(self):
    camera = self.scene.scenescapeScene.cameraWithID(self.cam.sensor_id)
    return camera.pose.translation.asNumpyCartesian.tolist()

  def test_cached_pose_reflects_saved_translation(self):
    """Positive: a saved pose change is visible through the cached scene."""
    self.cachedTranslation()

    transforms = list(self.cam.transforms)
    transforms[0] += TRANSLATION_DELTA
    transforms[1] += TRANSLATION_DELTA
    self.cam.transforms = transforms
    self.cam.save()

    persisted = Cam.objects.get(pk=self.cam.pk).transforms[:3]
    self.assertEqual(persisted, transforms[:3],
                     "precondition failed: the pose was not persisted")

    self.assertEqual(self.cachedTranslation(), persisted,
                     "cached scene returned a pose that no longer matches the database")
    return

  def test_cached_pose_stable_without_save(self):
    """Negative: with no intervening save, repeated reads must not change."""
    first = self.cachedTranslation()
    self.assertEqual(self.cachedTranslation(), first)
    self.assertEqual(first, INITIAL_TRANSFORMS[:3])
    return

  def test_camera_pose_reset_on_scene_reassignment(self):
    """Positive: camera pose must be cleared when reassigned to a different scene."""
    self.assertEqual(self.cam.transforms, INITIAL_TRANSFORMS)
    self.assertIsNone(self.cam.scene_x)
    self.assertIsNone(self.cam.scene_y)
    self.assertIsNone(self.cam.scene_z)

    new_scene = Scene.objects.create(name="new_scene", scale=100.0)

    self.cam.scene = new_scene
    self.cam.save()

    persisted = Cam.objects.get(pk=self.cam.pk)
    self.assertEqual(persisted.transforms, [],
                     "transforms should be cleared when scene is reassigned")
    self.assertIsNone(persisted.scene_x,
                      "scene_x should be None after reassignment")
    self.assertIsNone(persisted.scene_y,
                      "scene_y should be None after reassignment")
    self.assertIsNone(persisted.scene_z,
                      "scene_z should be None after reassignment")
    return
