#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import json
from manager import views
from scene_common.geometry import Point
from unittest.mock import Mock
from django.test import TestCase
from django.urls import reverse
from manager.models import Scene, SingletonSensor, Cam
from manager.views import SingletonSensorDeleteView, SingletonSensorCreateView, \
                         SingletonSensorUpdateView, CamCreateView, CamDeleteView, CamUpdateView
from unittest.mock import MagicMock, patch
from django.contrib.auth.models import User
from django.test.client import RequestFactory
from django.test.client import RequestFactory
from manager.settings import AXES_FAILURE_LIMIT

test_scene_id = None

class SetUpTestCases(TestCase):
  def setUp(self):
    self.factory = RequestFactory()
    request = self.factory.get('/')
    self.user = User.objects.create_superuser('test_user', 'test_user@intel.com', 'testpassword')
    self.client.post(reverse('sign_in'), data = {'username': 'test_user', 'password': 'testpassword', 'request': request})

    test_scene = Scene.objects.create(name = "test_scene", map = 'test_map')

    global test_scene_id
    test_scene_id = test_scene.id

    SingletonSensor.objects.create(sensor_id="100", name="test_sensor", scene = test_scene)
    Cam.objects.create(sensor_id="1", name="test_camera", scene = test_scene)
    return

class TestSceneViews(SetUpTestCases):
  def test_scene_detail_page(self):
    global test_scene_id
    response = self.client.get(reverse('sceneDetail', args=[test_scene_id]))
    self.assertEqual(response.status_code, 200)
    return

class TestIndex(TestCase):
  def setUp(self):
    self.factory = RequestFactory()
    request = self.factory.get('/')
    self.user = User.objects.create_superuser('test_user', 'test_user@intel.com', 'testpassword')
    self.client.post(reverse('sign_in'), data = {'username': 'test_user', 'password': 'testpassword', 'request': request})
    global test_scene_id
    Scene.objects.create(name = "test_scene", map=f"/test/{test_scene_id}")
    return

  def test_index(self):
    response = self.client.get('')
    self.assertEqual(response.status_code, 200)
    self.assertTemplateUsed(response, 'sscape/index.html')
    return

class TestRoiViews(TestCase):
  def setUp(self):
    self.factory = RequestFactory()
    request = self.factory.get('/')
    self.user = User.objects.create_superuser('test_user', 'test_user@intel.com', 'testpassword')
    self.client.post(reverse('sign_in'), data = {'username': 'test_user', 'password': 'testpassword', 'request': request})
    test_scene = Scene.objects.create(name = "test_scene",  map = 'test_map')
    self.test_scene_id = test_scene.id
    return

  def test_save_ROI_get(self):
    response = self.client.get(reverse('save-roi', args=[self.test_scene_id]))
    self.assertEqual(response.status_code, 200)
    return

  def test_save_ROI_post(self):
    response = self.client.post(reverse('save-roi', args=[self.test_scene_id]))
    self.assertEqual(response.status_code, 200)
    return

  def test_save_ROIs(self):
    response = self.client.post(reverse('save-roi', args=[self.test_scene_id]),
    data = { 'rois': json.dumps([{'title': 'roi1', 'points': [[1, 2]], 'uuid':'5d03455d-82e6-4d3c-abc2-a496c43e4d53'}]),
             'tripwires': json.dumps([{'title': 'trip1', 'points': [[1, 2]], 'uuid':'9029524e-b764-438e-912e-9613d43895a0'}])
    })
    self.assertEqual(response.status_code, 302)
    return

class TestSignInViews(TestCase):
  def setUp(self):
    self.factory = RequestFactory()
    self.request = self.factory.get('/')
    self.user = User.objects.create_superuser('test_user', 'test_user@intel.com', 'testpassword')
    self.client.post(reverse('sign_in'), data = {'username': 'test_user', 'password': 'testpassword', 'request': self.request})

    test_scene = Scene.objects.create(name = "test_scene")
    self.test_scene_id = test_scene.id
    return

  def test_sign_in_get(self):
    response = self.client.get(reverse('sign_in'))
    self.assertEqual(response.status_code, 200)
    self.assertTemplateUsed(response, 'sscape/sign_in.html')
    return

  def test_sign_in_post(self):
    response = self.client.post(reverse('sign_in'), data = {'username': 'test_user', 'password': 'wrong'})
    self.assertEqual(response.status_code, 200)
    self.assertTemplateUsed(response, 'sscape/sign_in.html')
    return

  def test_sign_in_post_scene_detail(self):
    self.client.get(reverse('sceneDetail', args=[self.test_scene_id]))
    response = self.client.post(reverse('sign_in'), data = {'username': 'test_user', 'password': 'wrong'})
    self.assertEqual(response.status_code, 200)
    self.assertTemplateUsed(response, 'sscape/sign_in.html')
    return

class TestSignOutViews(SetUpTestCases):
  def test_sign_out(self):
    response = self.client.post(reverse('sign_out'))
    self.assertEqual(response.status_code, 302)
    return

class TestAccountLockedViews(SetUpTestCases):
  def test_account_is_locked(self):
    attempt = 0
    while(attempt < AXES_FAILURE_LIMIT):
      response = self.client.post(reverse('account_locked'))
      attempt += 1
    self.assertEqual(response.status_code, 200)
    return

class TestCameraViews(TestCase):

  camera_intrinsics = {
    'cam_coord1': '5, 5','cam_coord2': '5, 10',
    'cam_coord3': '10, 5','cam_coord4': '10, 10',
    'map_coord1': '10, 10','map_coord2': '10, 15',
    'map_coord3': '15, 10','map_coord4': '15, 15',
    'image_width': 33,'image_height': 22
  }

  def setUp(self):
    self.factory = RequestFactory()
    request = self.factory.get('/')
    self.user = User.objects.create_superuser('test_user', 'test_user@intel.com', 'testpassword')
    self.client.post(reverse('sign_in'), data = {'username': 'test_user', 'password': 'testpassword', 'request': request})

    test_scene = Scene.objects.create(name = "test_scene", map = 'test_map')
    self.test_scene_id = test_scene.id
    Cam.objects.create(sensor_id="1", name="test_camera", scene = test_scene)
    return

  def setup_view(self, view, request, *args, **kwargs):
    view.request = request
    view.args = args
    view.kwargs = kwargs
    return view

  def test_form_valid_create(self):
    response = self.client.get(reverse('cam_create'))

    create_view = self.setup_view(CamCreateView(), response)

    mock_form = Mock()
    mock_form.instance = Mock()
    mock_form.instance.type = 'camera'

    form_valid = create_view.form_valid(mock_form)
    self.assertEqual(form_valid.status_code, 302)
    return

  def test_success_url_update(self):
    response = self.client.get(reverse('cam_update', args=['1']))

    update_view = self.setup_view(CamUpdateView(), response)

    mock_object = Mock()
    mock_object.scene = Mock()
    mock_object.scene.id = self.test_scene_id

    update_view.object = mock_object
    url = update_view.get_success_url()
    self.assertEqual(url, f"/{self.test_scene_id}")
    return

  def test_success_url_delete(self):
    response = self.client.get(reverse('cam_delete', args=['1']))

    delete_view = self.setup_view(CamDeleteView(), response)

    mock_object = Mock()
    mock_object.scene = Mock()
    mock_object.scene.id = self.test_scene_id

    delete_view.object = mock_object
    url = delete_view.get_success_url()
    self.assertEqual(url, f"/{self.test_scene_id}")
    return

  def test_success_url_delete_else(self):
    response = self.client.get(reverse('cam_delete', args=['1']))

    delete_view = self.setup_view(CamDeleteView(), response)

    mock_object = Mock()
    mock_object.scene = None

    delete_view.object = mock_object
    url = delete_view.get_success_url()
    self.assertEqual(url, '/cam/list/')
    return

  def test_camera_calibrate(self):
    dummy = self.camera_intrinsics.copy()
    dummy.update({'calibrate_save': 1})
    response = self.client.post('/cam/calibrate/1', data = dummy)
    self.assertEqual(response.status_code, 200)
    return

  def test_camera_calibrate_point_not_none(self):
    dummy = self.camera_intrinsics.copy()
    dummy.update({'calibrate_save': 1})

    point = Point(5, 5)
    with patch('scene_common.geometry.Line.intersection', return_value = point):
      response = self.client.post('/cam/calibrate/1', data = dummy)
    self.assertEqual(response.status_code, 200)
    return

  def test_camera_calibrate_else(self):
    dummy = self.camera_intrinsics.copy()
    response = self.client.post('/cam/calibrate/1', data = dummy)
    self.assertEqual(response.status_code, 200)
    return

  def test_camera_calibrate_elif_1(self):
    dummy = self.camera_intrinsics.copy()
    dummy.update({'save_camera_details': 1, 'scene': '1',
                  'name': 'camera1','sensor_id': 1})
    response = self.client.post('/cam/calibrate/1', data = dummy)
    self.assertEqual(response.status_code, 200)
    return

  def test_camera_calibrate_elif_2(self):
    with open('tests/ui/test_media/SensorIcon.png', 'rb') as img:
      dummy = self.camera_intrinsics.copy()
      dummy.update({'save_camera_advanced': 1,'icon': img})
      response = self.client.post('/cam/calibrate/1', data = dummy)
    self.assertEqual(response.status_code, 200)
    return

  def test_camera_calibrate_is_valid(self):
    response = self.client.post('/cam/calibrate/1', data = {'calibrate_save': 1})
    self.assertEqual(response.status_code, 200)
    return

class TestSingletonSensorViews(TestCase):

  sensor_intrinsics = {
    'area': 'circle',
    'sensor_x': 1, 'sensor_y': 1,
    'sensor_r': 1,'rois': 1
  }

  def setUp(self):
    self.factory = RequestFactory()
    request = self.factory.get('/')
    self.user = User.objects.create_superuser('test_user', 'test_user@intel.com', 'testpassword')
    self.client.post(reverse('sign_in'), data = {'username': 'test_user', 'password': 'testpassword', 'request': request})

    test_scene = Scene.objects.create(name = "test_scene", map = 'test_map')
    self.test_scene_id = test_scene.id
    SingletonSensor.objects.create(sensor_id="100", name="test_sensor", scene = test_scene)
    Cam.objects.create(sensor_id="1", name="test_camera", scene = test_scene)
    return

  def setup_view(self, view, request, *args, **kwargs):
    view.request = request
    view.args = args
    view.kwargs = kwargs
    return view

  def test_form_valid_create(self):
    response = self.client.get(reverse('singleton_sensor_create'))

    create_view = self.setup_view(SingletonSensorCreateView(), response)

    mock_form = Mock()
    mock_form.instance = Mock()
    mock_form.instance.type = 'generic'

    form_valid = create_view.form_valid(mock_form)
    self.assertEqual(form_valid.status_code, 302)
    return

  def test_success_url_create(self):
    response = self.client.get(reverse('singleton_sensor_create'))

    create_view = self.setup_view(SingletonSensorCreateView(), response)

    mock_object = Mock()
    mock_object.scene = Mock()
    mock_object.scene.id = self.test_scene_id

    create_view.object = mock_object
    url = create_view.get_success_url()
    self.assertEqual(url, f"/{self.test_scene_id}")
    return

  def test_success_url_update(self):
    response = self.client.get(reverse('singleton_sensor_update', args=['1']))

    update_view = self.setup_view(SingletonSensorUpdateView(), response)

    mock_object = Mock()
    mock_object.scene = Mock()
    mock_object.scene.id = self.test_scene_id

    update_view.object = mock_object
    url = update_view.get_success_url()
    self.assertEqual(url, f"/{self.test_scene_id}")
    return

  def test_success_url_delete(self):
    response = self.client.get(reverse('singleton_sensor_delete', args=['1']))

    delete_view = self.setup_view(SingletonSensorDeleteView(), response)

    mock_object = Mock()
    mock_object.scene = Mock()
    mock_object.scene.id = self.test_scene_id

    delete_view.object = mock_object
    url = delete_view.get_success_url()
    self.assertEqual(url, f"/{self.test_scene_id}")
    return

  def test_success_url_delete_else(self):
    response = self.client.get(reverse('singleton_sensor_delete', args=['1']))

    delete_view = self.setup_view(SingletonSensorDeleteView(), response)

    mock_object = Mock()
    mock_object.scene = None

    delete_view.object = mock_object
    url = delete_view.get_success_url()
    self.assertEqual(url, '/singleton_sensor/list/')
    return

  def test_singleton_sensor_details_form(self):
    response = self.client.get('/singleton_sensor/calibrate/1')
    self.assertEqual(response.status_code, 200)
    return

  def test_generic_calibrate(self):
    dummy = self.sensor_intrinsics.copy()
    response = self.client.post('/singleton_sensor/calibrate/1', data = dummy)
    self.assertEqual(response.status_code, 200)
    return

  def test_generic_calibrate_ROIs(self):
    dummy = self.sensor_intrinsics.copy()
    dummy.update({'rois': json.dumps([{'points': [[1, 2], [3, 4]]}])})
    response = self.client.post('/singleton_sensor/calibrate/1', data = dummy)
    self.assertEqual(response.status_code, 200)
    return

  def test_generic_calibrate_is_not_valid(self):
    dummy = self.sensor_intrinsics.copy()
    dummy.update({'sensor_x': ''})
    response = self.client.post('/singleton_sensor/calibrate/1', data = dummy)
    self.assertEqual(response.status_code, 200)
    return

  def test_generic_calibrate_else(self):
    views.SingletonDetailsForm = MagicMock()
    with open('tests/ui/test_media/SensorIcon.png', 'rb') as img:
      dummy = self.sensor_intrinsics.copy()
      dummy.update({'icon': img, 'save_sensor_details': 1})
      response = self.client.post('/singleton_sensor/calibrate/1', data = dummy)
    self.assertEqual(response.status_code, 200)
    return

  def test_generic_calibrate_else_point_gt_zero(self):
    views.len = MagicMock(return_value = 1)
    with open('tests/ui/test_media/SensorIcon.png', 'rb') as img:
      dummy = self.sensor_intrinsics.copy()
      dummy.update({'icon': img})
      response = self.client.post('/singleton_sensor/calibrate/1', data = dummy)
    self.assertEqual(response.status_code, 200)
    return
