#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

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
