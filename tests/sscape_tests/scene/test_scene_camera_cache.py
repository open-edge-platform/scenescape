# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.test import TestCase
from unittest.mock import patch

from manager.models import Cam, Scene
from manager.serializers import CamSerializer
from scene_common.options import EULER, QUATERNION
from scene_common.scenescape import SceneLoader

# [tx, ty, tz, qx, qy, qz, qw, sx, sy, sz]
INITIAL_TRANSFORMS = [1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0]
UPDATED_EULER_TRANSFORMS = [1.0000001, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0]
TRANSLATION_DELTA = 5.0
TEST_NAME = "NEX-T28217"


class SceneCameraCacheTestCase(TestCase):
  """Scene cache and camera pose must stay consistent with persisted state."""

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

  def test_same_scene_api_update_preserves_pose(self):
    """A 3D UI save in the current scene must persist its Euler pose."""
    serializer = CamSerializer(
      self.cam,
      data={
        "name": self.cam.name,
        "scene": str(self.scene.pk),
        "translation": UPDATED_EULER_TRANSFORMS[:3],
        "rotation": UPDATED_EULER_TRANSFORMS[3:6],
        "scale": UPDATED_EULER_TRANSFORMS[6:9],
        "transform_type": EULER,
      },
    )

    self.assertTrue(serializer.is_valid(), serializer.errors)
    serializer.save()

    persisted = Cam.objects.get(pk=self.cam.pk)
    self.assertEqual(persisted.scene_id, self.scene.pk)
    self.assertEqual(persisted.transforms, UPDATED_EULER_TRANSFORMS)
    self.assertEqual(persisted.transform_type, EULER)
    return

  def test_cached_pose_reflects_saved_translation(self):
    """A saved pose change must be visible through the cached scene."""
    self.cachedTranslation()

    transforms = list(self.cam.transforms)
    transforms[0] += TRANSLATION_DELTA
    transforms[1] += TRANSLATION_DELTA
    self.cam.transforms = transforms
    self.cam.save()

    persisted = Cam.objects.get(pk=self.cam.pk).transforms[:3]
    self.assertEqual(self.cachedTranslation(), persisted)
    return

  def test_camera_pose_reset_on_scene_reassignment(self):
    """A real scene reassignment must clear the previous scene pose."""
    new_scene = Scene.objects.create(name="new_scene", scale=100.0)

    self.cam.scene = new_scene
    self.cam.save()

    persisted = Cam.objects.get(pk=self.cam.pk)
    self.assertEqual(persisted.scene, new_scene)
    self.assertEqual(persisted.transforms, [])
    self.assertIsNone(persisted.scene_x)
    self.assertIsNone(persisted.scene_y)
    self.assertIsNone(persisted.scene_z)
    return

  def test_unpersisted_scene_change_does_not_clear_pose(self):
    """An update_fields save excluding scene must leave the persisted pose unchanged."""
    original_name = self.cam.name
    new_scene = Scene.objects.create(name="pending_scene", scale=100.0)
    self.cam.scene = new_scene
    self.cam.name = "Renamed Camera"

    self.cam.save(update_fields={"name"})

    persisted = Cam.objects.get(pk=self.cam.pk)
    self.assertNotEqual(persisted.name, original_name)
    self.assertEqual(persisted.scene, self.scene)
    self.assertEqual(persisted.transforms, INITIAL_TRANSFORMS)
    return


class CameraOpticsRegistrationTestCase(TestCase):
  def register(self, **fields):
    serializer = CamSerializer(data={'name': 'handheld-optics', **fields})
    self.assertTrue(serializer.is_valid(), serializer.errors)
    return serializer.save()

  def test_registration_without_dimensions_estimates_full_sensor_frame(self):
    with patch('manager.serializers.log.warning') as warning:
      camera = self.register(intrinsics={'fx': 1339, 'fy': 1339, 'cx': 956.14, 'cy': 725.87})
    camera.refresh_from_db()
    self.assertEqual(CamSerializer(camera).data['resolution'], [1912, 1452])
    warning.assert_called_once()

  def test_explicit_off_center_resolution_is_not_inferred(self):
    camera = self.register(
      intrinsics={'fx': 1339, 'fy': 1339, 'cx': 956.14, 'cy': 725.87},
      resolution=[1920, 1440],
    )
    self.assertEqual(CamSerializer(camera).data['resolution'], [1920, 1440])

  def test_intrinsics_only_update_preserves_registered_resolution(self):
    camera = self.register(resolution={'width': 1920, 'height': 1080})
    serializer = CamSerializer(camera, partial=True, data={
      'intrinsics': {'fx': 1000, 'fy': 1010, 'cx': 800, 'cy': 500},
    })
    self.assertTrue(serializer.is_valid(), serializer.errors)
    serializer.save()
    camera.refresh_from_db()
    self.assertEqual([camera.width, camera.height], [1920, 1080])
    self.assertEqual(camera.intrinsics_fx, 1000)

  def test_registration_without_pixel_intrinsics_retains_default(self):
    camera = self.register(intrinsics={'fov': 70})
    self.assertEqual([camera.width, camera.height], [640, 480])

  def test_non_optical_updates_still_require_name(self):
    camera = self.register()
    serializer = CamSerializer(camera, partial=True, data={'threshold': 0.6})
    self.assertFalse(serializer.is_valid())
    self.assertIn('name', serializer.errors)
