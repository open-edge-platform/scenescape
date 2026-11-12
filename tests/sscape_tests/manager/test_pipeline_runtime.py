# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import hashlib
from unittest.mock import patch
from uuid import UUID

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.db import transaction
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from manager.dlsps import (
  DLSPSBadRequestError,
  DLSPSConflictError,
  DLSPSNotFoundError,
  DLSPSUnavailableError,
  PipelineState,
  PipelineStatus,
  PipelineSummary as DLSPSPipelineSummary,
)
from manager.forms import CamCalibrateForm
from manager.models import Cam, PendingDLSPSStop, Pipeline, Scene, Sensor
from manager.pipeline_runtime import (
  MAX_FILTER_TAG_LENGTH,
  MAX_FILTER_TAGS,
  MAX_PENDING_STOP_ATTEMPTS,
  RESTART_CONFIG,
  PipelineSyncError,
  TagFilter,
  bind_pipeline_to_camera,
  parse_tag_filter,
  reconcile_camera_pipeline,
  retry_pending_stops,
  stop_all_camera_instances,
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


def summary(pipeline_id, name, *variants, tags=()):
  return PipelineSummary(id=pipeline_id, name=name, description='', tags=tuple(tags),
                         variants=tuple(PipelineVariant(id=v, name=v.upper()) for v in variants))


RUNNING = PipelineState.RUNNING
QUEUED = PipelineState.QUEUED
RUNTIME_SETTINGS = {'ENABLE_MLOPS_FLOW': True, 'DLSPS_STOP_TIMEOUT_S': 0}


def pipeline_status(instance_id, state, message=''):
  return PipelineStatus(id=str(instance_id), state=state, avg_fps=0.0, frame_fps=0.0,
                        frame_interval=0.0, start_time=None, first_frame_time=None,
                        elapsed_time=None, message=message)


class MockedClientsMixin:
  """Patch the ViPPET and DLSPS clients where pipeline_runtime looks them up.

  The DLSPS mock keeps instance states in ``self.instances`` like DLSPS does: a stop is only
  accepted for RUNNING/RESTARTING instances and moves them to ``self.state_after_stop``.
  """

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
    self.instances = {}
    self.launches = {}
    self.state_after_stop = PipelineState.ABORTED
    self.dlsps.create_pipeline.side_effect = self._fake_create
    self.dlsps.delete_pipeline.side_effect = self._fake_delete
    self.dlsps.get_pipeline_status.side_effect = self._fake_status
    self.dlsps.get_pipeline.side_effect = self._fake_summary
    self.dlsps.list_pipeline_statuses.side_effect = (
      lambda: [self._fake_status(instance_id) for instance_id in self.instances])
    self._patch('manager.models.sendUpdateCommand')

  def _fake_create(self, pipeline, **_kwargs):
    self.instances[NEW_ID] = (RUNNING, '')
    self.launches[NEW_ID] = pipeline
    return str(NEW_ID)

  def _fake_summary(self, instance_id):
    instance_id = UUID(str(instance_id))
    status = self._fake_status(instance_id)
    return DLSPSPipelineSummary(**vars(status), launch_command=self.launches.get(instance_id))

  def _fake_delete(self, instance_id):
    instance_id = UUID(str(instance_id))
    if instance_id not in self.instances:
      raise DLSPSNotFoundError('gone')
    if self.instances[instance_id][0] not in (RUNNING, PipelineState.RESTARTING):
      raise DLSPSConflictError('not running')
    self.instances[instance_id] = (self.state_after_stop, '')
    return str(instance_id)

  def _fake_status(self, instance_id):
    instance_id = UUID(str(instance_id))
    if instance_id not in self.instances:
      raise DLSPSNotFoundError('gone')
    return pipeline_status(instance_id, *self.instances[instance_id])

  def _patch(self, target, **kwargs):
    patcher = patch(target, **kwargs)
    mocked = patcher.start()
    self.addCleanup(patcher.stop)
    return mocked

  def set_vippet(self, summaries, strings):
    self.vippet.get_pipelines.return_value = summaries
    self.vippet_strings.update(strings)

  def make_camera(self, pipeline=None, instance_id=None, state=RUNNING, message='', **kwargs):
    """Create a camera; with ``instance_id`` it runs ``pipeline`` in DLSPS in ``state``."""
    camera = Cam.objects.create(sensor_id=kwargs.pop('sensor_id', 'runtime-cam'),
                                name=kwargs.pop('name', 'Runtime'), pipeline=pipeline,
                                **kwargs)
    if instance_id is not None:
      digest = None
      if pipeline is not None:
        bound = bind_pipeline_to_camera(pipeline.pipeline, camera.sensor_id)
        digest = hashlib.sha256(bound.encode()).hexdigest()
        self.launches[instance_id] = bound
      Cam.objects.filter(pk=camera.pk).update(dlsps_instance_id=instance_id,
                                              dlsps_pipeline_digest=digest)
      if state is not None:
        self.instances[instance_id] = (state, message)
    return camera

  def instance_id_of(self, camera):
    return Cam.objects.get(pk=camera.pk).dlsps_instance_id


@override_settings(**RUNTIME_SETTINGS)
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


@override_settings(ENABLE_MLOPS_FLOW=True)
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
    # Drop the stored messages so the next save in the same test reports only its own.
    self.client.cookies.pop('messages', None)
    return [str(m) for m in get_messages(response.wsgi_request)]


@override_settings(**RUNTIME_SETTINGS)
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

  def test_start_binds_publish_element_to_camera(self):
    shared = Pipeline.objects.create(
      name='Shared', pipeline='src ! sscape_post_inference_data_publish name=dp ! fakesink')
    camera = self.make_camera(pipeline=shared, scene=self.scene, sensor_id='qcam1')
    reconcile_camera_pipeline(camera.pk)
    self.dlsps.create_pipeline.assert_called_once_with(
      'src ! sscape_post_inference_data_publish name=dp cameraid="qcam1" ! fakesink',
      restart_config=RESTART_CONFIG)

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
    self.dlsps.delete_pipeline.assert_not_called()
    self.dlsps.create_pipeline.assert_not_called()
    self.assertEqual(self.instance_id_of(camera), OLD_ID)

  def test_unchanged_pipeline_without_instance_is_retried(self):
    camera = self.make_camera(pipeline=self.first, scene=self.scene)
    self.update_camera(camera, self.first)
    self.dlsps.create_pipeline.assert_called_once()
    self.assertEqual(self.instance_id_of(camera), NEW_ID)

  def test_changing_camera_id_rebinds_running_pipeline(self):
    publishing = Pipeline.objects.create(
      name='Publishing', pipeline='src ! sscape_post_inference_data_publish ! fakesink')
    camera = self.make_camera(pipeline=publishing, instance_id=OLD_ID, scene=self.scene,
                              sensor_id='old-id')
    camera.sensor_id = 'new-id'
    self.assertEqual(self.update_camera(camera, publishing), [])
    self.dlsps.delete_pipeline.assert_called_once_with(OLD_ID)
    self.dlsps.create_pipeline.assert_called_once_with(
      'src ! sscape_post_inference_data_publish cameraid="new-id" ! fakesink',
      restart_config=RESTART_CONFIG)

  def test_start_failure_saves_camera_and_warns(self):
    self.dlsps.create_pipeline.side_effect = DLSPSBadRequestError('invalid pipeline')
    camera = self.make_camera(scene=self.scene)
    warnings = self.update_camera(camera, self.first)
    self.assertEqual(len(warnings), 1)
    self.assertIn("failed to start pipeline 'First'", warnings[0])
    self.assertEqual(Cam.objects.get(pk=camera.pk).pipeline, self.first)
    self.assertIsNone(self.instance_id_of(camera))

  def test_unanswered_start_is_adopted_instead_of_started_again(self):
    def start_without_answer(pipeline, **kwargs):
      self._fake_create(pipeline, **kwargs)
      raise DLSPSUnavailableError('read timeout')
    self.dlsps.create_pipeline.side_effect = start_without_answer
    camera = self.make_camera(scene=self.scene)
    warnings = self.update_camera(camera, self.first)
    self.assertIn('did not confirm the start', warnings[0])
    self.assertTrue(Cam.objects.get(pk=camera.pk).dlsps_start_uncertain)
    self.assertIsNone(self.instance_id_of(camera))
    self.assertEqual(self.update_camera(camera, self.first), [])
    self.dlsps.create_pipeline.assert_called_once()
    camera = Cam.objects.get(pk=camera.pk)
    self.assertEqual((camera.dlsps_instance_id, camera.dlsps_start_uncertain), (NEW_ID, False))

  def test_unanswered_start_that_created_nothing_is_retried(self):
    self.dlsps.create_pipeline.side_effect = ['not-a-uuid', str(NEW_ID)]
    camera = self.make_camera(pipeline=self.first, scene=self.scene)
    self.assertEqual(len(reconcile_camera_pipeline(camera.pk)), 1)
    self.assertTrue(Cam.objects.get(pk=camera.pk).dlsps_start_uncertain)
    self.instances[NEW_ID] = (RUNNING, '')
    self.assertEqual(reconcile_camera_pipeline(camera.pk), [])
    self.assertEqual(self.dlsps.create_pipeline.call_count, 2)
    self.assertEqual(self.instance_id_of(camera), NEW_ID)

  def test_unanswered_start_is_not_repeated_while_dlsps_cannot_be_checked(self):
    self.dlsps.create_pipeline.side_effect = DLSPSUnavailableError('read timeout')
    camera = self.make_camera(pipeline=self.first, scene=self.scene)
    reconcile_camera_pipeline(camera.pk)
    self.dlsps.list_pipeline_statuses.side_effect = DLSPSUnavailableError('down')
    warnings = reconcile_camera_pipeline(camera.pk)
    self.assertIn('could not check whether its last pipeline start reached', warnings[0])
    self.dlsps.create_pipeline.assert_called_once()
    self.assertTrue(Cam.objects.get(pk=camera.pk).dlsps_start_uncertain)

  def test_unconfirmed_stop_keeps_instance_and_skips_start(self):
    cases = {
      'stop request fails': lambda: setattr(self.dlsps.delete_pipeline, 'side_effect',
                                            DLSPSUnavailableError('down')),
      'stop still in progress': lambda: setattr(self, 'state_after_stop', RUNNING),
      'instance queued': lambda: self.instances.update({OLD_ID: (QUEUED, '')}),
    }
    for name, arrange in cases.items():
      with self.subTest(name):
        Cam.objects.all().delete()
        self.dlsps.reset_mock()
        camera = self.make_camera(pipeline=self.first, instance_id=OLD_ID, scene=self.scene)
        arrange()
        warnings = self.update_camera(camera, self.second)
        self.assertEqual(len(warnings), 1)
        self.assertIn('has not stopped yet', warnings[0])
        self.dlsps.create_pipeline.assert_not_called()
        self.assertEqual(self.instance_id_of(camera), OLD_ID)
        self.dlsps.delete_pipeline.side_effect = self._fake_delete
        self.state_after_stop = PipelineState.ABORTED

  def test_replacement_is_retried_after_unconfirmed_stop(self):
    camera = self.make_camera(pipeline=self.first, instance_id=OLD_ID, scene=self.scene)
    self.state_after_stop = RUNNING
    self.update_camera(camera, self.second)
    self.assertEqual(self.instance_id_of(camera), OLD_ID)
    self.state_after_stop = PipelineState.ABORTED
    self.assertEqual(self.update_camera(camera, self.second), [])
    self.dlsps.create_pipeline.assert_called_once_with('second ! fakesink',
                                                       restart_config=RESTART_CONFIG)
    self.assertEqual(self.instance_id_of(camera), NEW_ID)

  def test_stop_waits_until_instance_ended(self):
    camera = self.make_camera(pipeline=self.first, instance_id=OLD_ID, scene=self.scene)
    self.state_after_stop = RUNNING
    sleep = self._patch('manager.pipeline_runtime.time.sleep', side_effect=(
      lambda _seconds: self.instances.update({OLD_ID: (PipelineState.ABORTED, '')})))
    with override_settings(DLSPS_STOP_TIMEOUT_S=5):
      self.assertEqual(self.update_camera(camera, self.second), [])
    sleep.assert_called_once()
    self.assertEqual(self.instance_id_of(camera), NEW_ID)

  def test_ended_instance_is_replaced(self):
    for state in (None, PipelineState.COMPLETED, PipelineState.ABORTED):
      with self.subTest(state=state):
        Cam.objects.all().delete()
        self.dlsps.reset_mock()
        self.instances.clear()
        camera = self.make_camera(pipeline=self.first, instance_id=OLD_ID, state=state)
        self.assertEqual(reconcile_camera_pipeline(camera.pk), [])
        self.dlsps.delete_pipeline.assert_not_called()
        self.dlsps.create_pipeline.assert_called_once()
        self.assertEqual(self.instance_id_of(camera), NEW_ID)

  def test_failed_instance_is_reported_and_restarted(self):
    camera = self.make_camera(pipeline=self.first, instance_id=OLD_ID, scene=self.scene,
                              state=PipelineState.ERROR, message='validation failed: bad model')
    warnings = self.update_camera(camera, self.first)
    self.assertEqual(len(warnings), 1)
    self.assertIn('previous DLSPS pipeline failed: validation failed: bad model', warnings[0])
    self.dlsps.create_pipeline.assert_called_once()
    self.assertEqual(self.instance_id_of(camera), NEW_ID)

  def test_unreachable_dlsps_keeps_instance(self):
    self.dlsps.get_pipeline_status.side_effect = DLSPSUnavailableError('down')
    camera = self.make_camera(pipeline=self.first, instance_id=OLD_ID, scene=self.scene)
    warnings = self.update_camera(camera, self.second)
    self.assertIn('could not check its DLSPS pipeline', warnings[0])
    self.dlsps.create_pipeline.assert_not_called()
    self.assertEqual(self.instance_id_of(camera), OLD_ID)

  def test_stale_camera_save_keeps_recorded_instance(self):
    camera = self.make_camera(pipeline=self.first, scene=self.scene)
    stale = Cam.objects.get(pk=camera.pk)
    reconcile_camera_pipeline(camera.pk)
    stale.name = 'Renamed'
    stale.save()
    camera = Cam.objects.get(pk=camera.pk)
    self.assertEqual((camera.name, camera.dlsps_instance_id), ('Renamed', NEW_ID))
    self.assertIsNotNone(camera.dlsps_pipeline_digest)

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

  def test_camera_page_shows_live_instance_state(self):
    camera = self.make_camera(pipeline=self.first, instance_id=OLD_ID, scene=self.scene,
                              state=PipelineState.ERROR, message='<b>bad model</b>')
    response = self.client.get(reverse('cam_update', args=[camera.pk]))
    self.assertContains(response, '<span id="camera-dlsps-instance-state">ERROR</span>',
                        html=True)
    self.assertContains(response, '&lt;b&gt;bad model&lt;/b&gt;')
    self.dlsps.get_pipeline_status.side_effect = DLSPSUnavailableError('down')
    response = self.client.get(reverse('cam_update', args=[camera.pk]))
    self.assertContains(response, '<span id="camera-dlsps-instance-state">UNKNOWN</span>',
                        html=True)

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


@override_settings(**RUNTIME_SETTINGS)
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
      self.assertTrue(PendingDLSPSStop.objects.filter(instance_id=OLD_ID).exists())
    self.dlsps.delete_pipeline.assert_called_once_with(OLD_ID)
    self.assertFalse(PendingDLSPSStop.objects.exists())

  def test_deleting_stale_camera_stops_instance_recorded_since_loading(self):
    for delete in ('instance', 'queryset', 'sensor cascade'):
      with self.subTest(delete=delete):
        self.dlsps.reset_mock()
        camera = self.make_camera(pipeline=self.first, sensor_id=delete[:20])
        stale = Cam.objects.get(pk=camera.pk)
        reconcile_camera_pipeline(camera.pk)
        with self.captureOnCommitCallbacks(execute=True):
          if delete == 'instance':
            stale.delete()
          elif delete == 'queryset':
            Cam.objects.filter(pk=camera.pk).delete()
          else:
            Sensor.objects.filter(pk=camera.pk).delete()
        self.dlsps.delete_pipeline.assert_called_once_with(NEW_ID)
        self.instances.clear()

  def test_rolled_back_delete_keeps_camera_and_instance(self):
    camera = self.make_camera(pipeline=self.first, instance_id=OLD_ID)
    camera_pk = camera.pk
    with self.captureOnCommitCallbacks(execute=True):
      try:
        with transaction.atomic():
          camera.delete()
          raise RuntimeError('rollback')
      except RuntimeError:
        pass
    self.dlsps.delete_pipeline.assert_not_called()
    self.assertFalse(PendingDLSPSStop.objects.exists())
    self.assertEqual(Cam.objects.get(pk=camera_pk).dlsps_instance_id, OLD_ID)

  def test_deleting_camera_with_unanswered_start_stops_matching_instance(self):
    self.dlsps.create_pipeline.side_effect = ['not-a-uuid']
    camera = self.make_camera(pipeline=self.first)
    reconcile_camera_pipeline(camera.pk)
    self.instances[OLD_ID] = (RUNNING, '')
    self.launches[OLD_ID] = 'first ! fakesink'
    with self.captureOnCommitCallbacks(execute=True):
      camera.delete()
    self.dlsps.delete_pipeline.assert_called_once_with(OLD_ID)
    self.assertFalse(PendingDLSPSStop.objects.exists())

  def test_deleting_camera_without_instance_does_not_contact_dlsps(self):
    camera = self.make_camera(pipeline=self.first)
    with self.captureOnCommitCallbacks(execute=True):
      camera.delete()
    self.dlsps_cls.assert_not_called()

  def test_unconfirmed_stop_of_deleted_camera_is_retried(self):
    camera = self.make_camera(pipeline=self.first, instance_id=OLD_ID, state=QUEUED)
    camera.refresh_from_db()
    with self.captureOnCommitCallbacks(execute=True):
      camera.delete()
    self.dlsps.delete_pipeline.assert_not_called()
    self.assertTrue(PendingDLSPSStop.objects.filter(instance_id=OLD_ID).exists())
    self.instances[OLD_ID] = (RUNNING, '')
    retry_pending_stops()
    self.dlsps.delete_pipeline.assert_called_once_with(OLD_ID)
    self.assertFalse(PendingDLSPSStop.objects.exists())

  def test_pending_stop_gives_up_after_max_attempts(self):
    self.instances[OLD_ID] = (QUEUED, '')
    PendingDLSPSStop.objects.create(instance_id=OLD_ID)
    for _ in range(MAX_PENDING_STOP_ATTEMPTS - 1):
      retry_pending_stops()
    self.assertEqual(PendingDLSPSStop.objects.get().attempts, MAX_PENDING_STOP_ATTEMPTS - 1)
    retry_pending_stops()
    self.assertFalse(PendingDLSPSStop.objects.exists())

  def test_pending_stop_survives_unreachable_or_unconfigured_dlsps(self):
    self.dlsps.delete_pipeline.side_effect = DLSPSUnavailableError('down')
    for instance_id in (OLD_ID, NEW_ID):
      camera = self.make_camera(pipeline=self.first, instance_id=instance_id,
                                sensor_id=str(instance_id)[:20])
      with self.captureOnCommitCallbacks(execute=True):
        camera.delete()
      self.dlsps_cls.side_effect = ValueError('no url')
    self.assertEqual(set(PendingDLSPSStop.objects.values_list('instance_id', flat=True)),
                     {OLD_ID, NEW_ID})

  def test_sync_retries_pending_stops_without_pipeline_changes(self):
    self.instances[OLD_ID] = (RUNNING, '')
    PendingDLSPSStop.objects.create(instance_id=OLD_ID)
    self.set_vippet([], {})
    sync_vippet_pipelines()
    self.dlsps.delete_pipeline.assert_called_once_with(OLD_ID)
    self.assertFalse(PendingDLSPSStop.objects.exists())

  def test_rest_camera_id_change_rebinds_pipeline(self):
    publishing = Pipeline.objects.create(
      name='Publishing', pipeline='src ! sscape_post_inference_data_publish ! fakesink')
    camera = self.make_camera(pipeline=publishing, instance_id=OLD_ID, sensor_id='old-id')
    client = APIClient()
    client.force_authenticate(self.admin)
    response = client.put('/api/v1/camera/old-id', {'name': 'Runtime', 'sensor_id': 'new-id'},
                          format='json')
    self.assertEqual(response.status_code, 200, response.content)
    self.dlsps.delete_pipeline.assert_called_once_with(OLD_ID)
    self.dlsps.create_pipeline.assert_called_once_with(
      'src ! sscape_post_inference_data_publish cameraid="new-id" ! fakesink',
      restart_config=RESTART_CONFIG)
    self.assertEqual(self.instance_id_of(camera), NEW_ID)

  def test_stop_all_camera_instances_resolves_unanswered_starts(self):
    self.dlsps.create_pipeline.side_effect = ['not-a-uuid']
    camera = self.make_camera(pipeline=self.first)
    reconcile_camera_pipeline(camera.pk)
    self.instances[OLD_ID] = (RUNNING, '')
    self.launches[OLD_ID] = 'first ! fakesink'
    stop_all_camera_instances()
    self.dlsps.delete_pipeline.assert_called_once_with(OLD_ID)
    camera = Cam.objects.get(pk=camera.pk)
    self.assertEqual((camera.dlsps_instance_id, camera.dlsps_start_uncertain), (None, False))


class BindPipelineToCameraTests(SimpleTestCase):

  def test_quoted_element_name_is_left_alone(self):
    for pipeline in (
        'videotestsrc ! textoverlay text="sscape_post_inference_data_publish" ! fakesink',
        "videotestsrc ! textoverlay text='a sscape_post_inference_data_publish b' ! fakesink",
        'textoverlay text="x \\" sscape_post_inference_data_publish" ! fakesink',
        'textoverlay text="unterminated sscape_post_inference_data_publish ! fakesink'):
      with self.subTest(pipeline=pipeline):
        self.assertEqual(bind_pipeline_to_camera(pipeline, 'c1'), pipeline)

  def test_quoted_property_values_with_spaces_and_links_are_kept(self):
    self.assertEqual(
      bind_pipeline_to_camera(
        'a ! sscape_post_inference_data_publish label="a ! b c" cameraid="x y"'
        ' track-topic=t!fakesink', 'c1'),
      'a ! sscape_post_inference_data_publish label="a ! b c" track-topic=t cameraid="c1"'
      '!fakesink')

  def test_adds_cameraid_to_publish_element(self):
    self.assertEqual(
      bind_pipeline_to_camera('a ! sscape_post_inference_data_publish ! gvametapublish', 'c1'),
      'a ! sscape_post_inference_data_publish cameraid="c1" ! gvametapublish')

  def test_replaces_existing_cameraid_and_keeps_other_properties(self):
    self.assertEqual(
      bind_pipeline_to_camera(
        'a ! sscape_post_inference_data_publish cameraid="old cam" name=dp publish-image=true',
        'c1'),
      'a ! sscape_post_inference_data_publish name=dp publish-image=true cameraid="c1"')

  def test_escapes_quotes_in_sensor_id(self):
    self.assertEqual(bind_pipeline_to_camera('sscape_post_inference_data_publish', 'a"b'),
                     'sscape_post_inference_data_publish cameraid="a\\"b"')

  def test_leaves_pipelines_without_publish_element_unchanged(self):
    pipeline = ('src ! my_sscape_post_inference_data_publish ! '
                'sscape_post_inference_data_publish_x ! fakesink')
    self.assertEqual(bind_pipeline_to_camera(pipeline, 'c1'), pipeline)


class TagFilterParsingTests(SimpleTestCase):

  def test_blank_input_means_no_filter(self):
    for text in (None, '', '   ', ' , ,, '):
      with self.subTest(text=text):
        tag_filter = parse_tag_filter(text)
        self.assertEqual(tag_filter.labels, ())
        self.assertTrue(tag_filter.matches([]))
        self.assertTrue(tag_filter.matches(['Anything']))

  def test_tags_are_trimmed_and_deduplicated_ignoring_case(self):
    tag_filter = parse_tag_filter(' Scenescape , retail,SCENESCAPE,, Retail ', match_all=True)
    self.assertEqual(tag_filter.labels, ('Scenescape', 'retail'))
    self.assertTrue(tag_filter.match_all)
    self.assertEqual(tag_filter.describe(), 'tags all of: Scenescape, retail')

  def test_limits_are_enforced(self):
    self.assertEqual(len(parse_tag_filter(','.join(f't{i}' for i in range(MAX_FILTER_TAGS))).labels),
                     MAX_FILTER_TAGS)
    self.assertEqual(parse_tag_filter('x' * MAX_FILTER_TAG_LENGTH).labels, ('x' * MAX_FILTER_TAG_LENGTH,))
    invalid = (','.join(f't{i}' for i in range(MAX_FILTER_TAGS + 1)),
               'x' * (MAX_FILTER_TAG_LENGTH + 1), 'bad\ttag', 'bad\x00tag')
    for text in invalid:
      with self.subTest(text=text[:30]), self.assertRaises(ValueError):
        parse_tag_filter(text)

  def test_any_and_all_matching_ignore_case(self):
    any_filter = TagFilter(labels=('scenescape', 'Manufacturing'))
    all_filter = TagFilter(labels=('retail', 'SCENESCAPE'), match_all=True)
    cases = (
      (['Retail', 'Scenescape'], True, True),
      (['Retail'], False, False),
      (['Scenescape'], True, False),
      (['manufacturing'], True, False),
      ([], False, False),
      (['Retail Scenescape'], False, False),
    )
    for tags, any_expected, all_expected in cases:
      with self.subTest(tags=tags):
        self.assertEqual(any_filter.matches(tags), any_expected)
        self.assertEqual(all_filter.matches(tags), all_expected)


@override_settings(ENABLE_MLOPS_FLOW=True)
class ViPPETTagFilteredSyncTests(MockedClientsMixin, TestCase):

  def setUp(self):
    super().setUp()
    self.set_vippet(
      [summary('queuing', 'Queuing', 'cpu', 'gpu', tags=['Scenescape', 'Retail']),
       summary('parking', 'Parking', 'cpu', tags=['Smart Cities']),
       summary('shelf', 'Shelf', 'cpu', tags=['retail']),
       summary('untagged', 'Untagged', 'cpu')],
      {('queuing', 'cpu'): 'q-cpu', ('queuing', 'gpu'): 'q-gpu', ('parking', 'cpu'): 'p-cpu',
       ('shelf', 'cpu'): 's-cpu', ('untagged', 'cpu'): 'u-cpu'})

  def fetched_ids(self):
    return {call.args for call in self.vippet.get_pipeline_string.call_args_list}

  def test_any_filter_imports_only_matching_pipelines(self):
    result = sync_vippet_pipelines(parse_tag_filter('scenescape'))
    self.assertEqual(result.created, ['Queuing (CPU)', 'Queuing (GPU)'])
    self.assertEqual((result.pipelines_matched, result.pipelines_total), (1, 4))
    self.assertEqual(self.fetched_ids(), {('queuing', 'cpu'), ('queuing', 'gpu')})
    self.assertEqual(set(Pipeline.objects.values_list('vippet_pipeline_id', flat=True)),
                     {'queuing/cpu', 'queuing/gpu'})

  def test_any_filter_with_several_tags(self):
    result = sync_vippet_pipelines(parse_tag_filter('Retail, Smart Cities'))
    self.assertEqual(result.pipelines_matched, 3)
    self.assertEqual(sorted(result.created),
                     ['Parking (CPU)', 'Queuing (CPU)', 'Queuing (GPU)', 'Shelf (CPU)'])

  def test_all_filter_requires_every_tag(self):
    result = sync_vippet_pipelines(parse_tag_filter('RETAIL, scenescape', match_all=True))
    self.assertEqual(result.pipelines_matched, 1)
    self.assertEqual(result.created, ['Queuing (CPU)', 'Queuing (GPU)'])

  def test_no_filter_imports_everything(self):
    for tag_filter in (None, parse_tag_filter('')):
      with self.subTest(tag_filter=tag_filter):
        result = sync_vippet_pipelines(tag_filter)
        self.assertEqual(result.pipelines_matched, 4)
    self.assertEqual(Pipeline.objects.count(), 5)

  def test_no_match_imports_nothing(self):
    result = sync_vippet_pipelines(parse_tag_filter('Manufacturing'))
    self.assertEqual((result.created, result.pipelines_matched), ([], 0))
    self.vippet.get_pipeline_string.assert_not_called()

  def test_previously_imported_non_matching_variant_is_still_updated(self):
    parking = Pipeline.objects.create(name='Parking (CPU)', pipeline='old',
                                      vippet_pipeline_id='parking/cpu')
    camera = self.make_camera(pipeline=parking, instance_id=OLD_ID)
    result = sync_vippet_pipelines(parse_tag_filter('Scenescape'))
    self.assertEqual(sorted(result.updated + result.created),
                     ['Parking (CPU)', 'Queuing (CPU)', 'Queuing (GPU)'])
    self.assertEqual(result.updated, ['Parking (CPU)'])
    parking.refresh_from_db()
    self.assertEqual(parking.pipeline, 'p-cpu')
    self.dlsps.delete_pipeline.assert_called_once_with(OLD_ID)
    self.assertEqual(self.instance_id_of(camera), NEW_ID)
    self.assertNotIn(('shelf', 'cpu'), self.fetched_ids())


@override_settings(ENABLE_MLOPS_FLOW=True)
class PipelineSyncViewTagTests(MockedClientsMixin, TestCase):

  @classmethod
  def setUpTestData(cls):
    cls.admin = get_user_model().objects.create_user(
      username='tag-admin', is_staff=True, is_superuser=True)

  def setUp(self):
    super().setUp()
    self.client.force_login(self.admin)
    self.url = reverse('pipeline_sync')
    self.set_vippet(
      [summary('queuing', 'Queuing', 'cpu', tags=['Scenescape', 'Retail']),
       summary('parking', 'Parking', 'cpu', tags=['Smart Cities'])],
      {('queuing', 'cpu'): 'q-cpu', ('parking', 'cpu'): 'p-cpu'})

  def test_filter_is_applied_and_reported(self):
    response = self.client.post(self.url, {'tags': 'scenescape, Retail', 'tag_match': 'all'},
                                follow=True)
    self.assertContains(response, 'Synced with ViPPET (tags all of: scenescape, Retail): '
                                  '1 of 2 pipelines matched; 1 created, 0 updated, 0 unchanged.')
    self.assertEqual(list(Pipeline.objects.values_list('name', flat=True)), ['Queuing (CPU)'])

  def test_last_filter_is_prefilled(self):
    self.client.post(self.url, {'tags': 'Scenescape', 'tag_match': 'all'})
    page = self.client.get(reverse('pipeline_list'))
    self.assertContains(page, 'value="Scenescape"')
    self.assertRegex(page.content.decode(), r'<input[^>]*value="all"[^>]*checked')
    other_client = Client()
    other_client.force_login(self.admin)
    self.assertNotContains(other_client.get(reverse('pipeline_list')), 'value="Scenescape"')

  def test_default_form_has_empty_filter_and_any(self):
    page = self.client.get(reverse('pipeline_list')).content.decode()
    self.assertRegex(page, r'<input type="text" name="tags"(?![^>]*value=)[^>]*>')
    self.assertRegex(page, r'<input[^>]*value="any"[^>]*checked')
    self.assertIn('id="pipeline-sync-form"', page)

  def test_missing_fields_sync_everything(self):
    response = self.client.post(self.url, follow=True)
    self.assertContains(response, 'Synced with ViPPET: 2 created, 0 updated, 0 unchanged.')

  def test_invalid_filter_is_rejected_without_contacting_vippet(self):
    for data in ({'tags': 'x' * (MAX_FILTER_TAG_LENGTH + 1)}, {'tags': 'a', 'tag_match': 'some'},
                 {'tags': 'x' * 2001}):
      with self.subTest(data={k: v[:20] for k, v in data.items()}):
        response = self.client.post(self.url, data, follow=True)
        self.assertContains(response, 'alert-danger')
        self.assertContains(response, 'Sync with ViPPET:')
    self.vippet_cls.assert_not_called()
    self.assertFalse(Pipeline.objects.exists())

  def test_filter_text_is_escaped(self):
    response = self.client.post(self.url, {'tags': '<script>alert(1)</script>'}, follow=True)
    self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
    self.assertNotContains(response, '<script>alert(1)</script>')
