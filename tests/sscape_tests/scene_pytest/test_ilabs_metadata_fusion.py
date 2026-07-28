#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

import pytest

robot_vision = pytest.importorskip("robot_vision")

from controller import ilabs_tracking  # noqa: E402
from controller.ilabs_tracking import IntelLabsTracking  # noqa: E402
from scene_common.geometry import Point  # noqa: E402

RealTrackedObject = robot_vision.tracking.TrackedObject


def test_metadata_attributes_round_trip():
  """Legacy adapter preserves fused metadata values and confidence."""
  metadata = {
      'plate': {'label': 'XYZ-789', 'model_name': 'lpr'},
      'gender': {'label': 'female', 'confidence': 0.9, 'model_name': 'm1'},
  }

  attributes = IntelLabsTracking.metadata_to_attributes(metadata)
  decoded_metadata = IntelLabsTracking.metadata_from_attributes(attributes)

  assert attributes['metadata_confidence.gender'] == '0.9'
  assert 'metadata_confidence.plate' not in attributes
  assert decoded_metadata == metadata
  assert list(decoded_metadata) == ['gender', 'plate']


def test_invalid_metadata_field_does_not_hide_valid_fields():
  """A malformed fused field is ignored without dropping other metadata."""
  attributes = {
      'metadata.plate': '{invalid',
      'metadata.gender': '{"label":"female"}',
  }

  metadata = IntelLabsTracking.metadata_from_attributes(attributes)

  assert metadata == {'gender': {'label': 'female'}}


def test_to_rv_object_assigns_complete_attributes_dict(monkeypatch):
  """Metadata survives pybind's by-value STL property conversion."""
  monkeypatch.setattr(ilabs_tracking.rv.tracking, 'TrackedObject', RealTrackedObject)
  tracker = object.__new__(IntelLabsTracking)
  detected_object = SimpleNamespace(
      uuid=None,
      sceneLoc=Point(1.0, 2.0, 0.0),
      size=[1.0, 1.0, 2.0],
      rotation=None,
      confidence=0.8,
      info={},
      frameCount=1,
      metadata={
          'plate': {'label': 'XYZ-789'},
          'gender': {'label': 'female', 'confidence': 0.9},
      },
  )

  rv_object = tracker.to_rv_object(detected_object)
  attributes = rv_object.attributes

  assert attributes['info'] == detected_object.uuid
  assert attributes['metadata.plate'] == '{"label":"XYZ-789"}'
  assert attributes['metadata.gender'] == '{"label":"female","confidence":0.9}'
  assert attributes['metadata_confidence.gender'] == '0.9'
