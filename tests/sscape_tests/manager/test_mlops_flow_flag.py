# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import re
from unittest.mock import patch
from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from manager.context_processors import selected_settings
from manager.forms import CamCalibrateForm, CamCreateForm, CamUpdateForm
from manager.models import Cam, Pipeline, Scene
from manager.pipeline_runtime import (
  PipelineSyncError,
  describe_camera_instance,
  reconcile_camera_pipeline,
  reconcile_pipeline_cameras,
  retry_pending_stops,
  sync_vippet_pipelines,
)
from manager.settings import _env_flag

INSTANCE_ID = UUID('11111111-1111-4111-8111-111111111111')
HINT = settings.MLOPS_FLOW_DISABLED_HINT


class EnvFlagTests(TestCase):

  def test_truthy_values_enable_flag(self):
    for value in ('true', 'TRUE', ' True ', '1', 't', 'yes', 'on'):
      with self.subTest(value=value), patch.dict('os.environ', {'ENABLE_MLOPS_FLOW': value}):
        self.assertTrue(_env_flag('ENABLE_MLOPS_FLOW'))

  def test_other_values_keep_flag_off(self):
    for value in ('', 'false', '0', 'no', 'off', 'enabled'):
      with self.subTest(value=value), patch.dict('os.environ', {'ENABLE_MLOPS_FLOW': value}):
        self.assertFalse(_env_flag('ENABLE_MLOPS_FLOW'))

  def test_unset_variable_keeps_flag_off(self):
    with patch.dict('os.environ', {}, clear=True):
      self.assertFalse(_env_flag('ENABLE_MLOPS_FLOW'))

  def test_flag_is_off_by_default_and_exposed_to_templates(self):
    self.assertFalse(settings.ENABLE_MLOPS_FLOW)
    context = selected_settings(RequestFactory().get('/'))
    self.assertFalse(context['ENABLE_MLOPS_FLOW'])
    self.assertEqual(context['MLOPS_FLOW_DISABLED_HINT'], HINT)
    self.assertIn('--enable-mlops-flow', HINT)
    self.assertIn('ENABLE_MLOPS_FLOW=true', HINT)


@override_settings(ENABLE_MLOPS_FLOW=False)
class MlopsFlowDisabledTests(TestCase):

  @classmethod
  def setUpTestData(cls):
    cls.admin = get_user_model().objects.create_user(
      username='flag-admin', is_staff=True, is_superuser=True)
    cls.reader = get_user_model().objects.create_user(username='flag-reader')
    cls.scene = Scene.objects.create(name='Flag scene')
    cls.first = Pipeline.objects.create(name='First', pipeline='first ! fakesink')
    cls.second = Pipeline.objects.create(name='Second', pipeline='second ! fakesink')

  def setUp(self):
    self.client.force_login(self.admin)
    for target in ('manager.pipeline_runtime.ViPPETClient', 'manager.pipeline_runtime.DLSPSClient',
                   'manager.models.sendUpdateCommand'):
      patcher = patch(target)
      self.addCleanup(patcher.stop)
      setattr(self, target.rsplit('.', 1)[1], patcher.start())

  def assert_no_external_calls(self):
    self.ViPPETClient.assert_not_called()
    self.DLSPSClient.assert_not_called()

  def make_camera(self, pipeline=None, instance_id=None):
    camera = Cam.objects.create(sensor_id='flag-cam', name='Flag cam', scene=self.scene,
                                pipeline=pipeline)
    if instance_id is not None:
      Cam.objects.filter(pk=camera.pk).update(dlsps_instance_id=instance_id)
    return Cam.objects.get(pk=camera.pk)

  def test_pipeline_list_shows_disabled_controls_with_hint(self):
    response = self.client.get(reverse('pipeline_list'))
    self.assertContains(response, 'id="pipeline-actions-disabled"')
    self.assertContains(response, f'title="{HINT}"')
    self.assertContains(response, 'id="mlops-flow-disabled-note"')
    self.assertContains(response, 'aria-label="Update First (disabled)"')
    self.assertContains(response, 'aria-label="Delete First (disabled)"')
    for absent in ('id="pipeline-sync-form"', reverse('pipeline_sync'), reverse('pipeline_create'),
                   reverse('pipeline_update', args=[self.first.pk]),
                   reverse('pipeline_delete', args=[self.first.pk])):
      with self.subTest(absent=absent):
        self.assertNotContains(response, absent)
    self.assertContains(response, 'first ! fakesink')

  def test_disabled_buttons_cannot_submit(self):
    page = self.client.get(reverse('pipeline_list')).content.decode()
    actions = page[page.index('id="pipeline-actions-disabled"'):page.index('</div>', page.index(
      'id="pipeline-actions-disabled"'))]
    self.assertEqual(actions.count('<button'), 2)
    self.assertEqual(actions.count('type="button"'), 2)
    self.assertEqual(actions.count('aria-disabled="true"'), 2)
    self.assertNotIn('<form', actions)
    self.assertNotIn('csrfmiddlewaretoken', actions)
    inputs = re.findall(r'<input[^>]*>', actions)
    self.assertEqual(len(inputs), 3)
    for tag in inputs:
      with self.subTest(input=tag):
        self.assertIn('disabled', tag)

  def test_reader_sees_plain_read_only_list(self):
    self.client.force_login(self.reader)
    response = self.client.get(reverse('pipeline_list'))
    self.assertEqual(response.status_code, 200)
    self.assertNotContains(response, 'id="pipeline-actions-disabled"')
    self.assertNotContains(response, 'id="pipeline-sync"')

  def test_superuser_cannot_mutate_or_sync(self):
    urls = (reverse('pipeline_create'), reverse('pipeline_update', args=[self.first.pk]),
            reverse('pipeline_delete', args=[self.first.pk]), reverse('pipeline_sync'))
    data = {'name': 'Changed', 'pipeline': 'changed ! fakesink'}
    for url in urls:
      for method in (self.client.get, self.client.post):
        with self.subTest(url=url, method=method.__name__):
          self.assertEqual(method(url, data).status_code, 403)
    self.assertEqual(set(Pipeline.objects.values_list('name', flat=True)), {'First', 'Second'})
    self.first.refresh_from_db()
    self.assertEqual(self.first.pipeline, 'first ! fakesink')
    self.assert_no_external_calls()

  def test_anonymous_is_still_redirected_to_sign_in(self):
    self.client.logout()
    response = self.client.post(reverse('pipeline_sync'))
    self.assertEqual(response.status_code, 302)
    self.assertIn(reverse('sign_in'), response['Location'])

  def test_camera_forms_disable_pipeline_field(self):
    camera = self.make_camera(pipeline=self.first)
    for form_class in (CamCreateForm, CamUpdateForm, CamCalibrateForm):
      with self.subTest(form=form_class.__name__):
        field = form_class(instance=camera).fields['pipeline']
        self.assertTrue(field.disabled)
        self.assertEqual(field.widget.attrs['title'], HINT)
    self.assertFalse(CamUpdateForm.base_fields['pipeline'].disabled)
    self.assertNotIn('title', CamUpdateForm.base_fields['pipeline'].widget.attrs)

  def test_camera_pages_render_greyed_selector_with_hint(self):
    camera = self.make_camera(pipeline=self.first, instance_id=INSTANCE_ID)
    for url in (reverse('cam_create'), reverse('cam_update', args=[camera.pk]),
                reverse('cam_calibrate', args=[camera.pk])):
      with self.subTest(url=url):
        response = self.client.get(url)
        self.assertContains(response, 'id="pipeline-mlops-flow-disabled"')
        self.assertContains(response, f'title="{HINT}"')
        page = response.content.decode()
        select = page[page.index('<select name="pipeline"'):page.index('>', page.index(
          '<select name="pipeline"'))]
        self.assertIn('disabled', select)
    self.assertContains(self.client.get(reverse('cam_update', args=[camera.pk])), str(INSTANCE_ID))

  def test_posted_pipeline_is_ignored_on_create(self):
    data = {'sensor_id': 'new-cam', 'name': 'New', 'scene': self.scene.pk,
            'pipeline': self.first.pk}
    self.assertEqual(self.client.post(reverse('cam_create'), data).status_code, 302)
    self.assertIsNone(Cam.objects.get(sensor_id='new-cam').pipeline)
    self.assert_no_external_calls()

  def test_stored_association_survives_update(self):
    camera = self.make_camera(pipeline=self.first, instance_id=INSTANCE_ID)
    for posted in (self.second.pk, ''):
      with self.subTest(posted=posted):
        data = {'sensor_id': camera.sensor_id, 'name': 'Renamed', 'scene': self.scene.pk,
                'pipeline': posted}
        response = self.client.post(reverse('cam_update', args=[camera.pk]), data)
        self.assertEqual(response.status_code, 302)
        camera.refresh_from_db()
        self.assertEqual((camera.name, camera.pipeline, camera.dlsps_instance_id),
                         ('Renamed', self.first, INSTANCE_ID))
    self.assert_no_external_calls()

  def test_calibrate_save_ignores_pipeline(self):
    camera = self.make_camera()
    form = CamCalibrateForm(instance=camera)
    data = {name: form[name].value() for name in form.fields
            if form[name].value() not in (None, False)}
    data['pipeline'] = self.first.pk
    response = self.client.post(reverse('cam_calibrate', args=[camera.pk]), data)
    self.assertEqual(response.status_code, 302)
    camera.refresh_from_db()
    self.assertIsNone(camera.pipeline)
    self.assert_no_external_calls()

  def test_deleting_camera_does_not_contact_dlsps(self):
    camera = self.make_camera(pipeline=self.first, instance_id=INSTANCE_ID)
    with self.captureOnCommitCallbacks(execute=True):
      camera.delete()
    self.assert_no_external_calls()

  def test_runtime_entry_points_are_inert(self):
    camera = self.make_camera(pipeline=self.first)
    self.assertEqual(reconcile_camera_pipeline(camera.pk), [])
    self.assertEqual(reconcile_pipeline_cameras(self.first), [])
    self.assertIsNone(describe_camera_instance(camera))
    retry_pending_stops()
    with self.assertRaisesRegex(PipelineSyncError, '--enable-mlops-flow'):
      sync_vippet_pipelines()
    camera.refresh_from_db()
    self.assertIsNone(camera.dlsps_instance_id)
    self.assert_no_external_calls()


@override_settings(ENABLE_MLOPS_FLOW=True)
class MlopsFlowEnabledRenderingTests(TestCase):

  @classmethod
  def setUpTestData(cls):
    cls.admin = get_user_model().objects.create_user(
      username='flag-on-admin', is_staff=True, is_superuser=True)

  def setUp(self):
    self.client.force_login(self.admin)

  def test_enabled_flow_renders_active_controls_without_hint(self):
    pipeline_list = self.client.get(reverse('pipeline_list'))
    self.assertContains(pipeline_list, 'id="pipeline-sync-form"')
    self.assertNotContains(pipeline_list, 'mlops-flow-disabled')
    cam_create = self.client.get(reverse('cam_create'))
    self.assertNotContains(cam_create, 'pipeline-mlops-flow-disabled')
    self.assertFalse(CamCreateForm().fields['pipeline'].disabled)
