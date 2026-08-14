# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import tempfile

from django.contrib.auth.models import User
from django.forms import ValidationError
from django.test import TestCase
from django.test.client import RequestFactory
from django.urls import reverse

from manager.forms import CamCreateForm
from manager.models import Cam, Scene


SAMPLE_MODEL_CONFIG = {
  "retail": {
    "type": "detect",
    "params": {
      "model": "intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml",
      "model_proc": "object_detection/person/person-detection-retail-0013.json"
    },
    "adapter-params": {
      "metadatagenpolicy": "detectionPolicy"
    }
  }
}


class CamCreateTestCase(TestCase):

  def setUp(self):
    self.factory = RequestFactory()
    request = self.factory.get('/')
    self.user = User.objects.create_superuser('test_user', 'test_user@intel.com', 'testpassword')
    self.client.post(reverse('sign_in'), data={
      'username': 'test_user',
      'password': 'testpassword',
      'request': request
    })
    self.scene = Scene.objects.create(name="test_scene", map="test_map")

  def test_cam_create_invalid_scene_returns_400(self):
    """Invalid form submissions from CamCreateView return HTTP 400."""
    response = self.client.post(reverse('cam_create'), data={
      'sensor_id': '100',
      'name': 'test_camera',
      'scene': 'not-a-valid-scene-pk',
    })
    self.assertEqual(response.status_code, 400)

  def test_cam_create_with_valid_scene_succeeds(self):
    """Camera creation without camerachain succeeds when required fields are valid."""
    response = self.client.post(reverse('cam_create'), data={
      'sensor_id': 'cam-100',
      'name': 'test_camera',
      'scene': str(self.scene.pk),
    })
    self.assertEqual(response.status_code, 302)
    self.assertTrue(Cam.objects.filter(sensor_id='cam-100', name='test_camera').exists())


class CamCreateCamerachainValidationTestCase(TestCase):
  """Unit tests for CamCreateForm.clean_camerachain model-config validation (#1162)."""

  def setUp(self):
    self._tmpdir = tempfile.TemporaryDirectory()
    self.addCleanup(self._tmpdir.cleanup)
    self.config_path = os.path.join(self._tmpdir.name, 'model_config.json')
    with open(self.config_path, 'w', encoding='utf-8') as config_file:
      json.dump(SAMPLE_MODEL_CONFIG, config_file)

    self._previous_folder = os.environ.get('MODEL_CONFIGS_FOLDER')
    os.environ['MODEL_CONFIGS_FOLDER'] = self._tmpdir.name

  def tearDown(self):
    if self._previous_folder is None:
      os.environ.pop('MODEL_CONFIGS_FOLDER', None)
    else:
      os.environ['MODEL_CONFIGS_FOLDER'] = self._previous_folder

  def _clean_camerachain(self, camerachain, modelconfig=None):
    form = CamCreateForm()
    if modelconfig is not None:
      form.instance.modelconfig = modelconfig
    form.cleaned_data = {'camerachain': camerachain}
    return form.clean_camerachain()

  def test_clean_camerachain_accepts_known_model(self):
    """Valid model names present in model-config are accepted."""
    self.assertEqual(self._clean_camerachain('retail'), 'retail')

  def test_clean_camerachain_accepts_empty_value(self):
    """Empty camerachain skips model-config validation (non-K8s / unset chain)."""
    self.assertEqual(self._clean_camerachain(''), '')
    self.assertEqual(self._clean_camerachain('   '), '')

  def test_clean_camerachain_rejects_unknown_model(self):
    """Model names missing from model-config raise a validation error."""
    with self.assertRaises(ValidationError) as ctx:
      self._clean_camerachain('pv2000')
    self.assertIn('pv2000', str(ctx.exception))
    self.assertIn('not found', str(ctx.exception).lower())

  def test_clean_camerachain_rejects_unknown_model_in_chain(self):
    """Sequential chains fail when any model is missing from model-config."""
    with self.assertRaises(ValidationError) as ctx:
      self._clean_camerachain('retail+pv2000')
    self.assertIn('pv2000', str(ctx.exception))

  def test_clean_camerachain_rejects_missing_config_file(self):
    """Missing model-config file raises a validation error."""
    with self.assertRaises(ValidationError) as ctx:
      self._clean_camerachain('retail', modelconfig='missing_config.json')
    self.assertIn('does not exist', str(ctx.exception))

  def test_clean_camerachain_ignores_path_components_in_modelconfig(self):
    """modelconfig values are restricted to basename under MODEL_CONFIGS_FOLDER."""
    # Path separators must not escape the configs folder; basename resolves to
    # the local model_config.json written in setUp.
    self.assertEqual(
      self._clean_camerachain('retail', modelconfig='../../model_config.json'),
      'retail',
    )
