# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from importlib import import_module
from unittest.mock import patch
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from rest_framework.test import APIRequestFactory, force_authenticate

from manager.api import ManageThing
from manager.forms import CamCalibrateForm, CamCreateForm, CamUpdateForm, PipelineForm
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
    self.assertIn('pipeline', CamUpdateView.form_class.base_fields)
    self.assertFalse(CamCreateForm.base_fields['pipeline'].required)

  def test_pipeline_not_added_to_camera_api(self):
    self.assertNotIn('pipeline', CamSerializer().fields)

  def test_dlsps_instance_id_is_not_editable(self):
    self.assertFalse(Pipeline._meta.get_field('dlsps_instance_id').editable)
    self.assertNotIn('dlsps_instance_id', PipelineForm.base_fields)


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

  def test_dlsps_instance_id_is_optional_and_persisted(self):
    pipeline = Pipeline.objects.create(name='External', pipeline='fakesrc ! fakesink')
    pipeline.refresh_from_db()
    self.assertIsNone(pipeline.dlsps_instance_id)
    instance_id = UUID('3f1c0d2e-8a4b-4d6c-9e1f-2a3b4c5d6e7f')
    pipeline.dlsps_instance_id = instance_id
    pipeline.save(update_fields=['dlsps_instance_id'])
    pipeline.refresh_from_db()
    self.assertEqual(pipeline.dlsps_instance_id, instance_id)

  def test_user_cannot_set_or_overwrite_dlsps_instance_id(self):
    instance_id = UUID('3f1c0d2e-8a4b-4d6c-9e1f-2a3b4c5d6e7f')
    data = {'name': 'External', 'pipeline': 'fakesrc ! fakesink',
            'dlsps_instance_id': str(instance_id)}
    response = self.client.post(reverse('pipeline_create'), data)
    self.assertRedirects(response, reverse('pipeline_list'))
    pipeline = Pipeline.objects.get(name='External')
    self.assertIsNone(pipeline.dlsps_instance_id)
    pipeline.dlsps_instance_id = instance_id
    pipeline.save(update_fields=['dlsps_instance_id'])
    data['dlsps_instance_id'] = '00000000-0000-0000-0000-000000000001'
    response = self.client.post(reverse('pipeline_update', args=[pipeline.pk]), data)
    self.assertRedirects(response, reverse('pipeline_list'))
    pipeline.refresh_from_db()
    self.assertEqual(pipeline.dlsps_instance_id, instance_id)
    for url in (reverse('pipeline_create'), reverse('pipeline_update', args=[pipeline.pk])):
      self.assertNotContains(self.client.get(url), 'name="dlsps_instance_id"')

  def test_form_rejects_duplicate_name(self):
    Pipeline.objects.create(name='Shared', pipeline='fakesrc ! fakesink')
    form = PipelineForm(data={'name': 'Shared', 'pipeline': 'videotestsrc ! fakesink'})
    self.assertFalse(form.is_valid())
    self.assertIn('name', form.errors)

  def test_pipeline_is_exclusive_and_delete_clears_reference(self):
    pipeline = Pipeline.objects.create(name='Shared', pipeline='fakesrc ! fakesink')
    with patch('manager.models.sendUpdateCommand'):
      first = Cam.objects.create(sensor_id='pipeline-first', name='First', pipeline=pipeline)
      with self.assertRaises(IntegrityError), transaction.atomic():
        Cam.objects.create(sensor_id='pipeline-second', name='Second', pipeline=pipeline)
      self.assertEqual(pipeline.cameras.count(), 1)
      pipeline.delete()
    first.refresh_from_db()
    self.assertIsNone(first.pipeline_id)

  def test_camera_selectors_exclude_assigned_pipelines_and_keep_current(self):
    selected = Pipeline.objects.create(name='Selected', pipeline='fakesrc ! fakesink')
    free = Pipeline.objects.create(name='Free', pipeline='fakesrc ! fakesink')
    other = Pipeline.objects.create(name='Other', pipeline='fakesrc ! fakesink')
    with patch('manager.models.sendUpdateCommand'):
      camera = Cam.objects.create(sensor_id='selected-camera', name='Selected', pipeline=selected)
      Cam.objects.create(sensor_id='other-camera', name='Other', pipeline=other)
    for form_class in (CamCreateForm, CamUpdateForm, CamCalibrateForm):
      with self.subTest(form=form_class.__name__):
        self.assertEqual(list(form_class().fields['pipeline'].queryset), [free])
        self.assertEqual(set(form_class(instance=camera).fields['pipeline'].queryset),
                         {selected, free})
        form = form_class(data={'pipeline': other.pk}, instance=camera)
        self.assertFalse(form.is_valid())
        self.assertIn('pipeline', form.errors)
    camera.pipeline = None
    with patch('manager.models.sendUpdateCommand'):
      camera.save()
    self.assertIn(selected, CamCreateForm().fields['pipeline'].queryset)

  def test_pipeline_uuid_is_displayed_read_only(self):
    instance_id = UUID('3f1c0d2e-8a4b-4d6c-9e1f-2a3b4c5d6e7f')
    Pipeline.objects.create(name='Visible', pipeline='fakesrc ! fakesink',
                            dlsps_instance_id=instance_id)
    self.assertContains(self.client.get(reverse('pipeline_list')), str(instance_id))

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
    self.assertContains(response, "<p>Associated cameras' pipeline selection will be cleared.</p>",
                        html=True)
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
    for name in ('id', 'name', 'pipeline', 'dlsps_instance_id'):
      self.assertEqual(historical._meta.get_field(name).deconstruct()[1:],
                       Pipeline._meta.get_field(name).deconstruct()[1:])
    module = import_module('manager.migrations.0006_pipeline_cam_pipeline')
    self.assertEqual(len(module.Migration.operations), 3)


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
      self.assertIsNone(pipeline.dlsps_instance_id)
      pipeline.dlsps_instance_id = UUID('3f1c0d2e-8a4b-4d6c-9e1f-2a3b4c5d6e7f')
      pipeline.save()
      pipeline.refresh_from_db()
      self.assertEqual(str(pipeline.dlsps_instance_id), '3f1c0d2e-8a4b-4d6c-9e1f-2a3b4c5d6e7f')
      camera_model.objects.filter(pk=camera_pk).update(pipeline_id=pipeline.pk)
      second = camera_model.objects.create(sensor_id='second-migration-camera', name='Second')
      with self.assertRaises(IntegrityError), transaction.atomic():
        camera_model.objects.filter(pk=second.pk).update(pipeline_id=pipeline.pk)
      executor = MigrationExecutor(connection)
      executor.migrate(old_target)
      self.assertTrue(old_apps.get_model('manager', 'Cam').objects.filter(pk=camera_pk).exists())
    finally:
      executor = MigrationExecutor(connection)
      executor.migrate(executor.loader.graph.leaf_nodes())
