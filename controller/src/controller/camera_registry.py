# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import threading

class CameraRegistry:
  """
  Process-wide, in-memory registry tracking, per scene:
    1. Which cameras are currently configured (written by Scene whenever its
       camera list changes -- additions and deletions both reflected
       immediately, no staleness).
    2. Which cameras have ever produced a valid ReID embedding (written by
       UUIDManager as detections come in; cumulative -- once a camera is
       confirmed producing embeddings, it stays confirmed even if a later
       detection from it lacks one, since that's usually a fixed
       camera/model property, not something that flickers frame to frame).

  getCameraCount() returns the INTERSECTION of the two: a camera only
  counts if it's both currently configured AND has proven it produces
  embeddings. This means:
    - Adding a camera that isn't streaming/producing embeddings yet does
      NOT bump the count.
    - Deleting a camera drops it from the count immediately, even if it
      had been producing embeddings before deletion.

  Keyed by scene_id (rather than single global sets) so multiple Scene
  instances in the same process don't get merged together.

  No network calls, no timers, no background threads -- this is pure
  in-memory state. Thread-safe via a single lock.
  """
  _instance = None
  _instance_lock = threading.Lock()

  def __init__(self):
    self._configured_cameras = {}   # scene_id -> set(camera_ids currently configured)
    self._embedding_cameras = {}    # scene_id -> set(camera_ids ever confirmed producing embeddings)
    self._lock = threading.Lock()

  @classmethod
  def getInstance(cls):
    """Return the process-wide singleton, creating it on first call."""
    with cls._instance_lock:
      if cls._instance is None:
        cls._instance = cls()
      return cls._instance

  def updateCameras(self, scene_id, camera_ids):
    """
    Replace the full set of configured camera IDs for the given scene.
    Called by Scene.updateCameras() whenever cameras are added or removed,
    so this always reflects the current truth -- no staleness, no polling.

    @param  scene_id    Identifier for the scene (e.g. Scene.name)
    @param  camera_ids  Iterable of current camera IDs for that scene
    """
    if scene_id is None:
      return
    with self._lock:
      self._configured_cameras[scene_id] = set(camera_ids)

  def recordEmbeddingObserved(self, scene_id, camera_id):
    """
    Mark a camera as confirmed producing a valid ReID embedding for this
    scene. Cumulative within this registry's lifetime -- never removed
    here directly; only excluded from getCameraCount() if the camera is
    later removed from the configured set.

    @param  scene_id   Identifier for the scene (e.g. Scene.name)
    @param  camera_id  The camera that produced a valid embedding
    """
    if scene_id is None or camera_id is None:
      return
    with self._lock:
      self._embedding_cameras.setdefault(scene_id, set()).add(camera_id)

  def getCameraCount(self, scene_id):
    """
    Return the count of cameras that are BOTH currently configured AND
    have ever produced a valid embedding, for the given scene.

    @param   scene_id  Identifier for the scene (e.g. Scene.name), or None
                       if the caller hasn't been assigned one yet
    @return  int       Count of qualifying cameras, or 0 if unknown/not
                       yet registered
    """
    if scene_id is None:
      return 0
    with self._lock:
      configured = self._configured_cameras.get(scene_id, set())
      with_embeddings = self._embedding_cameras.get(scene_id, set())
      return len(configured & with_embeddings)

  def removeScene(self, scene_id):
    """
    Remove a scene entirely from the registry (e.g. on scene deletion).

    @param  scene_id  Identifier for the scene to remove
    """
    with self._lock:
      self._configured_cameras.pop(scene_id, None)
      self._embedding_cameras.pop(scene_id, None)
