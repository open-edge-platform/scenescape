# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Opt-in track annotation uses the existing DLSPS parameter mapping."""

from unittest.mock import MagicMock

import pytest

from manager.ppl_generator import config_generator


@pytest.mark.parametrize('enabled', [None, False, True])
def test_track_annotation_parameter(monkeypatch, enabled):
  generator = MagicMock()
  generator.generate.return_value = 'sscape_post_inference_data_publish name=datapublisher'
  generator.get_metadata_policy.return_value = 'detectionPolicy'
  monkeypatch.setattr(config_generator, 'create_pipeline_generator_from_dict',
                      lambda _settings: generator)
  settings = {'name': 'Camera', 'sensor_id': 'cam-1'}
  if enabled is not None:
    settings['annotate_track_ids'] = enabled
  config = config_generator.PipelineConfigGenerator(settings).get_config_as_dict()
  pipeline = config['config']['pipelines'][0]
  assert pipeline['parameters']['properties']['annotate_track_ids']['element'] == {
    'name': 'datapublisher', 'property': 'annotate-track-ids'}
  payload = pipeline['payload']['parameters']
  if enabled:
    assert payload['annotate_track_ids'] is True
  else:
    assert 'annotate_track_ids' not in payload
