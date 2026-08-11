# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json

from django.test import TestCase
from django.urls import reverse
from manager.models import Scene
from manager.serializers import SceneSerializer
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
    response = self.client.get(
      reverse('scene_update', args=[self.test_scene_id]),
      data = {'name': 'test_scene_updated'})
    self.assertEqual(response.status_code, 302)
    self.assertEqual(
      response.url, f"/{self.test_scene_id}/?ss=scene-manage")

  def test_map_corners_lla_json_string_is_parsed(self):
    scene = Scene.objects.get(pk=self.test_scene_id)
    corners = [
      [37.0, -122.0, 0],
      [37.1, -122.0, 0],
      [37.1, -121.9, 0],
      [37.0, -121.9, 0],
    ]
    serializer = SceneSerializer(
      instance=scene,
      data={
        'name': scene.name,
        'output_lla': True,
        'map_corners_lla': json.dumps(corners),
      },
      partial=True)
    self.assertTrue(serializer.is_valid(), serializer.errors)
    self.assertEqual(serializer.validated_data['map_corners_lla'], corners)

  def test_output_lla_accepts_lowercase_true_string(self):
    scene = Scene.objects.get(pk=self.test_scene_id)
    corners = [
      [37.0, -122.0, 0],
      [37.1, -122.0, 0],
      [37.1, -121.9, 0],
      [37.0, -121.9, 0],
    ]
    serializer = SceneSerializer(
      instance=scene,
      data={
        'name': scene.name,
        'output_lla': 'true',
        'map_corners_lla': json.dumps(corners),
      },
      partial=True)
    self.assertTrue(serializer.is_valid(), serializer.errors)
    self.assertIs(serializer.validated_data['output_lla'], True)

  def test_output_lla_rejects_unknown_choice(self):
    scene = Scene.objects.get(pk=self.test_scene_id)
    serializer = SceneSerializer(
      instance=scene,
      data={
        'name': scene.name,
        'output_lla': 'not-a-bool',
      },
      partial=True)
    self.assertFalse(serializer.is_valid())
    self.assertIn('output_lla', serializer.errors)

  def test_map_corners_lla_invalid_string_is_rejected(self):
    scene = Scene.objects.get(pk=self.test_scene_id)
    serializer = SceneSerializer(
      instance=scene,
      data={
        'name': scene.name,
        'map_corners_lla': 'not-json',
      },
      partial=True)
    self.assertFalse(serializer.is_valid())
    self.assertIn('map_corners_lla', serializer.errors)
