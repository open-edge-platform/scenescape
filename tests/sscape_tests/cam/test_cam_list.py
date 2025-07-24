# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from django.test import TestCase
from django.urls import reverse
from manager.models import Cam, Scene
from django.contrib.auth.models import User
from django.test.client import RequestFactory


class CamListTestCase(TestCase):
  def setUp(self):
    self.factory = RequestFactory()
    request = self.factory.get('/')
    self.user = User.objects.create_user('test_user', 'test_user@intel.com', 'testpassword')
    self.client.post(reverse('sign_in'), data = {'username': 'test_user', 'password': 'testpassword', 'request': request})
    scene = Scene.objects.create(name = "test_scene", map = "test_map")
    Cam.objects.create(sensor_id="100", name="test_camera", scene = scene)

  def test_cam_list_page(self):
    response = self.client.get(reverse('cam_list'))
    self.assertEqual(response.status_code, 200)
