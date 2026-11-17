# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.test import TestCase
from django.urls import reverse
from manager.models import Scene
from django.contrib.auth.models import User
from django.test.client import RequestFactory

class SceneUpdateTestCase(TestCase):
  def setUp(self):
    self.factory = RequestFactory()
    request = self.factory.get('/')
    self.user = User.objects.create_superuser('test_user', 'test_user@intel.com', 'testpassword')
    self.client.post(reverse('sign_in'), data = {'username': 'test_user', 'password': 'testpassword', 'request': request})
    testScene = Scene.objects.create(name = "test_scene")
    self.test_scene_id = testScene.id

  def test_scene_update_page(self):
    response = self.client.get(reverse('scene_update', args=[self.test_scene_id]), data = {'name': 'test_scene_updated'})
    self.assertEqual(response.status_code, 200)
    self.assertTemplateUsed(response, 'scene/scene_update.html')

  def test_scene_update_page_exposes_generated_mesh_rotation(self):
    response = self.client.get(reverse('scene_update', args=[self.test_scene_id]))
    html = ' '.join(response.content.decode().split())
    self.assertIn(f'id="generatedMeshRotationX" value="{Scene.DEFAULT_MESH_ROTATION}"', html)

  def test_scene_update_transform_inputs_disable_autocomplete(self):
    response = self.client.get(reverse('scene_update', args=[self.test_scene_id]))
    form = response.context['form']
    for name in ('rotation_x', 'rotation_y', 'rotation_z', 'translation_x', 'translation_y', 'translation_z'):
      self.assertEqual(form.fields[name].widget.attrs['autocomplete'], 'off')
