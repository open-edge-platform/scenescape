#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import pytest
import tempfile
from unittest.mock import patch, MagicMock

from controller.scene_controller import SceneController


class TestSceneControllerExtractTrackerRate:
  """Unit tests for SceneController._extractTrackerRate."""

  def test_extract_tracker_rate_returns_default_when_missing(self):
    """Returns default fps when parameter is not present in config."""
    scene_controller = SceneController.__new__(SceneController)

    tracker_config = {}
    default_rate = 15

    result = scene_controller._extractTrackerRate(
      tracker_config,
      'effective_object_update_rate',
      default_rate,
    )

    assert result == default_rate

  @pytest.mark.parametrize(
    'raw_rate,expected_rate',
    [
      (30, 30),
      ('24', 24),
    ],
  )
  def test_extract_tracker_rate_returns_valid_integer_rates(self, raw_rate, expected_rate):
    """Returns parsed integer when config contains a valid rate."""
    scene_controller = SceneController.__new__(SceneController)
    tracker_config = {'effective_object_update_rate': raw_rate}

    result = scene_controller._extractTrackerRate(
      tracker_config,
      'effective_object_update_rate',
      15,
    )

    assert result == expected_rate

  def test_extract_tracker_rate_accepts_min_and_max_boundaries(self):
    """Accepts values equal to provided min/max boundaries."""
    scene_controller = SceneController.__new__(SceneController)

    min_config = {'effective_object_update_rate': 10}
    max_config = {'effective_object_update_rate': 30}

    min_result = scene_controller._extractTrackerRate(
      min_config,
      'effective_object_update_rate',
      15,
      min_rate=10,
    )
    max_result = scene_controller._extractTrackerRate(
      max_config,
      'effective_object_update_rate',
      15,
      max_rate=30,
    )

    assert min_result == 10
    assert max_result == 30

  @pytest.mark.parametrize(
    'raw_rate,min_rate,max_rate',
    [
      (0, None, None),
      ('abc', None, None),
      (5, 10, None),
      (45, None, 30),
    ],
  )
  def test_extract_tracker_rate_raises_for_invalid_values(
    self,
    raw_rate,
    min_rate,
    max_rate,
  ):
    """Raises ValueError for malformed or out-of-range rates."""
    scene_controller = SceneController.__new__(SceneController)
    tracker_config = {'effective_object_update_rate': raw_rate}

    with pytest.raises(ValueError, match='Invalid value for effective_object_update_rate'):
      scene_controller._extractTrackerRate(
        tracker_config,
        'effective_object_update_rate',
        30,
        min_rate=min_rate,
        max_rate=max_rate,
      )


class _BoolRaises:
  """Helper that raises during bool conversion to exercise exception path."""

  def __bool__(self):
    raise TypeError('cannot convert to bool')


class TestSceneControllerExtractTimeChunkingEnabled:
  """Unit tests for SceneController._extractTimeChunkingEnabled."""

  def test_extract_time_chunking_enabled_defaults_to_false_when_missing(self):
    """Sets time chunking to False when key is missing."""
    scene_controller = SceneController.__new__(SceneController)
    scene_controller.tracker_config_data = {}

    scene_controller._extractTimeChunkingEnabled({})

    assert scene_controller.tracker_config_data['time_chunking_enabled'] is False

  @pytest.mark.parametrize(
    'raw_value,expected_value',
    [
      (True, True),
      (False, False),
      (1, True),
      (0, False),
    ],
  )
  def test_extract_time_chunking_enabled_sets_boolean_value(self, raw_value, expected_value):
    """Stores bool-converted value when key is present."""
    scene_controller = SceneController.__new__(SceneController)
    scene_controller.tracker_config_data = {}

    scene_controller._extractTimeChunkingEnabled({'time_chunking_enabled': raw_value})

    assert scene_controller.tracker_config_data['time_chunking_enabled'] is expected_value

  def test_extract_time_chunking_enabled_raises_for_unboolable_value(self):
    """Raises ValueError when bool conversion fails."""
    scene_controller = SceneController.__new__(SceneController)
    scene_controller.tracker_config_data = {}

    with pytest.raises(ValueError, match='Invalid value for time_chunking_enabled'):
      scene_controller._extractTimeChunkingEnabled({'time_chunking_enabled': _BoolRaises()})


class TestSceneControllerExtractReidConfigData:
  """Regression tests: extractReidConfigData must read and store all reid config fields."""

  def test_extracts_all_known_reid_config_fields(self):
    """All reid config keys are loaded into scene_controller.reid_config_data."""
    scene_controller = SceneController.__new__(SceneController)
    scene_controller.reid_config_data = {}

    reid_config = {
      'feature_accumulation_threshold': 8,
      'similarity_threshold': 55,
      'stale_feature_timeout_secs': 7.5,
      'stale_feature_check_interval_secs': 2.0,
      'feature_slice_size': 10,
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
      json.dump(reid_config, f)
      tmp_path = f.name

    try:
      scene_controller.extractReidConfigData(tmp_path)
    finally:
      os.unlink(tmp_path)

    assert scene_controller.reid_config_data == reid_config

  def test_extract_reid_config_data_raises_for_missing_file(self):
    """Missing REID config file propagates FileNotFoundError."""
    scene_controller = SceneController.__new__(SceneController)
    scene_controller.reid_config_data = {}

    with pytest.raises(FileNotFoundError):
      scene_controller.extractReidConfigData('definitely-missing-reid-config.json')


class TestSceneDeserializeReidConfigPropagation:
  """Regression tests: Scene.deserialize must propagate reid_config_data to the tracker."""

  @patch('controller.scene.ControllerMode')
  @patch('controller.scene.IntelLabsTracking')
  def test_deserialize_without_reid_config_key_gives_empty_dict(
    self, mock_tracking, mock_mode
  ):
    """Scene.deserialize with no reid_config_data key results in empty dict on the scene."""
    mock_mode.isAnalyticsOnly.return_value = False

    mock_tracker_instance = MagicMock()
    mock_tracking.return_value = mock_tracker_instance

    from controller.scene import Scene
    scene_data = {
      'uid': 'test-uid-1',
      'name': 'test_scene',
      'map': None,
    }
    scene = Scene.deserialize(scene_data)

    assert scene.reid_config_data == {}

  @patch('controller.scene.ControllerMode')
  @patch('controller.scene.TimeChunkedIntelLabsTracking')
  def test_deserialize_with_reid_config_stores_config_on_scene(
    self, mock_tracking, mock_mode
  ):
    """Scene deserialized with reid_config_data stores it on the scene object."""
    mock_mode.isAnalyticsOnly.return_value = False
    mock_tracking.return_value = MagicMock()

    from controller.scene import Scene
    reid_config = {'feature_accumulation_threshold': 8, 'similarity_threshold': 55}
    scene_data = {
      'uid': 'test-uid-2',
      'name': 'test_scene',
      'map': None,
      'reid_config_data': reid_config,
      'tracker_config': [1.0, 2.0, 3.0, 15, True, 15, 5.0],
    }
    scene = Scene.deserialize(scene_data)

    assert scene.reid_config_data == reid_config

