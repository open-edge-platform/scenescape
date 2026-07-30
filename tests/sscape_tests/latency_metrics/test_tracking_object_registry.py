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

from controller.tracking_object_registry import TrackedObjectRegistry

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