# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import tempfile
from unittest.mock import mock_open, patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.exceptions import ValidationError as DRFValidationError

from manager.forms import CamCalibrateForm
from manager.models import Cam, Scene
from manager.serializers import CamSerializer
from manager.validators import validate_camerachain


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


class CamerachainValidationMixin:
  """Shared MODEL_CONFIGS_FOLDER fixture for form/serializer/helper tests."""

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

  def _write_config(self, content):
    with open(self.config_path, 'w', encoding='utf-8') as config_file:
      json.dump(content, config_file)


class ValidateCamerachainHelperTestCase(CamerachainValidationMixin, TestCase):
  """Unit tests for shared validate_camerachain helper (#1162)."""

  def test_accepts_known_model(self):
    self.assertEqual(validate_camerachain('retail'), 'retail')

  def test_accepts_empty_and_none(self):
    self.assertEqual(validate_camerachain(''), '')
    self.assertEqual(validate_camerachain('   '), '')
    self.assertEqual(validate_camerachain(None), '')

  def test_rejects_unknown_model(self):
    with self.assertRaises(ValidationError) as ctx:
      validate_camerachain('pv2000')
    self.assertIn('pv2000', str(ctx.exception))
    self.assertIn('not found', str(ctx.exception).lower())

  def test_rejects_unknown_model_in_chain(self):
    with self.assertRaises(ValidationError) as ctx:
      validate_camerachain('retail+pv2000')
    self.assertIn('pv2000', str(ctx.exception))

  def test_rejects_missing_config_file(self):
    with self.assertRaises(ValidationError) as ctx:
      validate_camerachain('retail', modelconfig_filename='missing_config.json')
    self.assertIn('does not exist', str(ctx.exception))

  def test_ignores_path_components_in_modelconfig(self):
    self.assertEqual(
      validate_camerachain('retail', modelconfig_filename='../../model_config.json'),
      'retail',
    )

  def test_rejects_symlink_escape(self):
    outside_dir = tempfile.TemporaryDirectory()
    self.addCleanup(outside_dir.cleanup)
    outside_config = os.path.join(outside_dir.name, 'outside.json')
    with open(outside_config, 'w', encoding='utf-8') as config_file:
      json.dump(SAMPLE_MODEL_CONFIG, config_file)

    link_name = 'escape_config.json'
    link_path = os.path.join(self._tmpdir.name, link_name)
    os.symlink(outside_config, link_path)

    with self.assertRaises(ValidationError) as ctx:
      validate_camerachain('retail', modelconfig_filename=link_name)
    message = str(ctx.exception)
    self.assertIn('Invalid model config path', message)
    self.assertNotIn(outside_dir.name, message)

  def test_oserror_omits_filesystem_paths(self):
    with patch('manager.ppl_generator.config_generator.open',
               mock_open()) as mocked_open:
      mocked_open.side_effect = PermissionError(
        13, 'Permission denied', self.config_path)
      with self.assertRaises(ValidationError) as ctx:
        validate_camerachain('retail')
    message = str(ctx.exception)
    self.assertIn('Unable to read model config file', message)
    self.assertNotIn(self._tmpdir.name, message)
    self.assertNotIn(self.config_path, message)

  def test_handles_non_object_config(self):
    for content in (42, "retail", ["retail"], None):
      self._write_config(content)
      with self.assertRaises(ValidationError) as ctx:
        validate_camerachain('retail')
      self.assertIn('must contain a JSON object', str(ctx.exception))

  def test_handles_non_object_model_entry(self):
    self._write_config({'retail': 42})
    with self.assertRaises(ValidationError) as ctx:
      validate_camerachain('retail')
    self.assertIn(
      "entry for 'retail' must be a JSON object", str(ctx.exception))


class CamCalibrateCamerachainValidationTestCase(CamerachainValidationMixin, TestCase):
  """Form wiring for clean_camerachain."""

  def _clean_camerachain(self, camerachain, modelconfig=None):
    form = CamCalibrateForm()
    if modelconfig is not None:
      form.instance.modelconfig = modelconfig
    form.cleaned_data = {'camerachain': camerachain}
    return form.clean_camerachain()

  def test_form_accepts_none_camerachain(self):
    """Nullable field values must not raise AttributeError on .strip()."""
    self.assertEqual(self._clean_camerachain(None), '')

  def test_form_rejects_unknown_model(self):
    with self.assertRaises(ValidationError) as ctx:
      self._clean_camerachain('pv2000')
    self.assertIn('pv2000', str(ctx.exception))


class CamSerializerCamerachainValidationTestCase(CamerachainValidationMixin, TestCase):
  """REST CamSerializer.validate_camerachain (#1162 API path)."""

  def setUp(self):
    super().setUp()
    self.scene = Scene.objects.create(name="test_scene", map="test_map")
    self.cam = Cam.objects.create(
      sensor_id="cam-1", name="test_camera", scene=self.scene)

  def test_serializer_accepts_known_model(self):
    serializer = CamSerializer(
      instance=self.cam,
      data={'name': self.cam.name, 'camerachain': 'retail'},
      partial=True)
    self.assertTrue(serializer.is_valid(), serializer.errors)
    self.assertEqual(serializer.validated_data['camerachain'], 'retail')

  def test_serializer_accepts_null_camerachain(self):
    serializer = CamSerializer(
      instance=self.cam,
      data={'name': self.cam.name, 'camerachain': None},
      partial=True)
    self.assertTrue(serializer.is_valid(), serializer.errors)
    self.assertEqual(serializer.validated_data.get('camerachain'), '')

  def test_serializer_rejects_unknown_model(self):
    serializer = CamSerializer(
      instance=self.cam,
      data={'name': self.cam.name, 'camerachain': 'pv2000'},
      partial=True)
    self.assertFalse(serializer.is_valid())
    self.assertIn('camerachain', serializer.errors)
    self.assertIn('pv2000', str(serializer.errors['camerachain']))

  def test_serializer_uses_request_modelconfig(self):
    serializer = CamSerializer(
      instance=self.cam,
      data={
        'name': self.cam.name,
        'camerachain': 'retail',
        'modelconfig': 'missing_config.json',
      },
      partial=True)
    self.assertFalse(serializer.is_valid())
    self.assertIn('camerachain', serializer.errors)
    self.assertIn('does not exist', str(serializer.errors['camerachain']))

  def test_serializer_validate_camerachain_raises_drf_error(self):
    serializer = CamSerializer(instance=self.cam)
    with self.assertRaises(DRFValidationError):
      serializer.validate_camerachain('pv2000')
