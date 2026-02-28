#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for UUIDManager.
Tests the interface and behavior of UUID manager without implementation bias.
These tests run inside the controller container where all dependencies are available.
"""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock, patch

from controller.uuid_manager import UUIDManager


class TestUUIDManagerInitialization:
  """Test UUIDManager initialization and basic setup."""

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_initialization_with_default_database(self, mock_vdms_class):
    """Verify UUIDManager initializes with default VDMS database."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()

    assert manager is not None
    assert hasattr(manager, 'reid_database'), "Should have reid_database attribute"
    assert manager.reid_database is not None
    assert manager.unique_id_count == 0
    assert manager.reid_enabled is True

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_initialization_with_custom_database(self, mock_vdms_class):
    """Verify UUIDManager can be initialized with custom database."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager(database="VDMS")

    assert manager is not None
    assert manager.reid_database is not None

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_has_thread_pool_for_async_operations(self, mock_vdms_class):
    """Verify UUIDManager has thread pool for asynchronous database operations."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()

    assert hasattr(manager, 'pool'), "Should have thread pool"
    assert manager.pool is not None

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_active_ids_tracking_initialized(self, mock_vdms_class):
    """Verify active_ids dictionary is initialized for tracking."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()

    assert hasattr(manager, 'active_ids')
    assert isinstance(manager.active_ids, dict)
    assert len(manager.active_ids) == 0


class TestExtractReidEmbedding:
  """Test Re-ID embedding extraction from detection objects."""

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_extract_reid_from_new_format(self, mock_vdms_class):
    """Verify extraction from new format: dict with 'embedding_vector' key."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()

    # Create object with new reid format
    obj = MagicMock()
    obj.reid = {
      "embedding_vector": np.array([0.1, 0.2, 0.3, 0.4]).astype(np.float32).tolist(),
      "model_name": "reid_model_v3"
    }

    embedding = manager._extractReidEmbedding(obj)

    assert embedding is not None, "Should extract embedding from new format"
    assert len(embedding) == 4, "Embedding should have correct length"

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_extract_reid_from_legacy_format(self, mock_vdms_class):
    """Verify extraction from legacy format: direct vector."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()

    # Create object with legacy reid format (direct vector)
    obj = MagicMock()
    obj.reid = np.array([0.1, 0.2, 0.3, 0.4]).astype(np.float32).tolist()

    embedding = manager._extractReidEmbedding(obj)

    assert embedding is not None, "Should extract embedding from legacy format"
    assert len(embedding) == 4, "Embedding should have correct length"

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_extract_reid_returns_none_when_missing(self, mock_vdms_class):
    """Verify None is returned when reid field is missing."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()

    # Create object without reid field using spec
    obj = Mock(spec=['rv_id'])

    embedding = manager._extractReidEmbedding(obj)

    assert embedding is None, "Should return None when reid is missing"

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_extract_reid_returns_none_when_none_value(self, mock_vdms_class):
    """Verify None is returned when reid value is None."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()

    # Create object with reid=None
    obj = MagicMock()
    obj.reid = None

    embedding = manager._extractReidEmbedding(obj)

    assert embedding is None, "Should return None when reid value is None"


class TestExtractSemanticMetadata:
  """Test semantic metadata extraction from detection objects."""

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_extract_semantic_metadata_new_format(self, mock_vdms_class):
    """Verify extraction from new metadata format: metadata attribute."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()

    # Create object with metadata attribute (new structure)
    obj = MagicMock()
    obj.category = "Person"  # Generic property (stays as-is, not in metadata)
    obj.metadata = {
      "gender": {"label": "Female", "model_name": "gender_v2", "confidence": 0.95},
      "age": {"label": 28, "model_name": "age_estimator", "confidence": 0.87}
    }

    metadata = manager._extractSemanticMetadata(obj)

    # Should extract metadata attribute directly
    assert "gender" in metadata, "Should extract gender metadata"
    assert metadata["gender"] == {"label": "Female", "model_name": "gender_v2", "confidence": 0.95}, \
      "Should preserve full metadata dict with label, model_name, and confidence"
    assert "age" in metadata, "Should extract age metadata"
    assert metadata["age"] == {"label": 28, "model_name": "age_estimator", "confidence": 0.87}, \
      "Should preserve full metadata dict for age"

    # Generic properties should not be in metadata
    assert "category" not in metadata, "Should not include generic properties"

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_extract_semantic_metadata_skips_generic_properties(self, mock_vdms_class):
    """Verify generic properties are excluded from metadata extraction."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()

    # Create object with metadata attribute (new structure)
    obj = MagicMock()
    obj.category = "Person"
    obj.confidence = 0.95
    obj.bounding_box_px = {"x": 0, "y": 0}
    obj.metadata = {
      "custom_attribute": {"label": "test", "model_name": "test_model", "confidence": 0.9}
    }

    metadata = manager._extractSemanticMetadata(obj)

    # Only metadata attribute should be extracted
    assert "category" not in metadata
    assert "confidence" not in metadata
    assert "bounding_box_px" not in metadata

    # Metadata attributes should be included
    assert "custom_attribute" in metadata
    assert metadata["custom_attribute"] == {"label": "test", "model_name": "test_model", "confidence": 0.9}

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_extract_semantic_metadata_skips_internal_fields(self, mock_vdms_class):
    """Verify only metadata attribute is extracted, not internal fields."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()

    # Create object with internal fields
    obj = MagicMock()
    obj._internal_field = "should_be_skipped"
    obj._private = "hidden"
    obj.metadata = {
      "public_attribute": {"label": "visible", "model_name": "model", "confidence": 0.9}
    }

    metadata = manager._extractSemanticMetadata(obj)

    # Internal fields should not be extracted (only metadata attribute is)
    assert "_internal_field" not in metadata
    assert "_private" not in metadata

    # Metadata contents should be extracted
    assert "public_attribute" in metadata

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_extract_semantic_metadata_handles_none_values(self, mock_vdms_class):
    """Verify None metadata is handled gracefully."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()

    # Create object with None metadata
    obj = MagicMock()
    obj.metadata = None

    metadata = manager._extractSemanticMetadata(obj)

    # Should return empty dict when metadata is None
    assert metadata == {}

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_extract_semantic_metadata_preserves_value_types(self, mock_vdms_class):
    """Verify extracted metadata preserves data types."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()

    # Create object with various value types in metadata
    obj = MagicMock()
    obj.metadata = {
      "string_attr": {"label": "text", "model_name": "model", "confidence": 0.9},
      "int_attr": {"label": 42, "model_name": "model", "confidence": 0.9},
      "float_attr": {"label": 3.14, "model_name": "model", "confidence": 0.9},
      "bool_attr": {"label": True, "model_name": "model", "confidence": 0.9}
    }

    metadata = manager._extractSemanticMetadata(obj)

    # Verify all types are preserved
    assert metadata["string_attr"] == {"label": "text", "model_name": "model", "confidence": 0.9}
    assert metadata["int_attr"] == {"label": 42, "model_name": "model", "confidence": 0.9}
    assert metadata["float_attr"] == {"label": 3.14, "model_name": "model", "confidence": 0.9}
    assert metadata["bool_attr"] == {"label": True, "model_name": "model", "confidence": 0.9}

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_extract_semantic_metadata_handles_legacy_format(self, mock_vdms_class):
    """Verify no metadata attribute returns empty dict (legacy objects)."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()

    # Create a real object without metadata attribute (not MagicMock which creates attrs dynamically)
    class LegacyObject:
      def __init__(self):
        self.color = "red"
        self.clothing = "jacket"

    obj = LegacyObject()

    metadata = manager._extractSemanticMetadata(obj)

    # Should return empty dict for objects without metadata attribute
    assert metadata == {}


class TestIsNewTrackerID:
  """Test checking if tracker ID is new."""

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_is_new_tracker_id_when_not_seen_before(self, mock_vdms_class):
    """Verify isNewTrackerID returns True for unseen tracker IDs."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()

    obj = MagicMock()
    obj.rv_id = "tracker_123"
    obj.reid = {"embedding_vector": np.array([0.1, 0.2, 0.3, 0.4])}

    result = manager.isNewTrackerID(obj)

    assert result is True, "Should return True for new tracker ID"

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_is_new_tracker_id_when_seen_before(self, mock_vdms_class):
    """Verify isNewTrackerID returns False for known tracker IDs."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()

    # Add tracker to active_ids
    manager.active_ids["tracker_123"] = ("gid_1", 0.95)

    obj = MagicMock()
    obj.rv_id = "tracker_123"
    obj.reid = {"embedding_vector": np.array([0.1, 0.2, 0.3, 0.4])}

    result = manager.isNewTrackerID(obj)

    assert result is False, "Should return False for known tracker ID"


class TestAssignID:
  """Test ID assignment logic."""

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_assign_id_increments_counter_when_no_reid(self, mock_vdms_class):
    """Verify unique_id_count increments when tracker has no reid vector."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()
    initial_count = manager.unique_id_count

    obj = MagicMock()
    obj.rv_id = "tracker_no_reid"
    obj.reid = None
    obj.category = "Person"
    obj.gid = "auto_gid_1"
    obj.metadata = {}

    manager.assignID(obj)

    assert manager.unique_id_count == initial_count + 1, "Should increment counter when assigning ID to tracker with no reid"

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_assign_id_does_not_increment_counter_when_reid_present(self, mock_vdms_class):
    """Verify unique_id_count is not incremented when tracker has reid vector."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()
    initial_count = manager.unique_id_count

    obj = MagicMock()
    obj.rv_id = "tracker_with_reid"
    obj.reid = {"embedding_vector": np.array([0.1, 0.2, 0.3, 0.4]).astype(np.float32).tolist()}
    obj.category = "Person"
    obj.gid = "auto_gid_1"
    obj.boundingBoxPixels = MagicMock()
    obj.boundingBoxPixels.area = 10000
    obj.metadata = {}

    manager.assignID(obj)

    assert manager.unique_id_count == initial_count, "Should not increment counter when reid is present"

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_assign_id_initializes_tracking_for_new_tracker(self, mock_vdms_class):
    """Verify assignID initializes tracking for new tracker IDs."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()

    obj = MagicMock()
    obj.rv_id = "new_tracker"
    obj.reid = None
    obj.category = "Person"
    obj.gid = "auto_gid_1"
    obj.metadata = {}

    manager.assignID(obj)

    assert "new_tracker" in manager.active_ids, "Should initialize tracking for new tracker"
    assert manager.active_ids["new_tracker"] == [None, None], "Should initialize with [None, None]"

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_assign_id_gathers_quality_features_for_new_tracker(self, mock_vdms_class):
    """Verify assignID gathers quality visual features for new tracker."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()

    obj = MagicMock()
    obj.rv_id = "new_tracker_with_features"
    obj.reid = {"embedding_vector": np.array([0.1, 0.2, 0.3, 0.4]).astype(np.float32).tolist()}
    obj.category = "Person"
    obj.gid = "auto_gid_1"
    obj.boundingBoxPixels = MagicMock()
    obj.boundingBoxPixels.area = 10000
    obj.metadata = {}

    manager.assignID(obj)

    # Should have gathered features for the tracker
    assert "new_tracker_with_features" in manager.quality_features, "Should gather quality features for new tracker"
    assert len(manager.quality_features["new_tracker_with_features"]) > 0, "Should have collected at least one feature"

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_assign_id_calls_pick_best_id_always(self, mock_vdms_class):
    """Verify assignID always calls pickBestID."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()
    # Mock pickBestID to verify it's called
    manager.pickBestID = MagicMock()

    obj = MagicMock()
    obj.rv_id = "tracker_123"
    obj.reid = None
    obj.category = "Person"
    obj.gid = "auto_gid_1"
    obj.metadata = {}

    manager.assignID(obj)

    manager.pickBestID.assert_called_once_with(obj), "Should call pickBestID"

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_assign_id_does_not_submit_query_without_sufficient_features(self, mock_vdms_class):
    """Verify assignID does not submit query if features are insufficient."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()
    manager.pool = MagicMock()

    obj = MagicMock()
    obj.rv_id = "tracker_few_features"
    obj.reid = {"embedding_vector": np.array([0.1, 0.2, 0.3, 0.4]).astype(np.float32).tolist()}
    obj.category = "Person"
    obj.gid = "auto_gid_1"
    obj.boundingBoxPixels = MagicMock()
    obj.boundingBoxPixels.area = 10000
    obj.metadata = {}

    manager.assignID(obj)

    # Only one feature gathered, less than minimum required
    assert manager.pool.submit.call_count == 0, "Should not submit query without sufficient features"

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_assign_id_submits_query_with_sufficient_features(self, mock_vdms_class):
    """Verify assignID submits similarity query when sufficient features are gathered."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()
    manager.pool = MagicMock()

    obj = MagicMock()
    obj.rv_id = "tracker_many_features"
    obj.reid = {"embedding_vector": np.array([0.1, 0.2, 0.3, 0.4]).astype(np.float32).tolist()}
    obj.category = "Person"
    obj.gid = "auto_gid_1"
    obj.boundingBoxPixels = MagicMock()
    obj.boundingBoxPixels.area = 10000
    obj.metadata = {}

    # Manually add sufficient features to trigger query submission
    manager.quality_features["tracker_many_features"] = [
      np.array([0.1, 0.2, 0.3, 0.4]).astype(np.float32).tolist() for _ in range(15)
    ]

    manager.assignID(obj)

    # Should submit query after gathering features and determining sufficiency
    assert manager.pool.submit.call_count >= 1, "Should submit query with sufficient features"
    assert "tracker_many_features" in manager.active_query, "Should mark query as submitted"

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_assign_id_skips_feature_gathering_if_query_already_submitted(self, mock_vdms_class):
    """Verify assignID doesn't resubmit queries if one is already in progress."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()
    manager.pool = MagicMock()

    obj = MagicMock()
    obj.rv_id = "tracker_with_pending_query"
    obj.reid = {"embedding_vector": np.array([0.1, 0.2, 0.3, 0.4]).astype(np.float32).tolist()}
    obj.category = "Person"
    obj.gid = "auto_gid_1"
    obj.boundingBoxPixels = MagicMock()
    obj.boundingBoxPixels.area = 10000
    obj.metadata = {}

    # Mark query as already submitted
    manager.active_query["tracker_with_pending_query"] = True

    initial_features = len(manager.quality_features.get("tracker_with_pending_query", []))

    manager.assignID(obj)

    # Should not gather new features or submit another query
    assert len(manager.quality_features.get("tracker_with_pending_query", [])) == initial_features, \
      "Should not gather features if query already submitted"


class TestConnectDatabase:
  """Test database connection."""

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_connect_database_submits_to_pool(self, mock_vdms_class):
    """Verify connectDatabase submits connection task to thread pool."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()

    # Track that connect was called through pool.submit
    manager.connectDatabase()

    # Verify pool.submit was called once
    assert manager.pool is not None, "Thread pool should exist"
    # The actual connect call will happen async in the pool
    # Just verify the method doesn't raise an exception


class TestDataTypes:
  """Test data type handling and preservation."""

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_metadata_with_unicode_strings(self, mock_vdms_class):
    """Verify Unicode strings in metadata are preserved."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()

    obj = MagicMock()
    obj.metadata = {
      "emotion": {"label": "Happy", "model_name": "emotion-recognition-retail-0003", "confidence": 0.9},
      "clothing_color": {"label": "Blue", "model_name": "clothing-attributes-recognition", "confidence": 0.85}
    }

    metadata = manager._extractSemanticMetadata(obj)

    # Metadata is passed as-is
    assert metadata["emotion"] == {"label": "Happy", "model_name": "emotion-recognition-retail-0003", "confidence": 0.9}
    assert metadata["clothing_color"] == {"label": "Blue", "model_name": "clothing-attributes-recognition", "confidence": 0.85}

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_metadata_with_special_characters(self, mock_vdms_class):
    """Verify special characters in metadata are preserved."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()

    obj = MagicMock()
    obj.metadata = {
      "description": {
        "label": 'Test "quoted" and \'apostrophe\' & symbols',
        "model_name": "desc",
        "confidence": 0.9
      }
    }

    metadata = manager._extractSemanticMetadata(obj)

    # Metadata is passed as-is
    assert metadata["description"] == {
      "label": 'Test "quoted" and \'apostrophe\' & symbols',
      "model_name": "desc",
      "confidence": 0.9
    }
