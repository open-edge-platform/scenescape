# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.contrib.auth.models import User
from django.test import TestCase
from django.test.client import RequestFactory
from django.urls import reverse

from manager.models import Cam, Scene
from manager.serializers import CamSerializer

TEST_NAME = "NEX-T10402"


class CamUpdateTestCase(TestCase):
  def setUp(self):
    self.factory = RequestFactory()
    request = self.factory.get('/')
    self.user = User.objects.create_superuser('test_user', 'test_user@intel.com', 'testpassword')
    self.client.post(reverse('sign_in'), data = {'username': 'test_user', 'password': 'testpassword', 'request': request})
    testScene = Scene.objects.create(name = "test_scene", map = "test_map")
    testCam = Cam.objects.create(sensor_id="100", name="test_camera", scene = testScene)

  def test_cam_update_page(self):
    response = self.client.post(reverse('cam_update', args=['1']), data = {'sensor_id': '100', 'name': 'test_camera_updated'})
    self.assertEqual(response.status_code, 200)


class CamSerializerPartialUpdateTestCase(TestCase):
  def setUp(self):
    self.scene = Scene.objects.create(name='camera_scene')
    self.other_scene = Scene.objects.create(name='other_scene')
    self.cam = Cam.objects.create(
      sensor_id='camera1', name='Camera 1', scene=self.scene)

  def test_create_without_name_is_rejected(self):
    serializer = CamSerializer(data={'scene': str(self.scene.pk)})
    self.assertFalse(serializer.is_valid())
    self.assertIn('name', serializer.errors)

  def test_partial_update_scene_without_name_succeeds(self):
    serializer = CamSerializer(
      self.cam, data={'scene': str(self.other_scene.pk)}, partial=True)
    self.assertTrue(serializer.is_valid(), serializer.errors)
    updated = serializer.save()
    self.assertEqual(str(updated.scene.pk), str(self.other_scene.pk))
    self.assertEqual(updated.name, 'Camera 1')

  def test_partial_update_empty_name_is_rejected(self):
    serializer = CamSerializer(self.cam, data={'name': '  '}, partial=True)
    self.assertFalse(serializer.is_valid())
    self.assertIn('name', serializer.errors)
