#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for CameraRegistry.
Tests the interface and behavior of the process-wide camera registry: the
configured/embedding-confirmed intersection semantics, cumulative embedding
tracking, and per-scene isolation.
These tests run inside the controller container where all dependencies
are available.
"""

import pytest

from controller.camera_registry import CameraRegistry


@pytest.fixture
def registry():
  """Fresh, non-singleton instance so state tests don't share process-wide state."""
  return CameraRegistry()


class TestGetCameraCount:
  """Test the core intersection semantics: configured AND embedding-confirmed."""

  def test_unknown_scene_returns_zero(self, registry):
    """Verify a scene that was never registered reports 0, not an error."""
    assert registry.getCameraCount("scene_1") == 0

  def test_none_scene_returns_zero(self, registry):
    """Verify a None scene_id (not yet assigned) reports 0."""
    assert registry.getCameraCount(None) == 0

  def test_configured_but_no_embedding_does_not_count(self, registry):
    """Verify a camera that's configured but hasn't produced an embedding yet is excluded."""
    registry.updateCameras("scene_1", ["cam1", "cam2"])

    assert registry.getCameraCount("scene_1") == 0

  def test_embedding_but_not_configured_does_not_count(self, registry):
    """Verify a camera producing embeddings but never configured for this scene is excluded."""
    registry.recordEmbeddingObserved("scene_1", "cam1")

    assert registry.getCameraCount("scene_1") == 0

  def test_configured_and_embedding_counts(self, registry):
    """Verify a camera that is both configured and embedding-confirmed is counted."""
    registry.updateCameras("scene_1", ["cam1"])
    registry.recordEmbeddingObserved("scene_1", "cam1")

    assert registry.getCameraCount("scene_1") == 1

  def test_only_intersection_counted_among_multiple_cameras(self, registry):
    """Verify only cameras present in both sets count, not the union."""
    registry.updateCameras("scene_1", ["cam1", "cam2", "cam3"])
    registry.recordEmbeddingObserved("scene_1", "cam1")
    registry.recordEmbeddingObserved("scene_1", "cam2")
    # cam3 configured but never produced an embedding; cam4 produced one but isn't configured
    registry.recordEmbeddingObserved("scene_1", "cam4")

    assert registry.getCameraCount("scene_1") == 2


class TestUpdateCameras:
  """Test that updateCameras always reflects the current configured set, no staleness."""

  def test_replaces_full_set_not_additive(self, registry):
    """Verify a second call replaces the configured set rather than merging with it."""
    registry.updateCameras("scene_1", ["cam1", "cam2"])
    registry.recordEmbeddingObserved("scene_1", "cam1")
    registry.recordEmbeddingObserved("scene_1", "cam2")
    assert registry.getCameraCount("scene_1") == 2

    registry.updateCameras("scene_1", ["cam1"])  # cam2 removed

    assert registry.getCameraCount("scene_1") == 1

  def test_deleting_a_camera_drops_it_immediately_even_if_it_had_embeddings(self, registry):
    """Verify removing a camera from the configured set excludes it right away,
    even though its embedding-confirmed status is never cleared."""
    registry.updateCameras("scene_1", ["cam1", "cam2"])
    registry.recordEmbeddingObserved("scene_1", "cam1")
    registry.recordEmbeddingObserved("scene_1", "cam2")

    registry.updateCameras("scene_1", ["cam1"])

    assert registry.getCameraCount("scene_1") == 1

  def test_re_adding_a_previously_embedding_confirmed_camera_counts_immediately(self, registry):
    """Verify a camera re-added to the configured set counts right away, since its
    embedding confirmation is cumulative and was never lost."""
    registry.updateCameras("scene_1", ["cam1"])
    registry.recordEmbeddingObserved("scene_1", "cam1")
    registry.updateCameras("scene_1", [])  # cam1 temporarily removed
    assert registry.getCameraCount("scene_1") == 0

    registry.updateCameras("scene_1", ["cam1"])  # cam1 re-added, no new embedding needed

    assert registry.getCameraCount("scene_1") == 1

  def test_adding_a_camera_not_yet_producing_embeddings_does_not_bump_count(self, registry):
    """Verify newly configuring a camera has no effect on the count until it actually
    produces a valid embedding."""
    registry.updateCameras("scene_1", ["cam1"])
    registry.recordEmbeddingObserved("scene_1", "cam1")
    assert registry.getCameraCount("scene_1") == 1

    registry.updateCameras("scene_1", ["cam1", "cam2"])

    assert registry.getCameraCount("scene_1") == 1

  def test_none_scene_id_is_noop(self, registry):
    """Verify updateCameras with scene_id=None is silently ignored."""
    registry.updateCameras(None, ["cam1"])

    assert registry.getCameraCount(None) == 0


class TestRecordEmbeddingObserved:
  """Test the cumulative, never-reset nature of embedding confirmation."""

  def test_embedding_confirmation_is_cumulative_across_calls(self, registry):
    """Verify recording an embedding once is enough; it isn't tied to a specific frame."""
    registry.updateCameras("scene_1", ["cam1"])

    registry.recordEmbeddingObserved("scene_1", "cam1")
    registry.recordEmbeddingObserved("scene_1", "cam1")  # duplicate observation

    assert registry.getCameraCount("scene_1") == 1

  def test_none_scene_id_is_noop(self, registry):
    """Verify recordEmbeddingObserved with scene_id=None is silently ignored."""
    registry.recordEmbeddingObserved(None, "cam1")

    assert registry.getCameraCount(None) == 0

  def test_none_camera_id_is_noop(self, registry):
    """Verify recordEmbeddingObserved with camera_id=None is silently ignored."""
    registry.updateCameras("scene_1", ["cam1"])

    registry.recordEmbeddingObserved("scene_1", None)

    assert registry.getCameraCount("scene_1") == 0


class TestSceneIsolation:
  """Test that multiple scenes in the same process never merge together."""

  def test_configured_cameras_are_isolated_per_scene(self, registry):
    """Verify one scene's configured cameras don't count toward another scene."""
    registry.updateCameras("scene_1", ["cam1"])
    registry.recordEmbeddingObserved("scene_1", "cam1")
    registry.recordEmbeddingObserved("scene_2", "cam1")  # same camera_id, different scene

    assert registry.getCameraCount("scene_1") == 1
    assert registry.getCameraCount("scene_2") == 0  # cam1 never configured for scene_2

  def test_embedding_confirmation_is_isolated_per_scene(self, registry):
    """Verify embedding confirmation in one scene doesn't leak into another scene
    that happens to configure a camera with the same ID."""
    registry.updateCameras("scene_1", ["cam1"])
    registry.updateCameras("scene_2", ["cam1"])
    registry.recordEmbeddingObserved("scene_1", "cam1")

    assert registry.getCameraCount("scene_1") == 1
    assert registry.getCameraCount("scene_2") == 0


class TestRemoveScene:
  """Test removing an entire scene from the registry."""

  def test_remove_scene_clears_count(self, registry):
    """Verify removing a scene drops both its configured and embedding-confirmed state."""
    registry.updateCameras("scene_1", ["cam1"])
    registry.recordEmbeddingObserved("scene_1", "cam1")
    assert registry.getCameraCount("scene_1") == 1

    registry.removeScene("scene_1")

    assert registry.getCameraCount("scene_1") == 0

  def test_remove_scene_does_not_affect_other_scenes(self, registry):
    """Verify removing one scene leaves other scenes' state untouched."""
    registry.updateCameras("scene_1", ["cam1"])
    registry.recordEmbeddingObserved("scene_1", "cam1")
    registry.updateCameras("scene_2", ["cam1"])
    registry.recordEmbeddingObserved("scene_2", "cam1")

    registry.removeScene("scene_1")

    assert registry.getCameraCount("scene_2") == 1

  def test_remove_unknown_scene_does_not_raise(self, registry):
    """Verify removing a scene that was never registered is a safe no-op."""
    registry.removeScene("never_seen_scene")  # should not raise

  def test_re_adding_camera_after_scene_removal_requires_new_embedding_confirmation(self, registry):
    """Verify removeScene truly clears cumulative embedding state, unlike updateCameras
    (which only clears the configured set, not the embedding-confirmed set)."""
    registry.updateCameras("scene_1", ["cam1"])
    registry.recordEmbeddingObserved("scene_1", "cam1")
    registry.removeScene("scene_1")

    registry.updateCameras("scene_1", ["cam1"])  # re-configure after full removal

    assert registry.getCameraCount("scene_1") == 0, \
      "Embedding confirmation should not survive a full scene removal"


class TestSingleton:
  """Test getInstance(), isolated from the direct-instantiation state tests above."""

  def setup_method(self):
    CameraRegistry._instance = None

  def teardown_method(self):
    CameraRegistry._instance = None

  def test_get_instance_returns_same_object(self):
    """Verify repeated calls return the same process-wide instance."""
    a = CameraRegistry.getInstance()
    b = CameraRegistry.getInstance()

    assert a is b

  def test_get_instance_creates_on_first_call(self):
    """Verify the singleton is lazily created on first access, not at import time."""
    assert CameraRegistry._instance is None

    instance = CameraRegistry.getInstance()

    assert instance is not None
    assert CameraRegistry._instance is instance
