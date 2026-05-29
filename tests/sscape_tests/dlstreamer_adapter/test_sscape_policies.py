# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path

import pytest

from sscape_policies import (
  _isDetection,
  detectionPolicy,
  detection3DPolicy,
  reidPolicy,
  classificationPolicy,
  ocrPolicy,
)

DATA_DIR = Path(__file__).resolve().parent / 'data'

@pytest.fixture
def valid_detection_item():
  return {
    'detection': {
      'confidence': 0.99,
      'label': 'person',
      'label_id': 1,
    },
    'x': 100, 'y': 50, 'w': 200, 'h': 400,
    'tensors': [],
  }

@pytest.fixture
def non_detection_item():
  """Item without detection key, as introduced by DLS metadata changes."""
  return {
    'classification': {
      'confidence': 0.0,
      'label': 'Female Male',
    },
    'h': 720, 'w': 1280, 'x': 0, 'y': 0,
    'tensors': [
      {
        'confidence': 0.0,
        'label': 'Female Male',
        'name': 'classification',
      }
    ],
  }

class TestIsDetection:

  def test_valid_detection(self, valid_detection_item):
    assert _isDetection(valid_detection_item) is True

  def test_missing_detection_key(self, non_detection_item):
    assert _isDetection(non_detection_item) is False

  def test_detection_missing_confidence(self):
    item = {'detection': {'label': 'person'}}
    assert _isDetection(item) is False

  def test_detection_not_a_dict(self):
    item = {'detection': 'not_a_dict'}
    assert _isDetection(item) is False

  def test_empty_item(self):
    assert _isDetection({}) is False

class TestDetectionPolicyGuard:

  def test_valid_item_populates_pobj(self, valid_detection_item):
    pobj = {}
    detectionPolicy(pobj, valid_detection_item, 1280, 720)
    assert 'category' in pobj
    assert pobj['category'] == 'person'
    assert pobj['confidence'] == 0.99

  def test_non_detection_leaves_pobj_empty(self, non_detection_item):
    pobj = {}
    detectionPolicy(pobj, non_detection_item, 1280, 720)
    assert pobj == {}

class TestDetection3DPolicyGuard:

  def test_non_detection_leaves_pobj_empty(self, non_detection_item):
    pobj = {}
    detection3DPolicy(pobj, non_detection_item, 1280, 720)
    assert pobj == {}

class TestClassificationPolicyGuard:

  def test_non_detection_leaves_pobj_empty(self, non_detection_item):
    pobj = {}
    classificationPolicy(pobj, non_detection_item, 1280, 720)
    assert pobj == {}

class TestReidPolicyGuard:

  def test_non_detection_leaves_pobj_empty(self, non_detection_item):
    pobj = {}
    reidPolicy(pobj, non_detection_item, 1280, 720)
    assert pobj == {}

class TestOcrPolicyGuard:

  def test_non_detection_leaves_pobj_empty(self, non_detection_item):
    pobj = {}
    ocrPolicy(pobj, non_detection_item, 1280, 720)
    assert pobj == {}

class TestWithRealMetadata:
  """Verify policies against real DLS metadata samples."""

  @pytest.fixture(scope='function')
  def detections_metadata(self):
    path = DATA_DIR / 'dls_metadata_detections.json'
    return json.loads(path.read_text())

  @pytest.fixture(scope='function')
  def mixed_metadata(self):
    path = DATA_DIR / 'dls_metadata_mixed.json'
    return json.loads(path.read_text())

  def test_detections_metadata_parses_detection(self, detections_metadata):
    item = detections_metadata['objects'][0]
    pobj = {}
    reidPolicy(pobj, item, 1280, 720)
    assert pobj['category'] == 'person'

  def test_mixed_metadata_skips_non_detection(self, mixed_metadata):
    non_det = mixed_metadata['objects'][1]
    pobj = {}
    reidPolicy(pobj, non_det, 1280, 720)
    assert pobj == {}

  def test_mixed_metadata_parses_valid_detection(self, mixed_metadata):
    det = mixed_metadata['objects'][0]
    pobj = {}
    reidPolicy(pobj, det, 1280, 720)
    assert pobj['category'] == 'person'
    assert 'metadata' in pobj
