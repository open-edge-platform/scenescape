# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from unittest.mock import patch

from manager.models import Cam, Scene
from manager.forms import CamCreateForm, CamCalibrateForm
from manager.serializers import CamSerializer, SceneSerializer
from manager.scene_import import ImportScene
from scene_common.options import EULER, QUATERNION, POINT_CORRESPONDENCE
from scene_common.scenescape import SceneLoader

# [tx, ty, tz, qx, qy, qz, qw, sx, sy, sz]
INITIAL_TRANSFORMS = [1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0]
UPDATED_EULER_TRANSFORMS = [1.0000001, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0]
# Four 2D camera points followed by four 3D map points.
POINT_CORRESPONDENCE_TRANSFORMS = [
  278.0, 61.0, 621.0, 132.0, 559.0, 460.0, 66.0, 289.0,
  0.1, 5.38, 0.0, 3.04, 5.35, 0.0, 3.05, 2.42, 0.0, 0.1, 2.45, 0.0,
]
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

  def test_pose_locked_defaults_and_round_trips(self):
    self.assertEqual(self.cam.pose_locked, False)
    serializer = CamSerializer(self.cam, partial=True, data={'pose_locked': True})
    self.assertTrue(serializer.is_valid(), serializer.errors)
    serializer.save()
    self.cam.refresh_from_db()
    self.assertEqual(self.cam.pose_locked, True)
    self.assertEqual(CamSerializer(self.cam).data['pose_locked'], True)
    self.assertEqual(SceneSerializer(self.scene).data['cameras'][0]['pose_locked'], True)
    camera = self.scene.scenescapeScene.cameraWithID(self.cam.sensor_id)
    self.assertEqual(camera.pose_locked, True)
    self.assertEqual(camera.serialize()['pose_locked'], True)
    serializer = CamSerializer(self.cam, partial=True, data={'name': 'Renamed'})
    self.assertTrue(serializer.is_valid(), serializer.errors)
    serializer.save()
    self.cam.refresh_from_db()
    self.assertEqual(self.cam.pose_locked, True)

  def test_invalid_pose_locked_does_not_change_camera(self):
    for value in [None, '', 'dynamic', []]:
      with self.subTest(value=value):
        serializer = CamSerializer(self.cam, partial=True, data={'pose_locked': value})
        self.assertFalse(serializer.is_valid())
        self.assertIn('pose_locked', serializer.errors)
        self.cam.refresh_from_db()
        self.assertEqual(self.cam.pose_locked, False)

  def test_archive_camera_lock_round_trip_and_legacy_default(self):
    self.cam.pose_locked = True
    self.cam.save()
    exported = dict(CamSerializer(self.cam).data)
    with patch.object(ImportScene, 'extractZip'), patch('manager.scene_import.RESTClient'):
      importer = ImportScene('unused.zip', None)
    for legacy in [False, True]:
      with self.subTest(legacy=legacy):
        camera_data = dict(exported, uid=f'imported-{legacy}', name=f'Imported {legacy}')
        if legacy:
          camera_data.pop('pose_locked', None)
        imported = importer.build_camera_items({'cameras': [camera_data]})[0]
        serializer = CamSerializer(data=imported)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        camera = serializer.save()
        self.assertEqual(camera.pose_locked, False if legacy else True)

  def test_camera_forms_expose_lock_and_defaults(self):
    self.cam.pose_locked = True
    self.cam.save()
    for form_class in [CamCreateForm, CamCalibrateForm]:
      with self.subTest(form=form_class.__name__):
        self.assertIn('pose_locked', form_class(instance=self.cam).fields)
    saved = CamCalibrateForm(instance=self.cam).save(commit=False)
    self.assertEqual(saved.pose_locked, True)
    form = CamCreateForm(data={'sensor_id': 'new-lock', 'name': 'New lock'})
    self.assertTrue(form.is_valid(), form.errors)
    self.assertEqual(form.save().pose_locked, False)

  def test_pose_policy_is_rejected(self):
    self.cam.pose_locked = False
    self.cam.save()
    serializer = CamSerializer(
      self.cam, partial=True, data={'pose_policy': 'configured'})
    self.assertFalse(serializer.is_valid())
    self.assertIn('pose_policy', serializer.errors)
    self.cam.refresh_from_db()
    self.assertEqual(self.cam.pose_locked, False)

  def test_calibration_page_renders_pose_locked_checkbox(self):
    user = User.objects.create_superuser('pose-lock-user', 'pose@example.com', 'password')
    self.client.force_login(user)

    response = self.client.get(reverse('cam_calibrate', args=[self.cam.pk]))

    self.assertEqual(response.status_code, 200)
    self.assertContains(response, 'id="pose_locked_wrapper"')
    self.assertContains(response, 'id="id_pose_locked"')
    self.assertContains(response, 'Pose locked')
    self.assertContains(response, 'live MQTT extrinsics and optics')
    self.assertNotContains(response, 'Pose policy')

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

  def test_scene_reassignment_with_pose_keeps_supplied_pose(self):
    """Re-linking a camera with calibration in the same update (scene import)
    must persist the supplied calibration points instead of clearing them."""
    new_scene = Scene.objects.create(name="import_scene", scale=100.0)
    serializer = CamSerializer(
      self.cam,
      data={
        "name": self.cam.name,
        "scene": str(new_scene.pk),
        "transform_type": POINT_CORRESPONDENCE,
        "transforms": POINT_CORRESPONDENCE_TRANSFORMS,
      },
      partial=True,
    )

    self.assertTrue(serializer.is_valid(), serializer.errors)
    serializer.save()

    persisted = Cam.objects.get(pk=self.cam.pk)
    self.assertEqual(persisted.scene, new_scene)
    self.assertEqual(persisted.transform_type, POINT_CORRESPONDENCE)
    self.assertEqual(persisted.transforms, POINT_CORRESPONDENCE_TRANSFORMS)
    self.assertFalse(getattr(self.cam, "_pose_supplied", False))
    return

  def test_scene_only_api_relink_clears_previous_pose(self):
    """A scene-only API update must still drop the previous scene's pose."""
    new_scene = Scene.objects.create(name="relink_scene", scale=100.0)
    serializer = CamSerializer(self.cam, data={"scene": str(new_scene.pk)}, partial=True)

    self.assertTrue(serializer.is_valid(), serializer.errors)
    serializer.save()

    persisted = Cam.objects.get(pk=self.cam.pk)
    self.assertEqual(persisted.scene, new_scene)
    self.assertEqual(persisted.transforms, [])
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
    self.assertEqual(camera.intrinsics_cx, 320.0)
    self.assertEqual(camera.intrinsics_cy, 240.0)

  def test_api_create_with_1280x720_centers_principal_point(self):
    """API create with demo video resolution and no cx/cy centers the frame."""
    camera = self.register(resolution=[1280, 720])
    camera.refresh_from_db()
    self.assertEqual([camera.width, camera.height], [1280, 720])
    self.assertEqual(camera.intrinsics_cx, 640.0)
    self.assertEqual(camera.intrinsics_cy, 360.0)
    self.assertEqual(
      CamSerializer(camera).data['intrinsics']['cx'], 640.0)
    self.assertEqual(
      CamSerializer(camera).data['intrinsics']['cy'], 360.0)

  def test_api_create_with_resolution_object_centers_principal_point(self):
    camera = self.register(resolution={'width': 1280, 'height': 720})
    self.assertEqual([camera.intrinsics_cx, camera.intrinsics_cy], [640.0, 360.0])

  def test_orm_create_with_resolution_centers_principal_point(self):
    """UI/ORM create path (Cam.save) centers cx/cy on the registered frame."""
    scene = Scene.objects.create(name="cxcy_scene", scale=100.0)
    camera = Cam.objects.create(
      sensor_id="cxcy_cam",
      name="CxCy Cam",
      type="camera",
      scene=scene,
      width=1280,
      height=720,
    )
    camera.refresh_from_db()
    self.assertEqual([camera.intrinsics_cx, camera.intrinsics_cy], [640.0, 360.0])

  def test_create_form_default_resolution_keeps_legacy_center(self):
    scene = Scene.objects.create(name="form_cxcy_scene", scale=100.0)
    form = CamCreateForm(data={
      'sensor_id': 'form_cxcy',
      'name': 'Form CxCy',
      'scene': scene.pk,
      'pose_locked': False,
    })
    self.assertTrue(form.is_valid(), form.errors)
    camera = form.save()
    self.assertEqual([camera.width, camera.height], [640, 480])
    self.assertEqual([camera.intrinsics_cx, camera.intrinsics_cy], [320.0, 240.0])

  def test_explicit_off_center_principal_point_is_preserved(self):
    camera = self.register(
      resolution=[1280, 720],
      intrinsics={'fx': 900, 'fy': 900, 'cx': 610, 'cy': 350},
    )
    self.assertEqual([camera.intrinsics_cx, camera.intrinsics_cy], [610.0, 350.0])

  def test_non_optical_updates_still_require_name(self):
    camera = self.register()
    serializer = CamSerializer(camera, partial=True, data={'threshold': 0.6})
    self.assertFalse(serializer.is_valid())
    self.assertIn('name', serializer.errors)
