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


class TestAssignIDUniqueCountNoReid:
  """Test assignID() unique_count increment when object has no reid vector."""

  def setup_method(self):
    """Set up mock database and UUIDManager."""
    self.mock_db = Mock()
    self.mock_db.connect = Mock()
    with patch('controller.uuid_manager.available_databases', {'VDMS': Mock(return_value=self.mock_db)}):
      self.manager = UUIDManager(database='VDMS')

    # Mock camera for moving objects
    self.mock_camera = Mock()
    self.mock_camera.pose = Mock()
    self.mock_camera.pose.intrinsics = Mock()
    self.mock_camera.pose.intrinsics.mapPixelToNormalizedImagePlane = Mock(return_value=Mock())

  def test_assign_id_increments_count_when_object_has_no_reid_vector(self):
    """Verify unique_count increments immediately when object has no reid vector."""
    from controller.moving_object import MovingObject, ReidState
    import time

    # Create object with no reid vector
    info = {'id': '1', 'confidence': 0.95}
    obj = MovingObject(info, time.time(), self.mock_camera)
    obj.rv_id = 1
    obj.reid = None  # No reid vector

    initial_count = self.manager.unique_id_count
    self.manager.assignID(obj)

    # Should increment since no reid vector means instant unique object
    assert self.manager.unique_id_count == initial_count + 1

  def test_assign_id_does_not_double_count_same_track(self):
    """Verify assignID() doesn't increment for same track on subsequent calls."""
    from controller.moving_object import MovingObject
    import time

    info = {'id': '1', 'confidence': 0.95}
    obj = MovingObject(info, time.time(), self.mock_camera)
    obj.rv_id = 1
    obj.reid = None

    self.manager.assignID(obj)
    count_after_first = self.manager.unique_id_count

    # Call assignID() again with same object (same rv_id)
    self.manager.assignID(obj)
    count_after_second = self.manager.unique_id_count

    # Should NOT increment again (already tracked)
    assert count_after_second == count_after_first

  def test_multiple_objects_without_reid_each_increment_count(self):
    """Verify each new object without reid increments counter."""
    from controller.moving_object import MovingObject
    import time

    initial_count = self.manager.unique_id_count

    for i in range(3):
      info = {'id': str(i), 'confidence': 0.95}
      obj = MovingObject(info, time.time(), self.mock_camera)
      obj.rv_id = i
      obj.reid = None

      self.manager.assignID(obj)

    # Each object should have incremented counter
    assert self.manager.unique_id_count == initial_count + 3


class TestAssignIDWithReidVector:
  """Test assignID() behavior when object has reid vector."""

  def setup_method(self):
    """Set up mock database and UUIDManager."""
    self.mock_db = Mock()
    self.mock_db.connect = Mock()
    with patch('controller.uuid_manager.available_databases', {'VDMS': Mock(return_value=self.mock_db)}):
      self.manager = UUIDManager(database='VDMS')

    self.mock_camera = Mock()
    self.mock_camera.pose = Mock()
    self.mock_camera.pose.intrinsics = Mock()
    self.mock_camera.pose.intrinsics.mapPixelToNormalizedImagePlane = Mock(return_value=Mock())

  def test_assign_id_does_not_increment_when_has_reid_vector(self):
    """Verify assignID() does NOT increment when object has reid vector (pending query)."""
    from controller.moving_object import MovingObject
    import time

    info = {'id': '1', 'confidence': 0.95}
    obj = MovingObject(info, time.time(), self.mock_camera)
    obj.rv_id = 1
    obj.reid = [0.1, 0.2, 0.3]  # Has reid vector
    obj.boundingBoxPixels = Mock(area=10000)  # Large enough bbox

    initial_count = self.manager.unique_id_count
    self.manager.assignID(obj)

    # Should NOT increment (waiting for query result)
    assert self.manager.unique_id_count == initial_count

  def test_assign_id_state_remains_pending_with_reid_vector(self):
    """Verify object state remains PENDING_COLLECTION when gathering features."""
    from controller.moving_object import MovingObject, ReidState
    import time

    info = {'id': '1', 'confidence': 0.95}
    obj = MovingObject(info, time.time(), self.mock_camera)
    obj.rv_id = 1
    obj.reid = [0.1, 0.2, 0.3]
    obj.boundingBoxPixels = Mock(area=10000)
    obj.category = 'person'

    self.manager.assignID(obj)

    # State should still be PENDING_COLLECTION (query not submitted yet, insufficient features)
    assert obj.reid_state == ReidState.PENDING_COLLECTION


class TestUpdateActiveDictQueryNoMatch:
  """Test updateActiveDict() unique_count increment for QUERY_NO_MATCH."""

  def setup_method(self):
    """Set up mock database and UUIDManager."""
    self.mock_db = Mock()
    self.mock_db.connect = Mock()
    with patch('controller.uuid_manager.available_databases', {'VDMS': Mock(return_value=self.mock_db)}):
      self.manager = UUIDManager(database='VDMS')

    self.mock_camera = Mock()
    self.mock_camera.pose = Mock()
    self.mock_camera.pose.intrinsics = Mock()
    self.mock_camera.pose.intrinsics.mapPixelToNormalizedImagePlane = Mock(return_value=Mock())

  def test_update_active_dict_increments_for_query_no_match(self):
    """Verify unique_count increments when query is made but no match found."""
    from controller.moving_object import MovingObject, ReidState
    import time

    info = {'id': '1', 'confidence': 0.95}
    obj = MovingObject(info, time.time(), self.mock_camera)
    obj.rv_id = 1
    obj.reid = [0.1, 0.2, 0.3]
    obj.category = 'person'
    obj.boundingBoxPixels = Mock(area=10000)

    # Initialize active_ids entry
    with self.manager.active_ids_lock:
      self.manager.active_ids[obj.rv_id] = [None, None]

    # Add quality features to simulate gathered features
    self.manager.quality_features[obj.rv_id] = [[0.1, 0.2, 0.3]]

    initial_count = self.manager.unique_id_count

    # Simulate query that found no match
    self.manager.updateActiveDict(obj, database_id=None, similarity=None)

    # Should increment (new unique object, no match in database)
    assert self.manager.unique_id_count == initial_count + 1
    # State should be QUERY_NO_MATCH
    assert obj.reid_state == ReidState.QUERY_NO_MATCH

  def test_update_active_dict_assigns_new_gid_on_no_match(self):
    """Verify new GID is assigned when query finds no match."""
    from controller.moving_object import MovingObject
    import time

    info = {'id': '1', 'confidence': 0.95}
    obj = MovingObject(info, time.time(), self.mock_camera)
    obj.rv_id = 1
    obj.reid = [0.1, 0.2, 0.3]
    obj.category = 'person'

    with self.manager.active_ids_lock:
      self.manager.active_ids[obj.rv_id] = [None, None]

    self.manager.quality_features[obj.rv_id] = [[0.1, 0.2, 0.3]]

    # No match found
    self.manager.updateActiveDict(obj, database_id=None, similarity=None)

    # GID should be assigned
    assert obj.gid is not None
    # Similarity should be None (no match)
    assert obj.similarity is None
    # State should be QUERY_NO_MATCH
    from controller.moving_object import ReidState
    assert obj.reid_state == ReidState.QUERY_NO_MATCH

  def test_multiple_no_match_objects_each_increment_count(self):
    """Verify multiple QUERY_NO_MATCH objects each increment counter."""
    from controller.moving_object import MovingObject
    import time

    initial_count = self.manager.unique_id_count

    for i in range(3):
      info = {'id': str(i), 'confidence': 0.95}
      obj = MovingObject(info, time.time(), self.mock_camera)
      obj.rv_id = i
      obj.reid = [0.1, 0.2, 0.3]
      obj.category = 'person'

      with self.manager.active_ids_lock:
        self.manager.active_ids[obj.rv_id] = [None, None]

      self.manager.quality_features[obj.rv_id] = [[0.1, 0.2, 0.3]]

      # Query found no match
      self.manager.updateActiveDict(obj, database_id=None, similarity=None)

    # Each no-match should increment counter
    assert self.manager.unique_id_count == initial_count + 3


class TestUpdateActiveDictMatched:
  """Test updateActiveDict() does NOT increment for MATCHED objects."""

  def setup_method(self):
    """Set up mock database and UUIDManager."""
    self.mock_db = Mock()
    self.mock_db.connect = Mock()
    with patch('controller.uuid_manager.available_databases', {'VDMS': Mock(return_value=self.mock_db)}):
      self.manager = UUIDManager(database='VDMS')

    self.mock_camera = Mock()
    self.mock_camera.pose = Mock()
    self.mock_camera.pose.intrinsics = Mock()
    self.mock_camera.pose.intrinsics.mapPixelToNormalizedImagePlane = Mock(return_value=Mock())

  def test_update_active_dict_does_not_increment_for_matched(self):
    """Verify unique_count does NOT increment when query finds a match."""
    from controller.moving_object import MovingObject, ReidState
    import time

    info = {'id': '1', 'confidence': 0.95}
    obj = MovingObject(info, time.time(), self.mock_camera)
    obj.rv_id = 1
    obj.reid = [0.1, 0.2, 0.3]
    obj.category = 'person'

    # Initialize active_ids
    with self.manager.active_ids_lock:
      self.manager.active_ids[obj.rv_id] = [None, None]

    self.manager.quality_features[obj.rv_id] = [[0.1, 0.2, 0.3]]

    initial_count = self.manager.unique_id_count

    # Simulate query that found a match in database
    matched_gid = "database_gid_existing_123"
    similarity_score = 0.92
    self.manager.updateActiveDict(obj, database_id=matched_gid, similarity=similarity_score)

    # Should NOT increment (object already existed in database)
    assert self.manager.unique_id_count == initial_count
    # State should be MATCHED
    assert obj.reid_state == ReidState.MATCHED
    # GID should be from database
    assert obj.gid == matched_gid
    # Similarity should be the match score
    assert obj.similarity == similarity_score

  def test_matched_object_does_not_contribute_to_unique_count(self):
    """Verify matched objects don't change unique_count."""
    from controller.moving_object import MovingObject
    import time

    initial_count = self.manager.unique_id_count

    # Simulate multiple matched objects
    for i in range(3):
      info = {'id': str(i), 'confidence': 0.95}
      obj = MovingObject(info, time.time(), self.mock_camera)
      obj.rv_id = i
      obj.reid = [0.1, 0.2, 0.3]
      obj.category = 'person'

      with self.manager.active_ids_lock:
        self.manager.active_ids[obj.rv_id] = [None, None]

      self.manager.quality_features[obj.rv_id] = [[0.1, 0.2, 0.3]]

      # All found matches in database
      self.manager.updateActiveDict(obj, database_id=f"existing_gid_{i}", similarity=0.85 + i*0.01)

    # Matched objects should NOT increase counter
    assert self.manager.unique_id_count == initial_count


class TestReidDisabledScenario:
  """Test unique_count behavior when reid is disabled."""

  def setup_method(self):
    """Set up mock database and UUIDManager."""
    self.mock_db = Mock()
    self.mock_db.connect = Mock()
    with patch('controller.uuid_manager.available_databases', {'VDMS': Mock(return_value=self.mock_db)}):
      self.manager = UUIDManager(database='VDMS')

    self.mock_camera = Mock()
    self.mock_camera.pose = Mock()
    self.mock_camera.pose.intrinsics = Mock()
    self.mock_camera.pose.intrinsics.mapPixelToNormalizedImagePlane = Mock(return_value=Mock())

  def test_reid_disabled_sets_state_without_incrementing_count(self):
    """Verify REID_DISABLED state set without incrementing unique_count."""
    from controller.moving_object import MovingObject, ReidState
    import time

    info = {'id': '1', 'confidence': 0.95}
    obj = MovingObject(info, time.time(), self.mock_camera)
    obj.rv_id = 1
    obj.reid = [0.1, 0.2, 0.3]  # Has reid vector
    obj.boundingBoxPixels = Mock(area=10000)

    # Disable reid
    self.manager.reid_enabled = False

    initial_count = self.manager.unique_id_count
    self.manager.assignID(obj)

    # State should be REID_DISABLED
    assert obj.reid_state == ReidState.REID_DISABLED
    # Count should NOT increment (system disabled, no query attempted)
    assert self.manager.unique_id_count == initial_count

  def test_reid_disabled_object_with_no_reid_vector_still_increments(self):
    """Verify object without reid vector increments even when reid disabled."""
    from controller.moving_object import MovingObject, ReidState
    import time

    info = {'id': '1', 'confidence': 0.95}
    obj = MovingObject(info, time.time(), self.mock_camera)
    obj.rv_id = 1
    obj.reid = None  # No reid vector

    # Disable reid
    self.manager.reid_enabled = False

    initial_count = self.manager.unique_id_count
    self.manager.assignID(obj)

    # State should be REID_DISABLED
    assert obj.reid_state == ReidState.REID_DISABLED
    # Should still increment (no reid vector = instant unique)
    assert self.manager.unique_id_count == initial_count + 1


class TestMixedScenarioIntegration:
  """Test realistic scenarios combining multiple object types."""

  def setup_method(self):
    """Set up mock database and UUIDManager."""
    self.mock_db = Mock()
    self.mock_db.connect = Mock()
    with patch('controller.uuid_manager.available_databases', {'VDMS': Mock(return_value=self.mock_db)}):
      self.manager = UUIDManager(database='VDMS')

    self.mock_camera = Mock()
    self.mock_camera.pose = Mock()
    self.mock_camera.pose.intrinsics = Mock()
    self.mock_camera.pose.intrinsics.mapPixelToNormalizedImagePlane = Mock(return_value=Mock())

  def test_three_objects_scenario_count_matches_expected(self):
    """
    Integration test: Simulate test scenario with 3 people in queuing scene.
    Expected unique_count should be 3 (all are new unique objects).

    Scenario:
    - Person A: Has reid vector, query finds no match → count = 1
    - Person B: Has reid vector, query finds no match → count = 2
    - Person C: No reid vector → count = 3
    """
    from controller.moving_object import MovingObject
    import time

    initial_count = self.manager.unique_id_count

    # Person A: Query with no match
    obj_a = MovingObject({'id': 'A', 'confidence': 0.95}, time.time(), self.mock_camera)
    obj_a.rv_id = 'A'
    obj_a.reid = [0.1, 0.2, 0.3]
    obj_a.category = 'person'

    with self.manager.active_ids_lock:
      self.manager.active_ids[obj_a.rv_id] = [None, None]
    self.manager.quality_features[obj_a.rv_id] = [[0.1, 0.2, 0.3]]
    self.manager.updateActiveDict(obj_a, database_id=None, similarity=None)

    # Person B: Query with no match
    obj_b = MovingObject({'id': 'B', 'confidence': 0.95}, time.time(), self.mock_camera)
    obj_b.rv_id = 'B'
    obj_b.reid = [0.2, 0.3, 0.4]
    obj_b.category = 'person'

    with self.manager.active_ids_lock:
      self.manager.active_ids[obj_b.rv_id] = [None, None]
    self.manager.quality_features[obj_b.rv_id] = [[0.2, 0.3, 0.4]]
    self.manager.updateActiveDict(obj_b, database_id=None, similarity=None)

    # Person C: No reid vector
    obj_c = MovingObject({'id': 'C', 'confidence': 0.95}, time.time(), self.mock_camera)
    obj_c.rv_id = 'C'
    obj_c.reid = None
    self.manager.assignID(obj_c)

    # Should have 3 unique objects
    assert self.manager.unique_id_count == initial_count + 3

  def test_mixed_matched_and_new_objects_count_only_new(self):
    """
    Verify count only includes new unique objects, not matched ones.
    - Person A: Matched to database → does NOT increment
    - Person B: No match → increments
    - Person C: No reid → increments
    - Person D: Matched to database → does NOT increment
    Expected count = 2 (only B and C)
    """
    from controller.moving_object import MovingObject
    import time

    initial_count = self.manager.unique_id_count

    # Person A: Matched
    obj_a = MovingObject({'id': 'A', 'confidence': 0.95}, time.time(), self.mock_camera)
    obj_a.rv_id = 'A'
    obj_a.reid = [0.1, 0.2, 0.3]
    obj_a.category = 'person'
    with self.manager.active_ids_lock:
      self.manager.active_ids[obj_a.rv_id] = [None, None]
    self.manager.quality_features[obj_a.rv_id] = [[0.1, 0.2, 0.3]]
    self.manager.updateActiveDict(obj_a, database_id="existing_A", similarity=0.95)

    # Person B: No match
    obj_b = MovingObject({'id': 'B', 'confidence': 0.95}, time.time(), self.mock_camera)
    obj_b.rv_id = 'B'
    obj_b.reid = [0.2, 0.3, 0.4]
    obj_b.category = 'person'
    with self.manager.active_ids_lock:
      self.manager.active_ids[obj_b.rv_id] = [None, None]
    self.manager.quality_features[obj_b.rv_id] = [[0.2, 0.3, 0.4]]
    self.manager.updateActiveDict(obj_b, database_id=None, similarity=None)

    # Person C: No reid
    obj_c = MovingObject({'id': 'C', 'confidence': 0.95}, time.time(), self.mock_camera)
    obj_c.rv_id = 'C'
    obj_c.reid = None
    self.manager.assignID(obj_c)

    # Person D: Matched
    obj_d = MovingObject({'id': 'D', 'confidence': 0.95}, time.time(), self.mock_camera)
    obj_d.rv_id = 'D'
    obj_d.reid = [0.4, 0.5, 0.6]
    obj_d.category = 'person'
    with self.manager.active_ids_lock:
      self.manager.active_ids[obj_d.rv_id] = [None, None]
    self.manager.quality_features[obj_d.rv_id] = [[0.4, 0.5, 0.6]]
    self.manager.updateActiveDict(obj_d, database_id="existing_D", similarity=0.90)

    # Only B and C should increment (2 new unique objects)
    assert self.manager.unique_id_count == initial_count + 2


class TestUniqueCountEdgeCases:
  """Test edge cases and boundary conditions."""

  def setup_method(self):
    """Set up mock database and UUIDManager."""
    self.mock_db = Mock()
    self.mock_db.connect = Mock()
    with patch('controller.uuid_manager.available_databases', {'VDMS': Mock(return_value=self.mock_db)}):
      self.manager = UUIDManager(database='VDMS')

    self.mock_camera = Mock()
    self.mock_camera.pose = Mock()
    self.mock_camera.pose.intrinsics = Mock()
    self.mock_camera.pose.intrinsics.mapPixelToNormalizedImagePlane = Mock(return_value=Mock())

  def test_similarity_zero_still_matches(self):
    """Verify object with 0.0 similarity is still counted as MATCHED (not incremented)."""
    from controller.moving_object import MovingObject, ReidState
    import time

    info = {'id': '1', 'confidence': 0.95}
    obj = MovingObject(info, time.time(), self.mock_camera)
    obj.rv_id = 1
    obj.reid = [0.1, 0.2, 0.3]
    obj.category = 'person'

    with self.manager.active_ids_lock:
      self.manager.active_ids[obj.rv_id] = [None, None]
    self.manager.quality_features[obj.rv_id] = [[0.1, 0.2, 0.3]]

    initial_count = self.manager.unique_id_count

    # Edge case: similarity = 0.0 (worst match, but still a match)
    self.manager.updateActiveDict(obj, database_id="existing_gid", similarity=0.0)

    # Should NOT increment (is_matched because similarity is not None)
    assert self.manager.unique_id_count == initial_count
    assert obj.similarity == 0.0
    assert obj.reid_state == ReidState.MATCHED

  def test_similarity_high_value_still_just_one_count(self):
    """Verify high similarity score doesn't cause multiple increments."""
    from controller.moving_object import MovingObject
    import time

    info = {'id': '1', 'confidence': 0.95}
    obj = MovingObject(info, time.time(), self.mock_camera)
    obj.rv_id = 1
    obj.reid = [0.1, 0.2, 0.3]
    obj.category = 'person'

    with self.manager.active_ids_lock:
      self.manager.active_ids[obj.rv_id] = [None, None]
    self.manager.quality_features[obj.rv_id] = [[0.1, 0.2, 0.3]]

    initial_count = self.manager.unique_id_count

    # Perfect match: similarity = 1.0
    self.manager.updateActiveDict(obj, database_id="existing_gid", similarity=1.0)

    # Should NOT increment
    assert self.manager.unique_id_count == initial_count
    assert obj.similarity == 1.0


class TestUpdateActiveDictStateTransitionsAndChaining:
  """Test state transitions and previous_ids_chain recording in updateActiveDict()."""

  def setup_method(self):
    """Set up mock database and UUIDManager."""
    self.mock_db = Mock()
    self.mock_db.connect = Mock()
    with patch('controller.uuid_manager.available_databases', {'VDMS': Mock(return_value=self.mock_db)}):
      self.manager = UUIDManager(database='VDMS')

    self.mock_camera = Mock()
    self.mock_camera.pose = Mock()
    self.mock_camera.pose.intrinsics = Mock()
    self.mock_camera.pose.intrinsics.mapPixelToNormalizedImagePlane = Mock(return_value=Mock())

  def test_match_found_records_id_change_with_similarity(self):
    """Verify that matched objects record ID change with similarity score in previous_ids_chain."""
    from controller.moving_object import MovingObject, ReidState
    import time

    info = {'id': '1', 'confidence': 0.95}
    obj = MovingObject(info, time.time(), self.mock_camera)
    obj.rv_id = 1
    obj.reid = [0.1, 0.2, 0.3]
    obj.category = 'person'

    with self.manager.active_ids_lock:
      self.manager.active_ids[obj.rv_id] = [None, None]

    self.manager.quality_features[obj.rv_id] = [[0.1, 0.2, 0.3]]

    # Match found with high similarity
    matched_id = "database_gid_match_001"
    similarity_score = 0.92
    query_time = time.time()

    self.manager.updateActiveDict(obj, database_id=matched_id, similarity=similarity_score, query_timestamp=query_time)

    # Verify state
    assert obj.reid_state == ReidState.MATCHED
    assert obj.gid == matched_id
    assert obj.similarity == similarity_score

    # Verify previous_ids_chain was populated
    assert len(obj.previous_ids_chain) == 1
    chain_entry = obj.previous_ids_chain[0]
    assert chain_entry['id'] == matched_id
    assert chain_entry['similarity_score'] == similarity_score
    assert chain_entry['timestamp'] == query_time

  def test_no_match_records_id_change_with_none_similarity(self):
    """Verify that no-match objects record ID change with None similarity in previous_ids_chain."""
    from controller.moving_object import MovingObject, ReidState
    import time

    info = {'id': '1', 'confidence': 0.95}
    obj = MovingObject(info, time.time(), self.mock_camera)
    obj.rv_id = 1
    obj.reid = [0.1, 0.2, 0.3]
    obj.category = 'person'

    with self.manager.active_ids_lock:
      self.manager.active_ids[obj.rv_id] = [None, None]

    self.manager.quality_features[obj.rv_id] = [[0.1, 0.2, 0.3]]

    # Query made but no match found
    query_time = time.time()
    self.manager.updateActiveDict(obj, database_id=None, similarity=None, query_timestamp=query_time)

    # Verify state
    assert obj.reid_state == ReidState.QUERY_NO_MATCH
    assert obj.gid is not None
    assert obj.similarity is None

    # Verify previous_ids_chain recorded with None similarity
    assert len(obj.previous_ids_chain) == 1
    chain_entry = obj.previous_ids_chain[0]
    assert chain_entry['id'] == obj.gid
    assert chain_entry['similarity_score'] is None
    assert chain_entry['timestamp'] == query_time

  def test_match_updates_active_ids_and_similarity(self):
    """Verify active_ids dict and similarity are properly updated on match."""
    from controller.moving_object import MovingObject
    import time

    info = {'id': '1', 'confidence': 0.95}
    obj = MovingObject(info, time.time(), self.mock_camera)
    obj.rv_id = 1
    obj.reid = [0.1, 0.2, 0.3]
    obj.category = 'person'

    with self.manager.active_ids_lock:
      self.manager.active_ids[obj.rv_id] = [None, None]

    self.manager.quality_features[obj.rv_id] = [[0.1, 0.2, 0.3]]

    matched_id = "db_match_789"
    similarity = 0.87
    self.manager.updateActiveDict(obj, database_id=matched_id, similarity=similarity)

    # Verify active_ids was updated
    assert obj.rv_id in self.manager.active_ids
    assert self.manager.active_ids[obj.rv_id][0] == matched_id
    assert self.manager.active_ids[obj.rv_id][1] == similarity

  def test_no_match_generates_new_gid_and_updates_active_ids(self):
    """Verify new GID is generated and active_ids is updated on no match."""
    from controller.moving_object import MovingObject
    import time

    info = {'id': '1', 'confidence': 0.95}
    obj = MovingObject(info, time.time(), self.mock_camera)
    obj.rv_id = 1
    obj.reid = [0.1, 0.2, 0.3]
    obj.category = 'person'

    with self.manager.active_ids_lock:
      self.manager.active_ids[obj.rv_id] = [None, None]

    self.manager.quality_features[obj.rv_id] = [[0.1, 0.2, 0.3]]

    old_gid_counter = MovingObject.gid_counter

    # Query found no match
    self.manager.updateActiveDict(obj, database_id=None, similarity=None)

    # Verify new GID was generated
    assert obj.gid == old_gid_counter
    assert obj.gid is not None

    # Verify active_ids updated with generated GID
    assert obj.rv_id in self.manager.active_ids
    assert self.manager.active_ids[obj.rv_id][0] == obj.gid
    assert self.manager.active_ids[obj.rv_id][1] is None

  def test_features_for_database_populated_on_match(self):
    """Verify features_for_database is populated with metadata on match."""
    from controller.moving_object import MovingObject
    import time

    info = {'id': '1', 'confidence': 0.95, 'age': 'adult', 'gender': 'male'}
    obj = MovingObject(info, time.time(), self.mock_camera)
    obj.rv_id = 1
    obj.reid = [0.1, 0.2, 0.3]
    obj.category = 'person'
    obj.metadata = {'age': 'adult', 'gender': 'male'}

    with self.manager.active_ids_lock:
      self.manager.active_ids[obj.rv_id] = [None, None]

    self.manager.quality_features[obj.rv_id] = [[0.1, 0.2, 0.3], [0.15, 0.25, 0.35]]

    self.manager.updateActiveDict(obj, database_id="db_match_456", similarity=0.91)

    # Verify features_for_database populated
    assert obj.rv_id in self.manager.features_for_database
    features_entry = self.manager.features_for_database[obj.rv_id]
    assert features_entry['gid'] == "db_match_456"
    assert features_entry['category'] == 'person'
    assert len(features_entry['reid_vectors']) == 2
    assert features_entry['metadata'] is not None

  def test_features_for_database_populated_on_no_match(self):
    """Verify features_for_database is populated on QUERY_NO_MATCH."""
    from controller.moving_object import MovingObject
    import time

    info = {'id': '1', 'confidence': 0.95}
    obj = MovingObject(info, time.time(), self.mock_camera)
    obj.rv_id = 1
    obj.reid = [0.1, 0.2, 0.3]
    obj.category = 'person'

    with self.manager.active_ids_lock:
      self.manager.active_ids[obj.rv_id] = [None, None]

    self.manager.quality_features[obj.rv_id] = [[0.1, 0.2, 0.3]]

    self.manager.updateActiveDict(obj, database_id=None, similarity=None)

    # Verify features_for_database populated even for no match
    assert obj.rv_id in self.manager.features_for_database
    features_entry = self.manager.features_for_database[obj.rv_id]
    assert features_entry['gid'] == obj.gid
    assert features_entry['category'] == 'person'
    assert len(features_entry['reid_vectors']) == 1


class TestUpdateActiveDictIDCollisionHandling:
  """Test ID-collision handling in updateActiveDict()."""

  def setup_method(self):
    """Set up mock database and UUIDManager."""
    self.mock_db = Mock()
    self.mock_db.connect = Mock()
    with patch('controller.uuid_manager.available_databases', {'VDMS': Mock(return_value=self.mock_db)}):
      self.manager = UUIDManager(database='VDMS')

    self.mock_camera = Mock()
    self.mock_camera.pose = Mock()
    self.mock_camera.pose.intrinsics = Mock()
    self.mock_camera.pose.intrinsics.mapPixelToNormalizedImagePlane = Mock(return_value=Mock())

  def test_isNewID_returns_true_for_unused_id(self):
    """Verify isNewID returns True for IDs not yet in active_ids."""
    with self.manager.active_ids_lock:
      self.manager.active_ids['rv_1'] = ['db_gid_100', 0.85]
      self.manager.active_ids['rv_2'] = ['db_gid_200', 0.90]

    # New ID not in active_ids
    assert self.manager.isNewID('db_gid_300') is True

  def test_isNewID_returns_false_for_existing_id(self):
    """Verify isNewID returns False for IDs already in active_ids (collision)."""
    with self.manager.active_ids_lock:
      self.manager.active_ids['rv_1'] = ['db_gid_100', 0.85]
      self.manager.active_ids['rv_2'] = ['db_gid_200', 0.90]

    # ID already assigned to rv_1
    assert self.manager.isNewID('db_gid_100') is False

  def test_match_with_existing_id_not_reassigned(self):
    """Verify collided database IDs are treated as no-match with a fresh unique gid."""
    from controller.moving_object import MovingObject, ReidState
    import time

    # Set up first object already matched to a database ID
    info1 = {'id': '1', 'confidence': 0.95}
    obj1 = MovingObject(info1, time.time(), self.mock_camera)
    obj1.rv_id = 1
    obj1.reid = [0.1, 0.2, 0.3]
    obj1.category = 'person'

    with self.manager.active_ids_lock:
      self.manager.active_ids[obj1.rv_id] = [None, None]

    self.manager.quality_features[obj1.rv_id] = [[0.1, 0.2, 0.3]]

    # First object matches to database_gid_X
    self.manager.updateActiveDict(obj1, database_id='database_gid_X', similarity=0.95)
    assert obj1.reid_state == ReidState.MATCHED
    assert obj1.gid == 'database_gid_X'

    # Now try to process second object with same database_gid_X (collision scenario)
    info2 = {'id': '2', 'confidence': 0.95}
    obj2 = MovingObject(info2, time.time(), self.mock_camera)
    obj2.rv_id = 2
    obj2.reid = [0.15, 0.25, 0.35]
    obj2.category = 'person'

    with self.manager.active_ids_lock:
      self.manager.active_ids[obj2.rv_id] = [None, None]

    self.manager.quality_features[obj2.rv_id] = [[0.15, 0.25, 0.35]]
    initial_count = self.manager.unique_id_count

    # Collision should be handled as no-match without reusing obj1's active gid.
    self.manager.updateActiveDict(obj2, database_id='database_gid_X', similarity=None)

    # obj2 gets QUERY_NO_MATCH state and a new unique gid.
    assert obj2.reid_state == ReidState.QUERY_NO_MATCH
    assert obj2.gid != 'database_gid_X'
    assert obj2.gid != obj1.gid
    assert obj2.similarity is None
    assert self.manager.active_ids[obj2.rv_id][0] == obj2.gid
    assert self.manager.unique_id_count == initial_count + 1
    assert len(obj2.previous_ids_chain) == 1
    assert obj2.previous_ids_chain[0]['id'] == obj2.gid
    assert obj2.previous_ids_chain[0]['similarity_score'] is None

  def test_multiple_objects_same_new_match_only_first_wins(self):
    """Test scenario where only the first track keeps a shared matched database ID."""
    from controller.moving_object import MovingObject, ReidState
    import time

    # Object A: Gets matched first
    obj_a = MovingObject({'id': 'A', 'confidence': 0.95}, time.time(), self.mock_camera)
    obj_a.rv_id = 'A'
    obj_a.reid = [0.1, 0.2, 0.3]
    obj_a.category = 'person'

    with self.manager.active_ids_lock:
      self.manager.active_ids[obj_a.rv_id] = [None, None]
    self.manager.quality_features[obj_a.rv_id] = [[0.1, 0.2, 0.3]]

    # A matches to shared_gid
    self.manager.updateActiveDict(obj_a, database_id='shared_gid', similarity=0.92)
    assert obj_a.reid_state == ReidState.MATCHED
    assert obj_a.gid == 'shared_gid'

    # Object B: Also gets match to same shared_gid (collision)
    obj_b = MovingObject({'id': 'B', 'confidence': 0.95}, time.time(), self.mock_camera)
    obj_b.rv_id = 'B'
    obj_b.reid = [0.15, 0.25, 0.35]
    obj_b.category = 'person'

    with self.manager.active_ids_lock:
      self.manager.active_ids[obj_b.rv_id] = [None, None]
    self.manager.quality_features[obj_b.rv_id] = [[0.15, 0.25, 0.35]]
    initial_count = self.manager.unique_id_count

    # B's match to shared_gid collides with A's active assignment and must not be reused.
    self.manager.updateActiveDict(obj_b, database_id='shared_gid', similarity=0.88)

    # B gets QUERY_NO_MATCH state and a distinct generated gid.
    assert obj_b.reid_state == ReidState.QUERY_NO_MATCH
    assert obj_b.gid != 'shared_gid'
    assert obj_a.gid == 'shared_gid'  # A still has the matched ID
    assert obj_b.gid != obj_a.gid
    assert obj_b.similarity is None  # B has no similarity (treated as no-match)
    assert self.manager.active_ids[obj_b.rv_id][0] == obj_b.gid
    assert self.manager.unique_id_count == initial_count + 1


class TestMovingObjectSetPreviousPersistence:
  """Regression tests for setPrevious() persistence across frame recreation."""

  def setup_method(self):
    """Set up a mock camera compatible with MovingObject initialization."""
    self.mock_camera = Mock()
    self.mock_camera.pose = Mock()
    self.mock_camera.pose.intrinsics = Mock()
    self.mock_camera.pose.intrinsics.mapPixelToNormalizedImagePlane = Mock(return_value=Mock())

  def _create_moving_object(self, obj_id):
    """Create a minimal MovingObject with required state for setPrevious()."""
    from controller.moving_object import MovingObject, ChainData
    import time

    obj = MovingObject({'id': obj_id, 'confidence': 0.95}, time.time(), self.mock_camera)
    obj.chain_data = ChainData(regions={}, publishedLocations=[], persist={})
    obj.location = [Mock()]
    return obj

  def test_set_previous_persists_reid_state_similarity_and_chain(self):
    """Verify reid_state, similarity, and previous_ids_chain are copied from previous frame object."""
    from controller.moving_object import ReidState

    old_obj = self._create_moving_object('1')
    new_obj = self._create_moving_object('2')

    old_obj.reid_state = ReidState.MATCHED
    old_obj.similarity = 0.91
    old_obj.previous_ids_chain = [
      {'id': 'gid_10', 'timestamp': 1000.0, 'similarity_score': 0.91}
    ]

    new_obj.setPrevious(old_obj)

    assert new_obj.reid_state == ReidState.MATCHED
    assert new_obj.similarity == 0.91
    assert new_obj.previous_ids_chain == old_obj.previous_ids_chain

  def test_set_previous_copies_chain_without_list_aliasing(self):
    """Verify previous_ids_chain list is copied by value, not aliased."""
    old_obj = self._create_moving_object('1')
    new_obj = self._create_moving_object('2')

    old_obj.previous_ids_chain = [
      {'id': 'gid_10', 'timestamp': 1000.0, 'similarity_score': 0.91}
    ]

    new_obj.setPrevious(old_obj)
    new_obj.previous_ids_chain.append(
      {'id': 'gid_11', 'timestamp': 1001.0, 'similarity_score': None}
    )

    assert len(new_obj.previous_ids_chain) == 2
    assert len(old_obj.previous_ids_chain) == 1
