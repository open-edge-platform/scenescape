# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from importlib import import_module
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from rest_framework.test import APIRequestFactory, force_authenticate

from manager.api import ManageThing
from manager.forms import CamCalibrateForm, CamCreateForm, PipelineForm
from manager.models import Cam, Pipeline, Scene
from manager.serializers import CamSerializer
from manager.views import CamUpdateView


class PipelineFormTests(TestCase):

  def test_pipeline_preserves_whitespace(self):
    text = '  videotestsrc !\n  fakesink  '
    field = PipelineForm.base_fields['pipeline']
    self.assertEqual(field.clean(text), text)

  def test_blank_pipeline_is_rejected(self):
    form = PipelineForm(data={'name': 'Blank', 'pipeline': ' \n '})
    self.assertFalse(form.is_valid())
    self.assertIn('pipeline', form.errors)

  def test_form_uses_responsive_styled_widgets(self):
    form = PipelineForm()
    self.assertEqual(form.fields['name'].widget.attrs['class'], 'form-control')
    editor_attrs = form.fields['pipeline'].widget.attrs
    self.assertEqual(editor_attrs['class'], 'form-control text-monospace')
    self.assertEqual(editor_attrs['rows'], 12)
    self.assertEqual(editor_attrs['spellcheck'], 'false')

  def test_camera_forms_offer_pipeline(self):
    self.assertIn('pipeline', CamCreateForm.base_fields)
    self.assertIn('pipeline', CamCalibrateForm.base_fields)
    self.assertIn('pipeline', CamUpdateView.fields)
    self.assertFalse(CamCreateForm.base_fields['pipeline'].required)

  def test_pipeline_not_added_to_camera_api(self):
    self.assertNotIn('pipeline', CamSerializer().fields)


class PipelineTests(TestCase):

  @classmethod
  def setUpTestData(cls):
    cls.admin = get_user_model().objects.create_user(
      username='pipeline-admin', is_staff=True, is_superuser=True)
    cls.reader = get_user_model().objects.create_user(username='pipeline-reader')

  def setUp(self):
    self.client.force_login(self.admin)

  def test_unique_names(self):
    Pipeline.objects.create(name='Shared', pipeline='videotestsrc ! fakesink')
    with self.assertRaises(IntegrityError), transaction.atomic():
      Pipeline.objects.create(name='Shared', pipeline='fakesrc ! fakesink')

  def test_names_sorted(self):
    Pipeline.objects.create(name='Zebra', pipeline='fakesrc ! fakesink')
    Pipeline.objects.create(name='Alpha', pipeline='fakesrc ! fakesink')
    self.assertEqual(list(Pipeline.objects.values_list('name', flat=True)), ['Alpha', 'Zebra'])

  def test_form_rejects_duplicate_name(self):
    Pipeline.objects.create(name='Shared', pipeline='fakesrc ! fakesink')
    form = PipelineForm(data={'name': 'Shared', 'pipeline': 'videotestsrc ! fakesink'})
    self.assertFalse(form.is_valid())
    self.assertIn('name', form.errors)

  def test_many_cameras_and_delete_clears_references(self):
    pipeline = Pipeline.objects.create(name='Shared', pipeline='fakesrc ! fakesink')
    with patch('manager.models.sendUpdateCommand'):
      first = Cam.objects.create(sensor_id='pipeline-first', name='First', pipeline=pipeline)
      second = Cam.objects.create(sensor_id='pipeline-second', name='Second', pipeline=pipeline)
      self.assertEqual(pipeline.cameras.count(), 2)
      pipeline.delete()
    for camera in (first, second):
      camera.refresh_from_db()
      self.assertIsNone(camera.pipeline_id)

  def test_pipeline_does_not_change_camera_runtime_data(self):
    pipeline = Pipeline.objects.create(name='Shared', pipeline='fakesrc ! fakesink')
    camera = Cam(sensor_id='pipeline-runtime', name='Runtime')
    before = camera.cameraData('update')
    camera.pipeline = pipeline
    self.assertEqual(camera.cameraData('update'), before)

  def test_list_requires_login(self):
    self.client.logout()
    self.assertEqual(self.client.get(reverse('pipeline_list')).status_code, 302)

  def test_empty_list_and_navigation(self):
    response = self.client.get(reverse('pipeline_list'))
    self.assertContains(response, 'No pipelines have been created.')
    page = response.content.decode()
    self.assertLess(page.index('nav-object-library'), page.index('nav-pipelines'))

  def test_list_escapes_pipeline(self):
    Pipeline.objects.create(name='<b>Name</b>', pipeline='<script>alert(1)</script>')
    response = self.client.get(reverse('pipeline_list'))
    self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
    self.assertNotContains(response, '<script>alert(1)</script>')

  def test_reader_can_list_but_cannot_mutate(self):
    pipeline = Pipeline.objects.create(name='Shared', pipeline='fakesrc ! fakesink')
    self.client.force_login(self.reader)
    response = self.client.get(reverse('pipeline_list'))
    self.assertEqual(response.status_code, 200)
    self.assertNotContains(response, '+ New Pipeline')
    for url in (reverse('pipeline_create'),
                reverse('pipeline_update', args=[pipeline.pk]),
                reverse('pipeline_delete', args=[pipeline.pk])):
      for method in (self.client.get, self.client.post):
        with self.subTest(url=url, method=method.__name__):
          self.assertEqual(method(url).status_code, 403)

  def test_create_update_delete(self):
    response = self.client.post(reverse('pipeline_create'),
                                {'name': 'Shared', 'pipeline': 'fakesrc ! fakesink'})
    self.assertRedirects(response, reverse('pipeline_list'))
    pipeline = Pipeline.objects.get(name='Shared')
    self.assertEqual(str(pipeline), 'Shared')
    self.assertContains(self.client.get(reverse('pipeline_update', args=[pipeline.pk])),
                        'Save Pipeline')
    response = self.client.post(reverse('pipeline_update', args=[pipeline.pk]),
                                {'name': 'Updated', 'pipeline': 'videotestsrc ! fakesink'})
    self.assertRedirects(response, reverse('pipeline_list'))
    pipeline.refresh_from_db()
    self.assertEqual(pipeline.name, 'Updated')
    response = self.client.get(reverse('pipeline_delete', args=[pipeline.pk]))
    self.assertContains(response, 'Associated cameras will be kept')
    self.assertTrue(Pipeline.objects.filter(pk=pipeline.pk).exists())
    response = self.client.post(reverse('pipeline_delete', args=[pipeline.pk]))
    self.assertRedirects(response, reverse('pipeline_list'))
    self.assertFalse(Pipeline.objects.filter(pk=pipeline.pk).exists())

  def test_mutations_require_csrf(self):
    client = Client(enforce_csrf_checks=True)
    client.force_login(self.admin)
    response = client.post(reverse('pipeline_create'), {'name': 'Rejected', 'pipeline': 'fakesink'})
    self.assertEqual(response.status_code, 403)
    self.assertFalse(Pipeline.objects.filter(name='Rejected').exists())

  def test_scene_creation_serializes_cameras_with_migrated_schema(self):
    request = APIRequestFactory().post(
      '/api/v1/scene', {'name': 'Import regression', 'scale': 100}, format='json')
    force_authenticate(request, user=self.admin)
    with patch('manager.models.sendUpdateCommand'):
      response = ManageThing.as_view()(request, thing_type='scene')
    self.assertEqual(response.status_code, 201)
    self.assertNotIn('cameras', response.data)
    self.assertTrue(Scene.objects.filter(name='Import regression').exists())

  def test_migration_matches_pipeline_model(self):
    executor = MigrationExecutor(connection)
    state = executor.loader.project_state()
    historical = state.apps.get_model('manager', 'Pipeline')
    for name in ('id', 'name', 'pipeline'):
      self.assertEqual(historical._meta.get_field(name).deconstruct()[1:],
                       Pipeline._meta.get_field(name).deconstruct()[1:])
    module = import_module('manager.migrations.0006_pipeline_cam_pipeline')
    self.assertEqual(len(module.Migration.operations), 2)


class PipelineMigrationTests(TransactionTestCase):

  def test_upgrade_and_rollback_preserve_camera(self):
    old_target = [('manager', '0005_default_asset3d_objects')]
    new_target = [('manager', '0006_pipeline_cam_pipeline')]
    executor = MigrationExecutor(connection)
    executor.migrate(old_target)
    try:
      old_apps = executor.loader.project_state(old_target).apps
      camera = old_apps.get_model('manager', 'Cam').objects.create(
        sensor_id='migration-camera', name='Existing')
      camera_pk = camera.pk
      executor = MigrationExecutor(connection)
      executor.migrate(new_target)
      apps = executor.loader.project_state(new_target).apps
      camera_model = apps.get_model('manager', 'Cam')
      self.assertIsNone(camera_model.objects.get(pk=camera_pk).pipeline_id)
      pipeline = apps.get_model('manager', 'Pipeline').objects.create(
        name='Migrated', pipeline='fakesrc ! fakesink')
      camera_model.objects.filter(pk=camera_pk).update(pipeline_id=pipeline.pk)
      executor = MigrationExecutor(connection)
      executor.migrate(old_target)
      self.assertTrue(old_apps.get_model('manager', 'Cam').objects.filter(pk=camera_pk).exists())
    finally:
      MigrationExecutor(connection).migrate(new_target)
