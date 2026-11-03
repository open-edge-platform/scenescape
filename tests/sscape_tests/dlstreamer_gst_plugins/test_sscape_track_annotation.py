# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Host-side coverage for track parsing, selection and labels."""

import json
from threading import Event, Thread

import numpy as np
import pytest

from sscape_track_annotation import TrackSync, draw_track_labels, parse_track_message

TIMESTAMP = '2026-11-02T12:00:00.000Z'
GID = '12345678-abcd-1234-abcd-123456789012'
BOX = {'x': 10, 'y': 50, 'width': 60, 'height': 80}


def track_payload(objects):
  return json.dumps({'timestamp': TIMESTAMP, 'objects': objects}).encode()


def test_camera_filtering_and_duplicates():
  obj = {'id': GID, 'camera_bounds': {'cam-1': BOX}}
  snapshot = parse_track_message(track_payload([obj, obj]), 'cam-1')
  assert snapshot[1] == [(GID, (10, 50, 60, 80))]
  assert parse_track_message(track_payload([obj]), 'cam-2')[1] == []


@pytest.mark.parametrize('payload', [b'no json', b'[]', b'{}', b' ' * (4 * 1024 * 1024 + 1),
                                    b'{"timestamp": null, "objects": []}'],
                         ids=['invalid-json', 'array', 'missing-fields', 'oversize', 'null-time'])
def test_malformed_payload(payload):
  assert parse_track_message(payload, 'cam-1') is None


@pytest.mark.parametrize('value', [float('nan'), float('inf'), True, '10', None])
def test_invalid_box(value):
  obj = {'id': GID, 'camera_bounds': {'cam-1': dict(BOX, x=value)}}
  assert parse_track_message(track_payload([obj]), 'cam-1')[1] == []


@pytest.mark.parametrize('offset, expected', [(0, [GID]), (-0.5, [GID]), (0.5, [GID]),
                                             (-2, []), (2, [])])
def test_timeout_selects_only_nearby_snapshot(offset, expected):
  sync = TrackSync()
  timestamp, entries = parse_track_message(
    track_payload([{'id': GID, 'camera_bounds': {'cam-1': BOX}}]), 'cam-1')
  sync.update((timestamp + offset, entries))
  sync.submit(None, {'timestamp': TIMESTAMP}, 0)
  _, _, selected = sync.take(1000)
  assert [entry[0] for entry in selected] == expected


def test_empty_snapshot_clears_and_older_snapshot_is_ignored():
  sync = TrackSync()
  sync.update((10, [(GID, BOX)]))
  sync.update((11, []))
  sync.update((9, [(GID, BOX)]))
  assert sync.snapshot == (11, [])


def test_requests_coalesce_and_stop_discards_pending():
  sync = TrackSync()
  sync.submit(None, {'timestamp': TIMESTAMP, 'id': 'first'}, 0)
  sync.submit(None, {'timestamp': TIMESTAMP, 'id': 'second'}, 1000)
  assert sync.take(1000)[1]['id'] == 'first'
  sync.stop()
  assert sync.take(1000) is None


def test_arriving_snapshot_wakes_pending_image():
  sync = TrackSync()
  snapshot = parse_track_message(track_payload([]), 'cam-1')
  sync.submit(None, {'timestamp': TIMESTAMP}, 2000)
  completed = Event()
  results = []

  def receive():
    results.append(sync.take(1000))
    completed.set()

  worker = Thread(target=receive)
  worker.start()
  try:
    sync.update(snapshot)
    assert completed.wait(1), 'Track arrival did not wake the worker'
    assert results[0][2] == []
  finally:
    sync.stop()
    worker.join(1)


def test_timeout_without_followup_messages():
  sync = TrackSync()
  sync.submit(None, {'timestamp': TIMESTAMP}, 10)
  assert sync.take(1000)[2] == []


def test_label_drawing_skips_offscreen_boxes():
  image = np.zeros((240, 320, 3), dtype=np.uint8)
  assert draw_track_labels(image, [(GID, (10, 50, 60, 80)),
                                   ('outside', (400, 0, 20, 20))]) == [GID]
  assert np.any(image[:50])
