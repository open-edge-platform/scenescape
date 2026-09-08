# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import tempfile
from unittest.mock import mock_open, patch

from django.forms import ValidationError
from django.test import TestCase

from manager.forms import CamCalibrateForm


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


class CamCalibrateCamerachainValidationTestCase(TestCase):
  """Unit tests for CamCalibrateForm.clean_camerachain model-config validation (#1162)."""

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
    form = CamCalibrateForm()
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

  def test_clean_camerachain_rejects_symlink_escape(self):
    """Symlinks that resolve outside MODEL_CONFIGS_FOLDER are rejected."""
    outside_dir = tempfile.TemporaryDirectory()
    self.addCleanup(outside_dir.cleanup)
    outside_config = os.path.join(outside_dir.name, 'outside.json')
    with open(outside_config, 'w', encoding='utf-8') as config_file:
      json.dump(SAMPLE_MODEL_CONFIG, config_file)

    link_name = 'escape_config.json'
    link_path = os.path.join(self._tmpdir.name, link_name)
    os.symlink(outside_config, link_path)

    with self.assertRaises(ValidationError) as ctx:
      self._clean_camerachain('retail', modelconfig=link_name)
    message = str(ctx.exception)
    self.assertIn('Invalid model config path', message)
    self.assertNotIn(outside_dir.name, message)

  def test_clean_camerachain_oserror_omits_filesystem_paths(self):
    """OSError while reading model-config must not surface filesystem paths."""
    with patch('manager.ppl_generator.config_generator.open',
               mock_open()) as mocked_open:
      mocked_open.side_effect = PermissionError(
        13, 'Permission denied', self.config_path)
      with self.assertRaises(ValidationError) as ctx:
        self._clean_camerachain('retail')
    message = str(ctx.exception)
    self.assertIn('Unable to read model config file', message)
    self.assertNotIn(self._tmpdir.name, message)
    self.assertNotIn(self.config_path, message)

  def _write_config(self, content):
    with open(self.config_path, 'w', encoding='utf-8') as config_file:
      json.dump(content, config_file)

  def test_clean_camerachain_handles_non_object_config(self):
    """Valid JSON that is not a model-config object yields a safe error, not a crash."""
    for content in (42, "retail", ["retail"], None):
      self._write_config(content)
      with self.assertRaises(ValidationError) as ctx:
        self._clean_camerachain('retail')
      self.assertIn(
        'must contain a JSON object', str(ctx.exception))

  def test_clean_camerachain_handles_non_object_model_entry(self):
    """A model entry that is not an object yields a safe error, not a crash."""
    self._write_config({'retail': 42})
    with self.assertRaises(ValidationError) as ctx:
      self._clean_camerachain('retail')
    self.assertIn(
      "entry for 'retail' must be a JSON object", str(ctx.exception))
