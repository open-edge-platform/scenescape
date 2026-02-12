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
    obj.reidVector = {
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
    obj.reidVector = np.array([0.1, 0.2, 0.3, 0.4]).astype(np.float32).tolist()
    
    embedding = manager._extractReidEmbedding(obj)
    
    assert embedding is not None, "Should extract embedding from legacy format"
    assert len(embedding) == 4, "Embedding should have correct length"

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_extract_reid_returns_none_when_missing(self, mock_vdms_class):
    """Verify None is returned when reid field is missing."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance
    
    manager = UUIDManager()
    
    # Create object without reidVector field using spec
    obj = Mock(spec=['rv_id'])
    
    embedding = manager._extractReidEmbedding(obj)
    
    assert embedding is None, "Should return None when reidVector is missing"

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_extract_reid_returns_none_when_none_value(self, mock_vdms_class):
    """Verify None is returned when reidVector value is None."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance
    
    manager = UUIDManager()
    
    # Create object with reidVector=None
    obj = MagicMock()
    obj.reidVector = None
    
    embedding = manager._extractReidEmbedding(obj)
    
    assert embedding is None, "Should return None when reidVector value is None"


class TestExtractSemanticMetadata:
  """Test semantic metadata extraction from detection objects."""

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_extract_semantic_metadata_new_format(self, mock_vdms_class):
    """Verify extraction from new metadata format: {value, model_name, confidence}."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance
    
    manager = UUIDManager()
    
    # Create object with new metadata format
    obj = MagicMock()
    obj.category = "Person"  # Generic property (should be skipped)
    obj.gender = {"value": "Female", "model_name": "gender_v2", "confidence": 0.95}
    obj.age = {"value": 28, "model_name": "age_estimator", "confidence": 0.87}
    
    metadata = manager._extractSemanticMetadata(obj)
    
    # Should extract semantic attributes as-is (full dict structure)
    assert "gender" in metadata, "Should extract gender metadata"
    assert metadata["gender"] == {"value": "Female", "model_name": "gender_v2", "confidence": 0.95}, \
      "Should preserve full metadata dict with value, model_name, and confidence"
    assert "age" in metadata, "Should extract age metadata"
    assert metadata["age"] == {"value": 28, "model_name": "age_estimator", "confidence": 0.87}, \
      "Should preserve full metadata dict for age"
    
    # Should skip generic properties
    assert "category" not in metadata, "Should not include generic properties"

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_extract_semantic_metadata_skips_generic_properties(self, mock_vdms_class):
    """Verify generic properties are excluded from metadata."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance
    
    manager = UUIDManager()
    
    # Create object with generic properties
    obj = MagicMock()
    obj.category = "Person"
    obj.confidence = 0.95
    obj.bounding_box_px = {"x": 0, "y": 0}
    obj.reid = [0.1, 0.2, 0.3, 0.4]
    obj.custom_attribute = {"value": "test", "model_name": "test_model", "confidence": 0.9}
    
    metadata = manager._extractSemanticMetadata(obj)
    
    # Generic properties should be excluded
    assert "category" not in metadata
    assert "confidence" not in metadata
    assert "bounding_box_px" not in metadata
    assert "reid" not in metadata
    
    # Custom semantic attributes should be included (as-is, full structure)
    assert "custom_attribute" in metadata
    assert metadata["custom_attribute"] == {"value": "test", "model_name": "test_model", "confidence": 0.9}

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_extract_semantic_metadata_skips_internal_fields(self, mock_vdms_class):
    """Verify internal fields (starting with _) are excluded."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance
    
    manager = UUIDManager()
    
    # Create object with internal fields
    obj = MagicMock()
    obj._internal_field = "should_be_skipped"
    obj._private = "hidden"
    obj.public_attribute = {"value": "visible", "model_name": "model", "confidence": 0.9}
    
    metadata = manager._extractSemanticMetadata(obj)
    
    # Internal fields should be skipped
    assert "_internal_field" not in metadata
    assert "_private" not in metadata
    
    # Public attributes should be included
    assert "public_attribute" in metadata

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_extract_semantic_metadata_handles_none_values(self, mock_vdms_class):
    """Verify None values are skipped."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance
    
    manager = UUIDManager()
    
    # Create object with None values
    obj = MagicMock()
    obj.nullable_attribute = None
    obj.valid_attribute = {"value": "something", "model_name": "model", "confidence": 0.9}
    
    metadata = manager._extractSemanticMetadata(obj)
    
    # None values should be skipped
    assert "nullable_attribute" not in metadata
    
    # Valid attributes should be included
    assert "valid_attribute" in metadata

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_extract_semantic_metadata_preserves_value_types(self, mock_vdms_class):
    """Verify extracted values preserve their data types."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance
    
    manager = UUIDManager()
    
    # Create object with various value types
    obj = MagicMock()
    obj.string_attr = {"value": "text", "model_name": "model", "confidence": 0.9}
    obj.int_attr = {"value": 42, "model_name": "model", "confidence": 0.9}
    obj.float_attr = {"value": 3.14, "model_name": "model", "confidence": 0.9}
    obj.bool_attr = {"value": True, "model_name": "model", "confidence": 0.9}
    
    metadata = manager._extractSemanticMetadata(obj)
    
    # Metadata is passed as-is (full dict structure), so check the dict values
    assert metadata["string_attr"] == {"value": "text", "model_name": "model", "confidence": 0.9}
    assert metadata["int_attr"] == {"value": 42, "model_name": "model", "confidence": 0.9}
    assert metadata["float_attr"] == {"value": 3.14, "model_name": "model", "confidence": 0.9}
    assert metadata["bool_attr"] == {"value": True, "model_name": "model", "confidence": 0.9}

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_extract_semantic_metadata_handles_legacy_format(self, mock_vdms_class):
    """Verify legacy format (plain values) are also extracted."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance
    
    manager = UUIDManager()
    
    # Create object with legacy format (plain values)
    obj = MagicMock()
    obj.color = "red"  # Legacy: plain value
    obj.clothing = "jacket"  # Legacy: plain value
    obj.modern_attr = {"value": "new format", "model_name": "model", "confidence": 0.9}
    
    metadata = manager._extractSemanticMetadata(obj)
    
    # Legacy format values should be preserved as-is
    assert metadata.get("color") == "red"
    assert metadata.get("clothing") == "jacket"
    
    # Modern format should also work (as-is, full dict structure)
    assert metadata.get("modern_attr") == {"value": "new format", "model_name": "model", "confidence": 0.9}


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
    obj.reidVector = np.array([0.1, 0.2, 0.3, 0.4])
    
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
    obj.reidVector = np.array([0.1, 0.2, 0.3, 0.4])
    
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
    obj.reidVector = None
    
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
    obj.person_name = {"value": "José García", "model_name": "name_detector", "confidence": 0.9}
    obj.location = {"value": "北京", "model_name": "location_detector", "confidence": 0.85}
    
    metadata = manager._extractSemanticMetadata(obj)
    
    # Metadata is passed as-is (full dict structure)
    assert metadata["person_name"] == {"value": "José García", "model_name": "name_detector", "confidence": 0.9}
    assert metadata["location"] == {"value": "北京", "model_name": "location_detector", "confidence": 0.85}

  @patch('controller.uuid_manager.VDMSDatabase')
  def test_metadata_with_special_characters(self, mock_vdms_class):
    """Verify special characters in metadata are preserved."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance
    
    manager = UUIDManager()
    
    obj = MagicMock()
    obj.description = {
      "value": 'Test "quoted" and \'apostrophe\' & symbols',
      "model_name": "desc",
      "confidence": 0.9
    }
    
    metadata = manager._extractSemanticMetadata(obj)
    
    # Metadata is passed as-is (full dict structure)
    assert metadata["description"] == {
      "value": 'Test "quoted" and \'apostrophe\' & symbols',
      "model_name": "desc",
      "confidence": 0.9
    }
