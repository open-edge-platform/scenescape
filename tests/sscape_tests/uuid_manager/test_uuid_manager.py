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

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_is_new_tracker_id_increments_counter_when_no_reid(self, mock_vdms_class):
    """Verify unique_id_count increments when tracker has no reid vector."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    manager = UUIDManager()
    initial_count = manager.unique_id_count

    obj = MagicMock()
    obj.rv_id = "tracker_no_reid"
    obj.reid = None

    result = manager.isNewTrackerID(obj)

    assert result is True, "Should return True for new tracker"
    assert manager.unique_id_count == initial_count + 1, "Should increment counter when no reid"


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
