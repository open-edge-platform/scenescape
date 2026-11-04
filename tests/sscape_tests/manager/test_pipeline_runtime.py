# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import patch
from uuid import UUID

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import Client, TestCase
from django.urls import reverse

from manager.dlsps import DLSPSConflictError, DLSPSNotFoundError, DLSPSUnavailableError
from manager.forms import CamCalibrateForm
from manager.models import Cam, Pipeline, Scene
from manager.pipeline_runtime import (
  RESTART_CONFIG,
  PipelineSyncError,
  apply_camera_pipeline,
  stop_dlsps_instance,
  sync_vippet_pipelines,
)
from manager.vippet import (
  PipelineSummary,
  PipelineVariant,
  ViPPETBadRequestError,
  ViPPETUnavailableError,
)

OLD_ID = UUID('11111111-1111-4111-8111-111111111111')
NEW_ID = UUID('22222222-2222-4222-8222-222222222222')


def summary(pipeline_id, name, *variants):
  return PipelineSummary(id=pipeline_id, name=name, description='', tags=(),
                         variants=tuple(PipelineVariant(id=v, name=v.upper()) for v in variants))


class MockedClientsMixin:
  """Patch the ViPPET and DLSPS clients where pipeline_runtime looks them up."""

  def setUp(self):
    super().setUp()
    self.vippet_cls = self._patch('manager.pipeline_runtime.ViPPETClient', autospec=True)
    self.vippet = self.vippet_cls.return_value
    self.vippet_strings = {}
    self.vippet.get_pipeline_string.side_effect = (
      lambda pipeline_id, variant_id: self.vippet_strings[(pipeline_id, variant_id)])
    self.dlsps_cls = self._patch('manager.pipeline_runtime.DLSPSClient', autospec=True)
    self.dlsps = self.dlsps_cls.return_value
    self.dlsps.__enter__.return_value = self.dlsps
    self.dlsps.create_pipeline.return_value = str(NEW_ID)
    self.dlsps.delete_pipeline.side_effect = str
    self._patch('manager.models.sendUpdateCommand')

  def _patch(self, target, **kwargs):
    patcher = patch(target, **kwargs)
    mocked = patcher.start()
    self.addCleanup(patcher.stop)
    return mocked

  def set_vippet(self, summaries, strings):
    self.vippet.get_pipelines.return_value = summaries
    self.vippet_strings.update(strings)

  def make_camera(self, pipeline=None, instance_id=None, **kwargs):
    camera = Cam.objects.create(sensor_id=kwargs.pop('sensor_id', 'runtime-cam'),
                                name=kwargs.pop('name', 'Runtime'), pipeline=pipeline,
                                **kwargs)
    if instance_id is not None:
      Cam.objects.filter(pk=camera.pk).update(dlsps_instance_id=instance_id)
    return camera

  def instance_id_of(self, camera):
    return Cam.objects.get(pk=camera.pk).dlsps_instance_id


class ViPPETSyncTests(MockedClientsMixin, TestCase):

  def test_creates_one_pipeline_per_variant(self):
    self.set_vippet([summary('people', 'People', 'cpu', 'gpu')],
                    {('people', 'cpu'): 'cpu ! fakesink', ('people', 'gpu'): 'gpu ! fakesink'})
    result = sync_vippet_pipelines()
    self.assertEqual(result.created, ['People (CPU)', 'People (GPU)'])
    self.assertEqual(
      list(Pipeline.objects.values_list('name', 'pipeline', 'vippet_pipeline_id')),
      [('People (CPU)', 'cpu ! fakesink', 'people/cpu'),
       ('People (GPU)', 'gpu ! fakesink', 'people/gpu')])
    self.vippet.__exit__.assert_called_once()

  def test_resync_updates_changed_and_counts_unchanged(self):
    Pipeline.objects.create(name='People (CPU)', pipeline='old', vippet_pipeline_id='people/cpu')
    Pipeline.objects.create(name='Old name', pipeline='gpu', vippet_pipeline_id='people/gpu')
    Pipeline.objects.create(name='People (NPU)', pipeline='npu', vippet_pipeline_id='people/npu')
    self.set_vippet([summary('people', 'People', 'cpu', 'gpu', 'npu')],
                    {('people', 'cpu'): 'new', ('people', 'gpu'): 'gpu',
                     ('people', 'npu'): 'npu'})
    result = sync_vippet_pipelines()
    self.assertEqual(result.created, [])
    self.assertEqual(result.updated, ['People (CPU)', 'People (GPU)'])
    self.assertEqual(result.unchanged, 1)
    self.assertEqual(Pipeline.objects.get(vippet_pipeline_id='people/cpu').pipeline, 'new')
    self.assertEqual(Pipeline.objects.get(vippet_pipeline_id='people/gpu').name, 'People (GPU)')

  def test_stale_and_manual_pipelines_are_kept(self):
    Pipeline.objects.create(name='Gone (CPU)', pipeline='a', vippet_pipeline_id='gone/cpu')
    Pipeline.objects.create(name='Manual', pipeline='b')
    self.set_vippet([], {})
    sync_vippet_pipelines()
    self.assertEqual(Pipeline.objects.count(), 2)

  def test_name_clash_with_other_pipeline_is_skipped(self):
    manual = Pipeline.objects.create(name='People (CPU)', pipeline='manual')
    self.set_vippet([summary('people', 'People', 'cpu', 'gpu')],
                    {('people', 'cpu'): 'cpu', ('people', 'gpu'): 'gpu'})
    result = sync_vippet_pipelines()
    self.assertEqual(result.created, ['People (GPU)'])
    self.assertEqual(len(result.skipped), 1)
    self.assertIn('People (CPU)', result.skipped[0])
    manual.refresh_from_db()
    self.assertEqual((manual.pipeline, manual.vippet_pipeline_id), ('manual', None))

  def test_duplicate_names_within_vippet_keep_first(self):
    self.set_vippet([summary('a', 'Same', 'cpu'), summary('b', 'Same', 'cpu')],
                    {('a', 'cpu'): 'a', ('b', 'cpu'): 'b'})
    result = sync_vippet_pipelines()
    self.assertEqual(result.created, ['Same (CPU)'])
    self.assertEqual(len(result.skipped), 1)
    self.assertEqual(Pipeline.objects.get().vippet_pipeline_id, 'a/cpu')

  def test_too_long_name_is_skipped(self):
    self.set_vippet([summary('long', 'x' * 200, 'cpu')], {('long', 'cpu'): 'cpu'})
    result = sync_vippet_pipelines()
    self.assertEqual(result.created, [])
    self.assertIn('exceeds 200 characters', result.skipped[0])
    self.assertFalse(Pipeline.objects.exists())

  def test_variant_failure_is_skipped_and_others_stored(self):
    def get_pipeline_string(_pipeline_id, variant_id):
      if variant_id == 'cpu':
        raise ViPPETBadRequestError('cannot convert')
      return 'gpu'
    self.set_vippet([summary('people', 'People', 'cpu', 'gpu')], {})
    self.vippet.get_pipeline_string.side_effect = get_pipeline_string
    result = sync_vippet_pipelines()
    self.assertEqual(result.created, ['People (GPU)'])
    self.assertEqual(result.skipped, ['People (CPU): could not fetch its pipeline string'])

  def test_not_configured_raises_without_changes(self):
    self.vippet_cls.side_effect = ValueError('no url')
    with self.assertRaisesRegex(PipelineSyncError, 'VIPPET_URL'):
      sync_vippet_pipelines()
    self.assertFalse(Pipeline.objects.exists())

  def test_list_failure_raises_without_changes(self):
    self.vippet.get_pipelines.side_effect = ViPPETUnavailableError('down')
    with self.assertRaises(PipelineSyncError):
      sync_vippet_pipelines()
    self.assertFalse(Pipeline.objects.exists())
    self.vippet.__exit__.assert_called_once()

  def test_changed_string_restarts_assigned_camera(self):
    pipeline = Pipeline.objects.create(name='People (CPU)', pipeline='old',
                                       vippet_pipeline_id='people/cpu')
    camera = self.make_camera(pipeline=pipeline, instance_id=OLD_ID)
    self.set_vippet([summary('people', 'People', 'cpu')], {('people', 'cpu'): 'new'})
    result = sync_vippet_pipelines()
    self.assertEqual(result.warnings, [])
    self.dlsps.delete_pipeline.assert_called_once_with(OLD_ID)
    self.dlsps.create_pipeline.assert_called_once_with('new', restart_config=RESTART_CONFIG)
    self.assertEqual(self.instance_id_of(camera), NEW_ID)

  def test_rename_only_does_not_restart_camera(self):
    pipeline = Pipeline.objects.create(name='Old', pipeline='same',
                                       vippet_pipeline_id='people/cpu')
    self.make_camera(pipeline=pipeline, instance_id=OLD_ID)
    self.set_vippet([summary('people', 'People', 'cpu')], {('people', 'cpu'): 'same'})
    sync_vippet_pipelines()
    self.dlsps_cls.assert_not_called()


class PipelineSyncViewTests(MockedClientsMixin, TestCase):

  @classmethod
  def setUpTestData(cls):
    cls.admin = get_user_model().objects.create_user(
      username='sync-admin', is_staff=True, is_superuser=True)
    cls.reader = get_user_model().objects.create_user(username='sync-reader')

  def setUp(self):
    super().setUp()
    self.client.force_login(self.admin)
    self.url = reverse('pipeline_sync')

  def test_sync_button_only_for_superuser(self):
    self.assertContains(self.client.get(reverse('pipeline_list')), 'id="pipeline-sync-form"')
    self.client.force_login(self.reader)
    self.assertNotContains(self.client.get(reverse('pipeline_list')), 'id="pipeline-sync-form"')

  def test_sync_reports_summary_on_pipeline_list(self):
    Pipeline.objects.create(name='Clash (CPU)', pipeline='manual')
    self.set_vippet([summary('people', 'People', 'cpu'), summary('clash', 'Clash', 'cpu')],
                    {('people', 'cpu'): 'cpu', ('clash', 'cpu'): 'cpu'})
    response = self.client.post(self.url, follow=True)
    self.assertRedirects(response, reverse('pipeline_list'))
    self.assertContains(response, 'Synced with ViPPET: 1 created, 0 updated, 0 unchanged.')
    self.assertContains(response, 'Clash (CPU): another pipeline already uses this name')
    self.assertContains(response, 'people/cpu')

  def test_sync_error_is_shown(self):
    self.vippet_cls.side_effect = ValueError('no url')
    response = self.client.post(self.url, follow=True)
    self.assertContains(response, 'ViPPET is not configured')
    self.assertContains(response, 'alert-danger')

  def test_message_content_is_escaped(self):
    self.set_vippet([summary('x', '<script>alert(1)</script>', 'cpu')], {('x', 'cpu'): 'cpu'})
    Pipeline.objects.create(name='<script>alert(1)</script> (CPU)', pipeline='manual')
    response = self.client.post(self.url, follow=True)
    self.assertNotContains(response, '<script>alert(1)</script>')

  def test_get_is_not_allowed(self):
    self.assertEqual(self.client.get(self.url).status_code, 405)
    self.vippet_cls.assert_not_called()

  def test_reader_is_forbidden(self):
    self.client.force_login(self.reader)
    self.assertEqual(self.client.post(self.url).status_code, 403)
    self.vippet_cls.assert_not_called()

  def test_anonymous_is_redirected(self):
    self.client.logout()
    self.assertEqual(self.client.post(self.url).status_code, 302)
    self.vippet_cls.assert_not_called()

  def test_csrf_is_required(self):
    client = Client(enforce_csrf_checks=True)
    client.force_login(self.admin)
    self.assertEqual(client.post(self.url).status_code, 403)
    self.vippet_cls.assert_not_called()


class CameraFixturesMixin(MockedClientsMixin):
  """Superuser client, a scene and two unassigned pipelines."""

  @classmethod
  def setUpTestData(cls):
    cls.admin = get_user_model().objects.create_user(
      username='runtime-admin', is_staff=True, is_superuser=True)
    cls.scene = Scene.objects.create(name='Runtime scene')
    cls.first = Pipeline.objects.create(name='First', pipeline='first ! fakesink')
    cls.second = Pipeline.objects.create(name='Second', pipeline='second ! fakesink')

  def setUp(self):
    super().setUp()
    self.client.force_login(self.admin)

  def update_camera(self, camera, pipeline):
    data = {'sensor_id': camera.sensor_id, 'name': camera.name, 'scene': self.scene.pk,
            'pipeline': pipeline.pk if pipeline else ''}
    response = self.client.post(reverse('cam_update', args=[camera.pk]), data)
    self.assertEqual(response.status_code, 302)
    return [str(m) for m in get_messages(response.wsgi_request)]


class CameraPipelineRuntimeTests(CameraFixturesMixin, TestCase):

  def test_create_with_pipeline_starts_instance_with_restarts(self):
    data = {'sensor_id': 'new-cam', 'name': 'New', 'scene': self.scene.pk,
            'pipeline': self.first.pk}
    response = self.client.post(reverse('cam_create'), data)
    self.assertEqual(response.status_code, 302)
    self.dlsps.create_pipeline.assert_called_once_with('first ! fakesink',
                                                       restart_config=RESTART_CONFIG)
    self.assertTrue(RESTART_CONFIG.enabled)
    self.assertEqual(Cam.objects.get(sensor_id='new-cam').dlsps_instance_id, NEW_ID)

  def test_create_without_pipeline_does_not_contact_dlsps(self):
    data = {'sensor_id': 'plain-cam', 'name': 'Plain', 'scene': self.scene.pk}
    self.assertEqual(self.client.post(reverse('cam_create'), data).status_code, 302)
    self.dlsps_cls.assert_not_called()

  def test_changing_pipeline_restarts_instance(self):
    camera = self.make_camera(pipeline=self.first, instance_id=OLD_ID, scene=self.scene)
    self.assertEqual(self.update_camera(camera, self.second), [])
    self.dlsps.delete_pipeline.assert_called_once_with(OLD_ID)
    self.dlsps.create_pipeline.assert_called_once_with('second ! fakesink',
                                                       restart_config=RESTART_CONFIG)
    self.assertEqual(self.instance_id_of(camera), NEW_ID)

  def test_clearing_pipeline_stops_instance(self):
    camera = self.make_camera(pipeline=self.first, instance_id=OLD_ID, scene=self.scene)
    self.assertEqual(self.update_camera(camera, None), [])
    self.dlsps.delete_pipeline.assert_called_once_with(OLD_ID)
    self.dlsps.create_pipeline.assert_not_called()
    self.assertIsNone(self.instance_id_of(camera))

  def test_unchanged_running_pipeline_is_left_alone(self):
    camera = self.make_camera(pipeline=self.first, instance_id=OLD_ID, scene=self.scene)
    self.update_camera(camera, self.first)
    self.dlsps_cls.assert_not_called()
    self.assertEqual(self.instance_id_of(camera), OLD_ID)

  def test_unchanged_pipeline_without_instance_is_retried(self):
    camera = self.make_camera(pipeline=self.first, scene=self.scene)
    self.update_camera(camera, self.first)
    self.dlsps.create_pipeline.assert_called_once()
    self.assertEqual(self.instance_id_of(camera), NEW_ID)

  def test_start_failure_saves_camera_and_warns(self):
    self.dlsps.create_pipeline.side_effect = DLSPSUnavailableError('down')
    camera = self.make_camera(scene=self.scene)
    warnings = self.update_camera(camera, self.first)
    self.assertEqual(len(warnings), 1)
    self.assertIn("failed to start pipeline 'First'", warnings[0])
    self.assertEqual(Cam.objects.get(pk=camera.pk).pipeline, self.first)
    self.assertIsNone(self.instance_id_of(camera))

  def test_non_uuid_instance_id_is_treated_as_start_failure(self):
    self.dlsps.create_pipeline.return_value = 'not-a-uuid'
    camera = self.make_camera(pipeline=self.first, scene=self.scene)
    self.assertEqual(len(apply_camera_pipeline(camera.pk, pipeline_changed=False)), 1)
    self.assertIsNone(self.instance_id_of(camera))

  def test_stop_failure_keeps_instance_and_skips_start(self):
    self.dlsps.delete_pipeline.side_effect = DLSPSUnavailableError('down')
    camera = self.make_camera(pipeline=self.first, instance_id=OLD_ID, scene=self.scene)
    warnings = self.update_camera(camera, self.second)
    self.assertEqual(len(warnings), 1)
    self.assertIn('failed to stop', warnings[0])
    self.dlsps.create_pipeline.assert_not_called()
    self.assertEqual(self.instance_id_of(camera), OLD_ID)

  def test_already_stopped_instance_is_replaced(self):
    for error in (DLSPSNotFoundError('gone'), DLSPSConflictError('completed')):
      name = type(error).__name__
      with self.subTest(error=name):
        self.dlsps.reset_mock()
        self.dlsps.delete_pipeline.side_effect = error
        pipeline = Pipeline.objects.create(name=name, pipeline=f'{name} ! fakesink')
        camera = self.make_camera(pipeline=pipeline, instance_id=OLD_ID,
                                  sensor_id=name[:20], name=name)
        self.assertEqual(apply_camera_pipeline(camera.pk, pipeline_changed=True), [])
        self.dlsps.create_pipeline.assert_called_once()
        self.assertEqual(self.instance_id_of(camera), NEW_ID)

  def test_dlsps_not_configured_warns(self):
    self.dlsps_cls.side_effect = ValueError('no url')
    camera = self.make_camera(scene=self.scene)
    warnings = self.update_camera(camera, self.first)
    self.assertEqual(len(warnings), 1)
    self.assertIn('DLSPS is not configured (set DLSPS_URL)', warnings[0])
    self.assertEqual(Cam.objects.get(pk=camera.pk).pipeline, self.first)

  def test_warning_is_shown_on_scene_page_after_save(self):
    self.dlsps_cls.side_effect = ValueError('no url')
    camera = self.make_camera(scene=self.scene)
    data = {'sensor_id': camera.sensor_id, 'name': camera.name, 'scene': self.scene.pk,
            'pipeline': self.first.pk}
    response = self.client.post(reverse('cam_update', args=[camera.pk]), data, follow=True)
    self.assertTemplateUsed(response, 'sscape/sceneDetail.html')
    self.assertContains(response, 'alert-warning')
    self.assertContains(response, 'DLSPS is not configured')

  def test_calibrate_page_selects_pipeline(self):
    camera = self.make_camera(scene=self.scene)
    form = CamCalibrateForm(instance=camera)
    data = {name: form[name].value() for name in form.fields
            if form[name].value() not in (None, False)}
    data['pipeline'] = self.first.pk
    response = self.client.post(reverse('cam_calibrate', args=[camera.pk]), data)
    self.assertEqual(response.status_code, 302)
    self.dlsps.create_pipeline.assert_called_once_with('first ! fakesink',
                                                       restart_config=RESTART_CONFIG)
    self.assertEqual(self.instance_id_of(camera), NEW_ID)


class PipelineLifecycleTests(CameraFixturesMixin, TestCase):

  def test_editing_assigned_pipeline_string_restarts_camera(self):
    pipeline = Pipeline.objects.create(name='Edited', pipeline='old ! fakesink')
    camera = self.make_camera(pipeline=pipeline, instance_id=OLD_ID)
    response = self.client.post(reverse('pipeline_update', args=[pipeline.pk]),
                                {'name': 'Edited', 'pipeline': 'new ! fakesink'})
    self.assertRedirects(response, reverse('pipeline_list'))
    self.dlsps.delete_pipeline.assert_called_once_with(OLD_ID)
    self.dlsps.create_pipeline.assert_called_once_with('new ! fakesink',
                                                       restart_config=RESTART_CONFIG)
    self.assertEqual(self.instance_id_of(camera), NEW_ID)

  def test_renaming_assigned_pipeline_does_not_restart(self):
    pipeline = Pipeline.objects.create(name='Named', pipeline='same ! fakesink')
    self.make_camera(pipeline=pipeline, instance_id=OLD_ID)
    self.client.post(reverse('pipeline_update', args=[pipeline.pk]),
                     {'name': 'Renamed', 'pipeline': 'same ! fakesink'})
    self.dlsps_cls.assert_not_called()

  def test_deleting_camera_stops_instance_after_commit(self):
    camera = self.make_camera(pipeline=self.first, instance_id=OLD_ID)
    camera.refresh_from_db()
    with self.captureOnCommitCallbacks(execute=True):
      camera.delete()
      self.dlsps_cls.assert_not_called()
    self.dlsps.delete_pipeline.assert_called_once_with(OLD_ID)

  def test_deleting_camera_without_instance_does_not_contact_dlsps(self):
    camera = self.make_camera(pipeline=self.first)
    with self.captureOnCommitCallbacks(execute=True):
      camera.delete()
    self.dlsps_cls.assert_not_called()

  def test_stop_dlsps_instance_never_raises(self):
    for error in (DLSPSUnavailableError('down'), DLSPSNotFoundError('gone')):
      with self.subTest(error=type(error).__name__):
        self.dlsps.delete_pipeline.side_effect = error
        stop_dlsps_instance(OLD_ID)
    self.dlsps_cls.side_effect = ValueError('no url')
    stop_dlsps_instance(OLD_ID)
