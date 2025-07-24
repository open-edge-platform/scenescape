# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from django.test import TestCase
from django.urls import reverse
from manager.models import Scene
from django.contrib.auth.models import User
from django.test.client import RequestFactory

class SceneDetailTestCase(TestCase):
  def setUp(self):
    self.factory = RequestFactory()
    request = self.factory.get('/')
    self.user = User.objects.create_superuser('test_user', 'test_user@intel.com', 'testpassword')
    self.client.post(reverse('sign_in'), data = {'username': 'test_user', 'password': 'testpassword', 'request': request})
    testScene = Scene.objects.create(name = "test_scene")
    self.test_scene_id = testScene.id

  def test_scene_detail_page(self):
    response = self.client.get(reverse('sceneDetail', args=[self.test_scene_id]))
    self.assertEqual(response.status_code, 200)
