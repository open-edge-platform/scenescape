#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for TrackedObjectRegistry.
Tests the interface and behavior of the process-wide tracked-object-count
registry: per-category updates, cross-category totals, and cleanup.
These tests run inside the controller container where all dependencies
are available.
"""

import pytest

from scene_common.tracking_object_registry import TrackedObjectRegistry

@pytest.fixture
def registry():
  """Fresh, non-singleton instance so state tests don't share process-wide state."""
  return TrackedObjectRegistry()


class TestUpdateAndGetTotalCount:
  """Test per-category updates and the cross-category total they produce."""

  def test_total_count_unknown_scene_is_zero(self, registry):
    """Verify an unregistered scene reports 0, not an error."""
    assert registry.getTotalCount("scene_1") == 0

  def test_total_count_none_scene_is_zero(self, registry):
    """Verify a None scene_id (not yet assigned) reports 0."""
    assert registry.getTotalCount(None) == 0

  def test_single_category_count(self, registry):
    """Verify a single category's count is reflected directly in the total."""
    registry.updateCategoryCount("scene_1", "person", 5)

    assert registry.getTotalCount("scene_1") == 5

  def test_multiple_categories_sum(self, registry):
    """Verify the total is the sum across every category reported for a scene."""
    registry.updateCategoryCount("scene_1", "person", 5)
    registry.updateCategoryCount("scene_1", "car", 2)

    assert registry.getTotalCount("scene_1") == 7

  def test_updating_same_category_overwrites_not_adds(self, registry):
    """Verify a repeated update replaces the prior count rather than accumulating."""
    registry.updateCategoryCount("scene_1", "person", 5)

    registry.updateCategoryCount("scene_1", "person", 3)

    assert registry.getTotalCount("scene_1") == 3

  def test_zero_count_is_stored_not_ignored(self, registry):
    """Verify 0 is treated as meaningful data (category currently empty), not 'no data'."""
    registry.updateCategoryCount("scene_1", "person", 5)

    registry.updateCategoryCount("scene_1", "person", 0)

    assert registry.getTotalCount("scene_1") == 0

  def test_scenes_are_isolated(self, registry):
    """Verify separate scenes' category counts never mix into each other's totals."""
    registry.updateCategoryCount("scene_1", "person", 5)
    registry.updateCategoryCount("scene_2", "person", 100)

    assert registry.getTotalCount("scene_1") == 5
    assert registry.getTotalCount("scene_2") == 100

  def test_update_with_none_scene_id_is_noop(self, registry):
    """Verify updates with scene_id=None are silently ignored, not stored under a None key."""
    registry.updateCategoryCount(None, "person", 5)

    assert registry.getTotalCount(None) == 0

  def test_update_with_none_category_is_noop(self, registry):
    """Verify updates with category=None are silently ignored."""
    registry.updateCategoryCount("scene_1", None, 5)

    assert registry.getTotalCount("scene_1") == 0


class TestRemoveCategory:
  """Test removing a single category's contribution to the total."""

  def test_remove_category_drops_its_contribution(self, registry):
    """Verify removing one category immediately excludes it from the total."""
    registry.updateCategoryCount("scene_1", "person", 5)
    registry.updateCategoryCount("scene_1", "car", 2)

    registry.removeCategory("scene_1", "car")

    assert registry.getTotalCount("scene_1") == 5

  def test_remove_unknown_category_does_not_raise(self, registry):
    """Verify removing a category that was never registered is a safe no-op."""
    registry.updateCategoryCount("scene_1", "person", 5)

    registry.removeCategory("scene_1", "car")  # never existed

    assert registry.getTotalCount("scene_1") == 5

  def test_remove_category_from_unknown_scene_does_not_raise(self, registry):
    """Verify removing from a scene that was never registered is a safe no-op."""
    registry.removeCategory("never_seen_scene", "person")  # should not raise

  def test_removing_the_last_category_forgets_the_scene(self, registry):
    """Verify a scene left with no categories does not linger in the registry."""
    registry.updateCategoryCount("scene_1", "person", 5)

    registry.removeCategory("scene_1", "person")

    assert "scene_1" not in registry._category_counts


class TestGenerations:
  """Test that a retired tracker cannot clobber the one that replaced it."""

  def test_older_generation_cannot_overwrite_a_newer_count(self, registry):
    """Verify a draining old tracker's report is dropped once the new one reported."""
    registry.updateCategoryCount("scene_1", "person", 2, generation=2)

    registry.updateCategoryCount("scene_1", "person", 9, generation=1)

    assert registry.getTotalCount("scene_1") == 2

  def test_newer_generation_replaces_an_older_count(self, registry):
    """Verify the replacement tracker takes over the entry."""
    registry.updateCategoryCount("scene_1", "person", 9, generation=1)

    registry.updateCategoryCount("scene_1", "person", 2, generation=2)

    assert registry.getTotalCount("scene_1") == 2

  def test_same_generation_updates_its_own_count(self, registry):
    """Verify a tracker keeps updating its own entry every cycle."""
    registry.updateCategoryCount("scene_1", "person", 2, generation=3)

    registry.updateCategoryCount("scene_1", "person", 4, generation=3)

    assert registry.getTotalCount("scene_1") == 4

  def test_older_generation_cannot_remove_a_newer_count(self, registry):
    """Verify the old tracker's shutdown leaves the replacement's count alone."""
    registry.updateCategoryCount("scene_1", "person", 2, generation=2)

    registry.removeCategory("scene_1", "person", generation=1)

    assert registry.getTotalCount("scene_1") == 2

  def test_owner_removes_its_own_count(self, registry):
    """Verify a tracker still removes the entry it reported."""
    registry.updateCategoryCount("scene_1", "person", 2, generation=2)

    registry.removeCategory("scene_1", "person", generation=2)

    assert registry.getTotalCount("scene_1") == 0

  def test_categories_are_ordered_independently(self, registry):
    """Verify a newer generation in one category does not shield another."""
    registry.updateCategoryCount("scene_1", "car", 1, generation=5)

    registry.updateCategoryCount("scene_1", "person", 3, generation=1)

    assert registry.getTotalCount("scene_1") == 4

  def test_unversioned_calls_still_overwrite_and_remove(self, registry):
    """Verify callers that pass no generation keep the unconditional behavior."""
    registry.updateCategoryCount("scene_1", "person", 2, generation=2)

    registry.updateCategoryCount("scene_1", "person", 7)
    assert registry.getTotalCount("scene_1") == 7

    registry.removeCategory("scene_1", "person")
    assert registry.getTotalCount("scene_1") == 0


class TestRemoveScene:
  """Test removing an entire scene from the registry."""

  def test_remove_scene_clears_total(self, registry):
    """Verify removing a scene drops every category it had, total goes to 0."""
    registry.updateCategoryCount("scene_1", "person", 5)
    registry.updateCategoryCount("scene_1", "car", 2)

    registry.removeScene("scene_1")

    assert registry.getTotalCount("scene_1") == 0

  def test_remove_scene_does_not_affect_other_scenes(self, registry):
    """Verify removing one scene leaves other scenes' totals untouched."""
    registry.updateCategoryCount("scene_1", "person", 5)
    registry.updateCategoryCount("scene_2", "person", 10)

    registry.removeScene("scene_1")

    assert registry.getTotalCount("scene_2") == 10

  def test_remove_unknown_scene_does_not_raise(self, registry):
    """Verify removing a scene that was never registered is a safe no-op."""
    registry.removeScene("never_seen_scene")  # should not raise


class TestSingleton:
  """Test getInstance(), isolated from the direct-instantiation state tests above."""

  def setup_method(self):
    TrackedObjectRegistry._instance = None

  def teardown_method(self):
    TrackedObjectRegistry._instance = None

  def test_get_instance_returns_same_object(self):
    """Verify repeated calls return the same process-wide instance."""
    a = TrackedObjectRegistry.getInstance()
    b = TrackedObjectRegistry.getInstance()

    assert a is b

  def test_get_instance_creates_on_first_call(self):
    """Verify the singleton is lazily created on first access, not at import time."""
    assert TrackedObjectRegistry._instance is None

    instance = TrackedObjectRegistry.getInstance()

    assert instance is not None
    assert TrackedObjectRegistry._instance is instance
