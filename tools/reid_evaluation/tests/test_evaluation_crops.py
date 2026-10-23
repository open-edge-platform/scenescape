# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import csv
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from tools.reid_evaluation.crops import (
    REVIEW_FIELDS, _contact_sheet, export_crops, person_boxes, reviewed_manifest,
)
from tools.reid_evaluation.evaluate import score_queries


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


def test_export_ids_namespace_cameras_and_recordings(tmp_path, monkeypatch):
  cv2, ov = MagicMock(), MagicMock()
  monkeypatch.setitem(sys.modules, 'cv2', cv2)
  monkeypatch.setitem(sys.modules, 'openvino', ov)
  compiled = ov.Core.return_value.compile_model.return_value
  compiled.inputs = [compiled.input.return_value]
  compiled.outputs = [compiled.output.return_value]
  compiled.input.return_value.shape = [1, 3, 2, 2]
  compiled.input.return_value.element_type.to_dtype.return_value = np.uint8
  compiled.create_infer_request.return_value.infer.return_value = {
    compiled.output.return_value: np.array([[0, 1, 0.9, 0, 0, 1, 1]]),
  }
  cv2.VideoCapture.return_value.get.return_value = 1.0
  cv2.VideoCapture.return_value.retrieve.return_value = (True, np.zeros((10, 10, 3)))
  cv2.resize.return_value = np.zeros((2, 2, 3))

  def save_crop(path, crop):
    Path(path).write_bytes(b'crop')
    return True

  cv2.imwrite.side_effect = save_crop
  sheets = MagicMock()
  monkeypatch.setattr('tools.reid_evaluation.crops._contact_sheet', sheets)
  detector = tmp_path / 'detector.xml'
  detector.write_bytes(b'xml')
  detector.with_suffix('.bin').write_bytes(b'bin')
  rows = []
  namespaces = []
  for index, (camera, content) in enumerate([
      ('cam1', b'recording-a'), ('cam2', b'recording-a'),
      ('cam1', b'recording-b'), ('cam1', b'recording-a')]):
    video = tmp_path / f'renamed-{index}.mp4'
    video.write_bytes(content)
    output = tmp_path / f'export-{index}'
    result = export_crops(SimpleNamespace(
      camera=camera, video=video, detector=detector, output=output, device='CPU',
      every_seconds=1.0, start_seconds=0.0, max_frames=1, confidence=0.7,
      minimum_area=0, person_label=1))
    with (output / 'review.csv').open() as stream:
      row = next(csv.DictReader(stream))
    assert row['id'] == f"{result['id_namespace']}-f0000000-p00"
    assert row['image'] == f"crops/{row['id']}.png"
    row.update(image=str(output / row['image']), identity='person-a',
               split='gallery' if index == 0 else 'test')
    rows.append(row)
    namespaces.append(result['id_namespace'])

  assert len(set(namespaces[:3])) == 3
  assert rows[0]['id'] == rows[3]['id']
  review = tmp_path / 'combined.csv'
  _write_review(review, rows[:3])
  manifest_path = tmp_path / 'manifest.json'
  reviewed_manifest(review, manifest_path)
  samples = json.loads(manifest_path.read_text())['samples']
  for sample in samples:
    sample['embedding'] = [1, 0]
  cross_camera = score_queries(samples)
  assert cross_camera[0]['correct']
  assert cross_camera[1]['skipped']
  scored = score_queries(samples, cross_camera=False)
  assert len(scored) == 2
  assert all(row['correct'] for row in scored)
  assert sheets.call_count == 4


def test_contact_sheet_uses_readable_suffix(tmp_path, monkeypatch):
  image_module = pytest.importorskip('PIL.Image')
  draw_module = pytest.importorskip('PIL.ImageDraw')
  image_module.new('RGB', (10, 20)).save(tmp_path / 'crop.png')
  draw = MagicMock()
  monkeypatch.setattr(draw_module, 'Draw', lambda image: draw)
  _contact_sheet([{
    'id': '0123456789abcdef01234567-f0000000-p00',
    'image': 'crop.png', 'timestamp_seconds': 0.0,
  }], tmp_path, 0)
  assert [call.args[1] for call in draw.text.call_args_list] == ['f0000000-p00', 't=0.00s']
  assert (tmp_path / 'contact-sheet-000.jpg').is_file()
