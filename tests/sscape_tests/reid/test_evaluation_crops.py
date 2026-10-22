# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import csv
import json

import numpy as np
import pytest

from tools.reid_evaluation.crops import REVIEW_FIELDS, person_boxes, reviewed_manifest


def test_ssd_person_boxes_filter_clip_and_preserve_scores():
  output = np.asarray([[[
      [0, 1, 0.9, -0.1, 0.1, 0.5, 1.2],
      [0, 2, 0.9, 0, 0, 1, 1],
      [0, 1, 0.2, 0, 0, 1, 1],
      [0, 1, 0.9, 0.8, 0.8, 0.1, 0.1],
      [-1, 1, 0.9, 0, 0, 1, 1],
      [0, 1, float('nan'), 0, 0, 1, 1],
  ]]])

  boxes = person_boxes(output, 100, 200, minimum_area=100)

  assert len(boxes) == 1
  assert boxes[0] == {'x': 0, 'y': 20, 'width': 50, 'height': 180, 'confidence': 0.9}


def test_small_crops_and_unsupported_detector_outputs_are_rejected():
  assert person_boxes(np.asarray([[0, 1, 0.9, 0, 0, 0.1, 0.1]]), 100, 100) == []
  with pytest.raises(ValueError, match='seven values'):
    person_boxes(np.zeros((1, 100, 6)), 100, 100)


def _write_review(path, rows):
  with path.open('w', newline='') as stream:
    writer = csv.DictWriter(stream, fieldnames=REVIEW_FIELDS)
    writer.writeheader()
    writer.writerows(rows)


def test_review_requires_human_labels_before_creating_manifest(tmp_path):
  (tmp_path / 'person.png').write_bytes(b'image placeholder')
  row = {'id': 'crop-1', 'image': 'person.png', 'camera': 'qcam1', 'include': 'yes'}
  review = tmp_path / 'review.csv'
  _write_review(review, [row])

  with pytest.raises(ValueError, match='needs an identity'):
    reviewed_manifest(review, tmp_path / 'manifest.json')
  assert not (tmp_path / 'manifest.json').exists()


def test_reviewed_manifest_preserves_labels_and_excludes_rejected_crops(tmp_path):
  (tmp_path / 'gallery.png').write_bytes(b'gallery placeholder')
  (tmp_path / 'query.png').write_bytes(b'query placeholder')
  review = tmp_path / 'review.csv'
  _write_review(review, [
      {'id': 'gallery', 'image': 'gallery.png', 'camera': 'qcam1', 'identity': 'person-a',
       'split': 'gallery', 'include': 'yes'},
      {'id': 'query', 'image': 'query.png', 'camera': 'qcam1', 'identity': 'person-a',
          'split': 'test', 'include': 'yes'},
      {'id': 'bad-detection', 'include': 'no'},
  ])
  output = tmp_path / 'manifest.json'

  result = reviewed_manifest(review, output)

  manifest = json.loads(output.read_text())
  assert len(manifest['samples']) == 2
  assert manifest['samples'][0]['identity'] == 'person-a'
  assert result['single_camera'] is True
  assert manifest['samples'][1]['image'] == str(tmp_path / 'query.png')
  with pytest.raises(ValueError, match='already exists'):
    reviewed_manifest(review, output)


def test_duplicate_crop_ids_and_missing_images_are_rejected(tmp_path):
  (tmp_path / 'crop.png').write_bytes(b'image placeholder')
  review = tmp_path / 'review.csv'
  row = {'id': 'duplicate', 'image': 'crop.png', 'camera': 'qcam1', 'identity': 'person-a',
         'split': 'gallery', 'include': 'yes'}
  _write_review(review, [row, {**row, 'split': 'test'}])
  with pytest.raises(ValueError, match='unique'):
    reviewed_manifest(review, tmp_path / 'manifest.json')
  _write_review(review, [{**row, 'image': 'missing.png'}])
  with pytest.raises(ValueError, match='missing'):
    reviewed_manifest(review, tmp_path / 'manifest.json')


def test_malformed_review_csv_is_rejected_without_writing_manifest(tmp_path):
  review = tmp_path / 'review.csv'
  review.write_text(','.join(REVIEW_FIELDS) + '\ncrop-1,crop.png\n')
  with pytest.raises(ValueError, match='Malformed review'):
    reviewed_manifest(review, tmp_path / 'manifest.json')
  assert not (tmp_path / 'manifest.json').exists()
