#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import tempfile
from unittest.mock import Mock
from django.test import TestCase, override_settings
from django.urls import reverse
from manager.models import Scene, SingletonSensor, Cam, ChildScene
from manager.views import (
  SingletonSensorDeleteView, CamDeleteView, ChildDeleteView)
from django.contrib.auth.models import User
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
    self.assertEqual(response.status_code, 302)
    self.assertEqual(response.url, f'/{self.test_scene_id}')
    return

  def test_save_ROI_post(self):
    response = self.client.post(reverse('save-roi', args=[self.test_scene_id]))
    self.assertEqual(response.status_code, 302)
    self.assertEqual(response.url, f'/{self.test_scene_id}')
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

  def test_cam_create_redirects_to_sheet(self):
    response = self.client.get(reverse('cam_create'))
    self.assertEqual(response.status_code, 302)
    self.assertIn('ss=cam-create', response.url)
    return

  def test_cam_create_with_scene_redirects_to_scene_sheet(self):
    response = self.client.get(
      reverse('cam_create'), data={'scene': str(self.test_scene_id)})
    self.assertEqual(response.status_code, 302)
    self.assertEqual(response.url, f"/{self.test_scene_id}/?ss=cam-create")
    return

  def test_cam_update_redirects_to_sheet(self):
    cam = Cam.objects.get(sensor_id="1")
    response = self.client.get(reverse('cam_update', args=[cam.pk]))
    self.assertEqual(response.status_code, 302)
    self.assertIn('ss=cam-edit', response.url)
    self.assertIn(f'id={cam.sensor_id}', response.url)
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

  def test_camera_calibrate_get_redirects_to_react_sheet(self):
    cam = Cam.objects.get(sensor_id="1")
    response = self.client.get('/cam/calibrate/1')
    self.assertEqual(response.status_code, 302)
    self.assertEqual(
      response.url, f"{reverse('cam_list')}?ss=calibrate-cam&id={cam.pk}")
    return

  def test_camera_calibrate_post_also_redirects(self):
    cam = Cam.objects.get(sensor_id="1")
    response = self.client.post('/cam/calibrate/1', data={'calibrate_save': 1})
    self.assertEqual(response.status_code, 302)
    self.assertEqual(
      response.url, f"{reverse('cam_list')}?ss=calibrate-cam&id={cam.pk}")
    return

  def test_camera_calibrate_orphan_redirects_to_list(self):
    orphan = Cam.objects.create(sensor_id="2", name="orphan_cam", scene=None)
    response = self.client.get(f'/cam/calibrate/{orphan.pk}')
    self.assertEqual(response.status_code, 302)
    self.assertEqual(response.url, reverse('cam_list'))
    return

  def test_camera_calibrate_embed_renders_3d_workspace(self):
    cam = Cam.objects.get(sensor_id="1")
    response = self.client.get(f'/cam/calibrate/{cam.pk}?embed=1')
    self.assertEqual(response.status_code, 200)
    self.assertContains(response, 'id="camera_img_canvas"')
    self.assertContains(response, 'id="map_canvas_3D"')
    self.assertContains(response, 'id="initial-id_transforms"')
    return

  def test_camera_calibrate_embed_orphan_redirects_to_list(self):
    orphan = Cam.objects.create(sensor_id="3", name="orphan_embed", scene=None)
    response = self.client.get(f'/cam/calibrate/{orphan.pk}?embed=1')
    self.assertEqual(response.status_code, 302)
    self.assertEqual(response.url, reverse('cam_list'))
    return

class TestSingletonSensorViews(TestCase):

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

  def test_sensor_create_redirects_to_sheet(self):
    response = self.client.get(reverse('singleton_sensor_create'))
    self.assertEqual(response.status_code, 302)
    self.assertIn('ss=sensor-create', response.url)
    return

  def test_sensor_create_with_scene_redirects_to_scene_sheet(self):
    response = self.client.get(
      reverse('singleton_sensor_create'),
      data={'scene': str(self.test_scene_id)})
    self.assertEqual(response.status_code, 302)
    self.assertEqual(
      response.url, f"/{self.test_scene_id}/?ss=sensor-create")
    return

  def test_sensor_update_redirects_to_sheet(self):
    sensor = SingletonSensor.objects.get(sensor_id="100")
    response = self.client.get(reverse('singleton_sensor_update', args=[sensor.pk]))
    self.assertEqual(response.status_code, 302)
    self.assertIn('ss=sensor-edit', response.url)
    self.assertIn(f'id={sensor.sensor_id}', response.url)
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

  def test_generic_calibrate_url_removed(self):
    """Standalone sensor calibrate URL is gone; React hosts the sheet."""
    response = self.client.get('/singleton_sensor/calibrate/1')
    self.assertEqual(response.status_code, 404)
    return

class TestChildViews(TestCase):

  def setUp(self):
    self.factory = RequestFactory()
    request = self.factory.get('/')
    self.user = User.objects.create_superuser(
      'test_user', 'test_user@intel.com', 'testpassword')
    self.client.post(
      reverse('sign_in'),
      data={
        'username': 'test_user',
        'password': 'testpassword',
        'request': request,
      },
    )
    self.parent = Scene.objects.create(name="parent_scene", map="test_map")
    self.child = Scene.objects.create(name="child_scene", map="test_map")
    self.link = ChildScene.objects.create(
      parent=self.parent, child=self.child, child_type="local")
    return

  def setup_view(self, view, request, *args, **kwargs):
    view.request = request
    view.args = args
    view.kwargs = kwargs
    return view

  def test_success_url_delete(self):
    response = self.client.get(reverse('child_delete', args=[self.link.pk]))
    delete_view = self.setup_view(ChildDeleteView(), response)
    mock_object = Mock()
    mock_object.parent_id = self.parent.id
    delete_view.object = mock_object
    url = delete_view.get_success_url()
    self.assertEqual(url, f"/{self.parent.id}/")
    return

  def test_success_url_delete_else(self):
    response = self.client.get(reverse('child_delete', args=[self.link.pk]))
    delete_view = self.setup_view(ChildDeleteView(), response)
    mock_object = Mock()
    mock_object.parent_id = None
    delete_view.object = mock_object
    url = delete_view.get_success_url()
    self.assertEqual(url, reverse('index'))
    return

  def test_child_delete_post_redirects_to_parent_scene(self):
    response = self.client.post(reverse('child_delete', args=[self.link.pk]))
    self.assertEqual(response.status_code, 302)
    self.assertEqual(response.url, f"/{self.parent.id}/")
    self.assertFalse(ChildScene.objects.filter(pk=self.link.pk).exists())
    return

class TestSaveGeospatialSnapshot(TestCase):
  """Verifies save-geospatial-snapshot uses session auth, not token auth (ITEP-95127)."""
  TEST_NAME = "NEX-T27251"

  # 1x1 transparent PNG; content is irrelevant, only auth wiring is under test
  DUMMY_IMAGE_DATA = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB"
                       "CAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")

  def setUp(self):
    self.user = User.objects.create_superuser('test_user', 'test_user@intel.com', 'testpassword')
    self.media_root = tempfile.mkdtemp()
    return

  def test_authenticated_session_can_save_snapshot(self):
    self.client.post(reverse('sign_in'), data = {'username': 'test_user', 'password': 'testpassword'})
    with override_settings(MEDIA_ROOT=self.media_root):
      response = self.client.post(reverse('save_geospatial_snapshot'), data = {'image_data': self.DUMMY_IMAGE_DATA})
    self.assertEqual(response.status_code, 200)
    return

  def test_unauthenticated_request_is_rejected(self):
    # No login: DRF's SessionAuthentication authenticates the request as an
    # AnonymousUser (rather than failing outright), so IsAdminOrReadOnly denies
    # it as a permission failure (403), not as an authentication failure (401).
    response = self.client.post(reverse('save_geospatial_snapshot'), data = {'image_data': self.DUMMY_IMAGE_DATA})
    self.assertEqual(response.status_code, 403)
    return
