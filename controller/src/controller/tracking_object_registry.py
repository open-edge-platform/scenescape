# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import threading

class TrackedObjectRegistry:
  """
  Process-wide, in-memory registry tracking, per scene, the current count of
  active tracked objects/persons for each tracked category (e.g. "person",
  "car"). Exists because each category runs as its own tracker/UUIDManager
  instance with no visibility into any other category's tracked-object
  count -- this registry is the one place a scene-wide total across all
  categories can actually be derived.

  Written by UUIDManager.pruneInactiveTracks() once per tracking cycle, per
  category -- always reflects the current truth for that category, no
  staleness. getTotalCount() sums whatever each category last reported,
  so a category that goes quiet (0 active tracks, or the tracker itself
  shuts down and calls removeCategory()) stops contributing immediately
  rather than lingering in the total.

  Keyed by scene_id (like CameraRegistry) so multiple Scene instances in
  the same process don't get merged together.

  No network calls, no timers, no background threads -- this is pure
  in-memory state. Thread-safe via a single lock.
  """
  _instance = None
  _instance_lock = threading.Lock()

  def __init__(self):
    self._category_counts = {}   # scene_id -> {category: count}
    self._lock = threading.Lock()

  @classmethod
  def getInstance(cls):
    """Return the process-wide singleton, creating it on first call."""
    with cls._instance_lock:
      if cls._instance is None:
        cls._instance = cls()
      return cls._instance

  def updateCategoryCount(self, scene_id, category, count):
    """
    Replace the current tracked-object count for one category within a
    scene. Called once per tracking cycle by the category's own
    UUIDManager.pruneInactiveTracks() -- always the latest truth for that
    category, no staleness.

    @param  scene_id  Identifier for the scene (e.g. Scene.name)
    @param  category  The tracked object category (e.g. "person", "car")
    @param  count     Current count of active tracked objects for this
                      category (0 is a valid, meaningful value -- it is
                      stored, not treated as "no data")
    """
    if scene_id is None or category is None:
      return
    with self._lock:
      self._category_counts.setdefault(scene_id, {})[category] = count

  def getTotalCount(self, scene_id):
    """
    Return the sum of the most recently reported tracked-object count
    across every category for the given scene.

    @param   scene_id  Identifier for the scene (e.g. Scene.name), or None
                       if the caller hasn't been assigned one yet
    @return  int       Total tracked-object count across all categories,
                       or 0 if unknown/not yet registered
    """
    if scene_id is None:
      return 0
    with self._lock:
      return sum(self._category_counts.get(scene_id, {}).values())

  def removeCategory(self, scene_id, category):
    """
    Remove a single category's contribution to the total (e.g. that
    category's tracker thread has shut down), so it stops being counted
    immediately rather than lingering at its last-reported value forever.

    @param  scene_id  Identifier for the scene (e.g. Scene.name)
    @param  category  The tracked object category to remove
    """
    with self._lock:
      if scene_id in self._category_counts:
        self._category_counts[scene_id].pop(category, None)

  def removeScene(self, scene_id):
    """
    Remove a scene entirely from the registry (e.g. on scene deletion).

    @param  scene_id  Identifier for the scene to remove
    """
    with self._lock:
      self._category_counts.pop(scene_id, None)
