#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.test.client import RequestFactory
from django.urls import reverse

from manager import views
from manager.models import Scene, SingletonSensor, Cam
from manager.settings import AXES_FAILURE_LIMIT
from manager.views import SingletonSensorDeleteView, SingletonSensorCreateView, \
                         SingletonSensorUpdateView, CamCreateView, CamDeleteView, CamUpdateView, \
                         saveRegionData, saveTripwireData
from scene_common.geometry import Point

test_scene_id = None

SENSOR_ICON_PATH = Path(__file__).resolve().parent.parent.parent / 'ui' / 'test_media' / 'SensorIcon.png'

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

  def _generate_roi(self, title='roi1', uuid_str=None, points=None):
    """Helper to generate ROI data structure."""
    if uuid_str is None:
      uuid_str = str(uuid.uuid4())
    if points is None:
      points = [[1, 2]]
    return {'title': title, 'points': points, 'uuid': uuid_str}

  def _generate_tripwire(self, title='trip1', uuid_str=None, points=None):
    """Helper to generate tripwire data structure."""
    if uuid_str is None:
      uuid_str = str(uuid.uuid4())
    if points is None:
      points = [[1, 2]]
    return {'title': title, 'points': points, 'uuid': uuid_str}

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

class TestRoiSaveNotificationBatching(TestCase):
  """Verifies saveROI batches sendUpdateCommand into exactly one call per save."""

  def setUp(self):
    self.factory = RequestFactory()
    request = self.factory.get('/')
    self.user = User.objects.create_superuser('test_user', 'test_user@intel.com', 'testpassword')
    self.client.post(reverse('sign_in'), data = {'username': 'test_user', 'password': 'testpassword', 'request': request})
    test_scene = Scene.objects.create(name = "test_scene",  map = 'test_map')
    self.test_scene_id = test_scene.id
    return

  def _generate_roi(self, title='roi1', uuid_str=None, points=None):
    """Helper to generate ROI data structure."""
    if uuid_str is None:
      uuid_str = str(uuid.uuid4())
    if points is None:
      points = [[1, 2]]
    return {'title': title, 'points': points, 'uuid': uuid_str}

  def _generate_tripwire(self, title='trip1', uuid_str=None, points=None):
    """Helper to generate tripwire data structure."""
    if uuid_str is None:
      uuid_str = str(uuid.uuid4())
    if points is None:
      points = [[1, 2]]
    return {'title': title, 'points': points, 'uuid': uuid_str}

  @patch('manager.views.sendUpdateCommand')
  @patch('manager.views.transaction.on_commit')
  def test_single_notification_multiple_rois(self, mock_on_commit, mock_send_update):
    """Test that multiple ROIs in one request trigger sendUpdateCommand exactly once."""
    # Make on_commit execute callbacks immediately
    def execute_callback(callback):
      callback()
    mock_on_commit.side_effect = execute_callback
    
    rois = [
      self._generate_roi(title='roi1', uuid_str=str(uuid.uuid4())),
      self._generate_roi(title='roi2', uuid_str=str(uuid.uuid4())),
      self._generate_roi(title='roi3', uuid_str=str(uuid.uuid4())),
    ]
    
    response = self.client.post(reverse('save-roi', args=[self.test_scene_id]),
      data = {
        'rois': json.dumps(rois),
        'tripwires': json.dumps([])
      })
    
    self.assertEqual(response.status_code, 302)
    # Should call sendUpdateCommand exactly once, not 3 times
    mock_send_update.assert_called_once()
    # Verify it was called with the scene_id
    mock_send_update.assert_called_once_with(scene_id=self.test_scene_id)

  @patch('manager.views.sendUpdateCommand')
  @patch('manager.views.transaction.on_commit')
  def test_single_notification_multiple_tripwires(self, mock_on_commit, mock_send_update):
    """Test that multiple tripwires in one request trigger sendUpdateCommand exactly once."""
    def execute_callback(callback):
      callback()
    mock_on_commit.side_effect = execute_callback
    
    tripwires = [
      self._generate_tripwire(title='trip1', uuid_str=str(uuid.uuid4())),
      self._generate_tripwire(title='trip2', uuid_str=str(uuid.uuid4())),
      self._generate_tripwire(title='trip3', uuid_str=str(uuid.uuid4())),
    ]
    
    response = self.client.post(reverse('save-roi', args=[self.test_scene_id]),
      data = {
        'rois': json.dumps([]),
        'tripwires': json.dumps(tripwires)
      })
    
    self.assertEqual(response.status_code, 302)
    # Should call sendUpdateCommand exactly once, not 3 times
    mock_send_update.assert_called_once()
    mock_send_update.assert_called_once_with(scene_id=self.test_scene_id)

  @patch('manager.views.sendUpdateCommand')
  @patch('manager.views.transaction.on_commit')
  def test_single_notification_rois_and_tripwires_together(self, mock_on_commit, mock_send_update):
    """Test that mixed ROI and tripwire changes trigger sendUpdateCommand exactly once."""
    def execute_callback(callback):
      callback()
    mock_on_commit.side_effect = execute_callback
    
    rois = [
      self._generate_roi(title='roi1', uuid_str=str(uuid.uuid4())),
      self._generate_roi(title='roi2', uuid_str=str(uuid.uuid4())),
    ]
    tripwires = [
      self._generate_tripwire(title='trip1', uuid_str=str(uuid.uuid4())),
      self._generate_tripwire(title='trip2', uuid_str=str(uuid.uuid4())),
    ]
    
    response = self.client.post(reverse('save-roi', args=[self.test_scene_id]),
      data = {
        'rois': json.dumps(rois),
        'tripwires': json.dumps(tripwires)
      })
    
    self.assertEqual(response.status_code, 302)
    # Should call sendUpdateCommand exactly once, not twice (once for ROIs + once for tripwires)
    mock_send_update.assert_called_once()
    mock_send_update.assert_called_once_with(scene_id=self.test_scene_id)

  def test_no_notification_when_nothing_changed(self):
    """Test that saveRegionData/saveTripwireData return False (no change) when posting empty lists to a scene with zero existing regions/tripwires."""
    # Create a fresh scene with zero regions and tripwires
    fresh_scene = Scene.objects.create(name="fresh_scene_for_noop_test", map='test_map')
    
    # Create a mock form with empty rois and tripwires JSON
    form = Mock()
    form.cleaned_data = {
      'rois': json.dumps([]),
      'tripwires': json.dumps([])
    }
    
    # Call saveRegionData with empty list on a scene with zero existing regions
    # Should return False (no changes, no notification needed)
    changed_regions = saveRegionData(fresh_scene, form)
    self.assertFalse(changed_regions, "saveRegionData should return False when posting empty rois to a scene with zero existing regions")
    
    # Call saveTripwireData with empty list on a scene with zero existing tripwires
    # Should return False (no changes, no notification needed)
    changed_tripwires = saveTripwireData(fresh_scene, form)
    self.assertFalse(changed_tripwires, "saveTripwireData should return False when posting empty tripwires to a scene with zero existing tripwires")

  @patch('manager.views.sendUpdateCommand')
  @patch('manager.views.transaction.on_commit')
  def test_notification_on_deletion_only(self, mock_on_commit, mock_send_update):
    """Test that deletion triggers sendUpdateCommand exactly once."""
    def execute_callback(callback):
      callback()
    mock_on_commit.side_effect = execute_callback
    
    # First request: save a ROI
    roi_uuid = str(uuid.uuid4())
    rois = [self._generate_roi(title='roi1', uuid_str=roi_uuid)]
    response1 = self.client.post(reverse('save-roi', args=[self.test_scene_id]),
      data = {
        'rois': json.dumps(rois),
        'tripwires': json.dumps([])
      })
    self.assertEqual(response1.status_code, 302)
    mock_send_update.assert_called_once()
    
    # Reset mock
    mock_send_update.reset_mock()
    
    # Second request: POST with empty ROI list (deletes the ROI)
    response2 = self.client.post(reverse('save-roi', args=[self.test_scene_id]),
      data = {
        'rois': json.dumps([]),
        'tripwires': json.dumps([])
      })
    self.assertEqual(response2.status_code, 302)
    # Should call sendUpdateCommand exactly once for the deletion
    mock_send_update.assert_called_once()
    mock_send_update.assert_called_once_with(scene_id=self.test_scene_id)

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

  def test_sign_in_post_success(self):
    response = self.client.post(reverse('sign_in'), data = {'username': ' test_user ', 'password': 'testpassword', 'request': self.request})
    self.assertEqual(response.status_code, 302)
    return

  def test_sign_in_post_trims_whitespace(self):
    response = self.client.post(reverse('sign_in'), data = {'username': ' test_user ', 'password': 'testpassword', 'request': self.request})
    self.assertEqual(response.status_code, 302)
    return

  def test_sign_in_post_wrong_username(self):
    response = self.client.post(reverse('sign_in'), data = {'username': 'wrong_user', 'password': 'testpassword', 'request': self.request})
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
    with open(str(SENSOR_ICON_PATH), 'rb') as img:
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
    with open(str(SENSOR_ICON_PATH), 'rb') as img:
      dummy = self.sensor_intrinsics.copy()
      dummy.update({'icon': img, 'save_sensor_details': 1})
      response = self.client.post('/singleton_sensor/calibrate/1', data = dummy)
    self.assertEqual(response.status_code, 200)
    return

  def test_generic_calibrate_else_point_gt_zero(self):
    views.len = MagicMock(return_value = 1)
    with open(str(SENSOR_ICON_PATH), 'rb') as img:
      dummy = self.sensor_intrinsics.copy()
      dummy.update({'icon': img})
      response = self.client.post('/singleton_sensor/calibrate/1', data = dummy)
    self.assertEqual(response.status_code, 200)
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

