
# Copyright (C) 2022 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

from django.test import TestCase
from django.urls import reverse
from manager.models import Cam, Scene
from django.contrib.auth.models import User
from django.test.client import RequestFactory

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
