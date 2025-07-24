# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from django.test import TestCase
from django.urls import reverse
from manager.models import SingletonSensor, Scene
from django.contrib.auth.models import User
from django.test.client import RequestFactory

class SingletonSensorListTestCase(TestCase):
  def setUp(self):
    self.factory = RequestFactory()
    request = self.factory.get('/')
    self.user = User.objects.create_user('test_user', 'test_user@intel.com', 'testpassword')
    self.client.post(reverse('sign_in'), data = {'username': 'test_user', 'password': 'testpassword', 'request': request})
    scene = Scene.objects.create(name = "test_scene")
    SingletonSensor.objects.create(sensor_id="100", name="test_sensor", scene = scene)

  def test_singleton_sensor_list_page(self):
    response = self.client.get(reverse('singleton_sensor_list'))
    self.assertEqual(response.status_code, 200)
    self.assertTemplateUsed(response, 'singleton_sensor/singleton_sensor_list.html')
