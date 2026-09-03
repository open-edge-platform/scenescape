#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Concurrency regression tests for Tracking curObjects / object_classes handoff."""

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import controller.tracking as tracking_mod
from controller.tracking import Tracking

TEST_NAME = "NEX-T28251"


@pytest.fixture(autouse=True)
def mock_uuid_manager():
  with patch('controller.tracking.UUIDManager') as mock_cls:
    mock_cls.return_value = MagicMock()
    yield mock_cls


class TestTrackingConcurrentHandoff:
  def test_current_objects_safe_during_curobjects_swap(self):
    """Publishers iterating currentObjects must not race tracker swaps."""
    parent = Tracking()
    child = Tracking()
    child.curObjects = [SimpleNamespace(oid='a')]
    with parent._state_lock:
      parent.trackers['person'] = child

    errors = []
    stop = threading.Event()

    def publisher():
      try:
        while not stop.is_set():
          # Bypass groupObjects (needs full MovingObject shape); exercise the
          # locked snapshot path that publish uses for a single category.
          objs = parent.currentObjects(category='person')
          assert isinstance(objs, list)
          for item in objs:
            _ = getattr(item, 'oid', None)
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    def tracker_swap():
      try:
        for i in range(2000):
          snapshot = [SimpleNamespace(oid=f'id-{i}') for _ in range(5)]
          with child._state_lock:
            child.curObjects = snapshot
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    readers = [threading.Thread(target=publisher, daemon=True) for _ in range(4)]
    for t in readers:
      t.start()
    tracker_swap()
    stop.set()
    for t in readers:
      t.join(timeout=2.0)

    assert not errors, f"curObjects handoff race: {errors}"

  def test_object_classes_update_safe_during_create(self):
    """Asset refresh must not race createObject class lookup."""
    errors = []
    tracker = Tracking()

    def updater():
      try:
        for i in range(200):
          tracker.updateObjectClasses([
            {'name': f'asset-{i % 5}', 'x_size': 1.0, 'y_size': 1.0, 'z_size': 1.0},
            {'name': 'apriltag'},
          ])
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    def reader():
      try:
        for _ in range(200):
          with tracking_mod._object_classes_lock:
            _ = list(tracking_mod.object_classes.keys())
            for name, meta in list(tracking_mod.object_classes.items()):
              assert 'class' in meta
      except Exception as exc:  # noqa: BLE001
        errors.append(exc)

    threads = [
      threading.Thread(target=updater),
      threading.Thread(target=reader),
      threading.Thread(target=updater),
      threading.Thread(target=reader),
    ]
    for t in threads:
      t.start()
    for t in threads:
      t.join()
    assert not errors, f"object_classes race: {errors}"
    # Negative: apriltag default class must still be present after refresh churn.
    with tracking_mod._object_classes_lock:
      assert 'apriltag' in tracking_mod.object_classes
