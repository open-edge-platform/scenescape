#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

pytest.importorskip("robot_vision")

from controller.ilabs_tracking import IntelLabsTracking  # noqa: E402


def test_metadata_attributes_round_trip():
  """Legacy adapter preserves fused metadata values and confidence."""
  metadata = {
      'plate': {'label': 'XYZ-789', 'model_name': 'lpr'},
      'gender': {'label': 'female', 'confidence': 0.9, 'model_name': 'm1'},
  }

  attributes = IntelLabsTracking.metadata_to_attributes(metadata)

  assert attributes['metadata_confidence.gender'] == '0.9'
  assert 'metadata_confidence.plate' not in attributes
  assert IntelLabsTracking.metadata_from_attributes(attributes) == metadata


def test_invalid_metadata_field_does_not_hide_valid_fields():
  """A malformed fused field is ignored without dropping other metadata."""
  attributes = {
      'metadata.plate': '{invalid',
      'metadata.gender': '{"label":"female"}',
  }

  metadata = IntelLabsTracking.metadata_from_attributes(attributes)

  assert metadata == {'gender': {'label': 'female'}}
