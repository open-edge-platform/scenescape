# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Scene registration start, queueing, and finish must not interleave."""

import threading
from types import SimpleNamespace

from auto_camera_calibration_context import CameraCalibrationContext

_WAIT = 5


class _BlockingPendingSet(set):
  """Pause the first insertion so a concurrent request can race it."""

  def __init__(self):
    super().__init__()
    self.adding = threading.Event()
    self.proceed = threading.Event()

  def add(self, item):
    """Signal the insertion, then wait before storing the item."""
    if not self.adding.is_set():
      self.adding.set()
      self.proceed.wait(_WAIT)
    super().add(item)


def _context():
  context = object.__new__(CameraCalibrationContext)
  context.register_thread_lock = threading.Lock()
  context.registration_state_lock = threading.RLock()
  context.current_processing_scene = None
  context.pending_registrations = _BlockingPendingSet()
  context.registration_results = {}
  context.process_scene = lambda scene, map_update: None
  return context


def test_late_queue_cannot_overwrite_a_started_worker():
  """Tab 1 queues B while A runs; tab 2 starts B once A finishes. B must not stay pending."""
  context = _context()
  scene_a, scene_b = SimpleNamespace(id="A"), SimpleNamespace(id="B")
  assert context.scene_update_thread_wrapper(scene_a, map_update=True)

  outcomes = {}
  first = threading.Thread(
    target=lambda: outcomes.setdefault("first", context.request_scene_registration(scene_b)))
  first.start()
  assert context.pending_registrations.adding.wait(_WAIT)

  second = threading.Thread(target=lambda: (
    context.finish_registration("A", {"status": "success"}),
    outcomes.setdefault("second", context.request_scene_registration(scene_b))))
  second.start()
  second.join(0.5)
  assert second.is_alive(), "A finished and B started while B was being queued"

  context.pending_registrations.proceed.set()
  first.join(_WAIT)
  second.join(_WAIT)
  assert outcomes == {"first": "busy", "second": "started"}
  assert "B" not in context.pending_registrations
  assert context.current_processing_scene == "B"
