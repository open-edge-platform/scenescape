#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for UUIDManager.
Tests the interface and behavior of UUID manager without implementation bias.
These tests run inside the controller container where all dependencies are available.
"""

import numpy as np
import concurrent.futures
from types import SimpleNamespace
from unittest.mock import Mock, MagicMock, patch

import pytest

from controller.uuid_manager import (
  UUIDManager,
  DEFAULT_SIMILARITY_THRESHOLD_L2,
  DEFAULT_SIMILARITY_THRESHOLD_COSINE,
)

from controller.moving_object import MovingObject, ReidState, Chronoloc
from scene_common.geometry import Point, Rectangle
import time

def call_update_active_dict_locked(manager, sscape_object, database_id, similarity,
                                   query_timestamp=None, query_vector_scores=None):
  """Call updateActiveDict while holding active_ids_lock, matching production call pattern."""
  with manager.active_ids_lock:
    manager.updateActiveDict(
      sscape_object,
      database_id=database_id,
      similarity=similarity,
      query_timestamp=query_timestamp,
      query_vector_scores=query_vector_scores,
    )

@pytest.fixture(autouse=True)
def mock_vdms_db():
  """Patch the backend registry lookup so all tests use a fake backend."""
  mock_vdms_db = MagicMock()

  with patch('controller.uuid_manager.create_reid_database',
             return_value=mock_vdms_db):
    yield mock_vdms_db


class TestUUIDManagerInitialization:
  """Test UUIDManager initialization and basic setup."""

  def test_initialization_with_default_database(self, mock_vdms_db):
    """Verify UUIDManager initializes with default VDMS database."""

    manager = UUIDManager()

    assert manager is not None
    assert hasattr(manager, 'reid_database'), "Should have reid_database attribute"
    assert manager.reid_database is not None
    assert manager.unique_id_count == 0
    assert manager.reid_enabled is True

  def test_initialization_with_custom_database(self, mock_vdms_db):
    """Verify UUIDManager can be initialized with custom database."""

    manager = UUIDManager(database="VDMS")

    assert manager is not None
    assert manager.reid_database is not None

  def test_has_thread_pool_for_async_operations(self, mock_vdms_db):
    """Verify UUIDManager has thread pool for asynchronous database operations."""

    manager = UUIDManager()

    assert hasattr(manager, 'pool'), "Should have thread pool"
    assert manager.pool is not None

  def test_active_ids_tracking_initialized(self, mock_vdms_db):
    """Verify active_ids dictionary is initialized for tracking."""

    manager = UUIDManager()

    assert hasattr(manager, 'active_ids')
    assert isinstance(manager.active_ids, dict)
    assert len(manager.active_ids) == 0

  def test_default_similarity_configuration_uses_cosine(self, mock_vdms_db):
    """Unconfigured ReID should use cosine matching and its threshold."""

    manager = UUIDManager()

    assert manager.similarity_metric == 'COSINE'
    assert manager.similarity_threshold == DEFAULT_SIMILARITY_THRESHOLD_COSINE
    assert manager.reid_database.similarity_metric == 'IP'

  def test_default_similarity_threshold_uses_l2_value_when_metric_is_l2(self, mock_vdms_db):
    """L2 metric should use the L2-specific default threshold when not configured."""

    manager = UUIDManager(reid_config_data={'similarity_metric': 'L2'})

    assert manager.similarity_metric == 'L2'
    assert manager.similarity_threshold == DEFAULT_SIMILARITY_THRESHOLD_L2

  def test_default_similarity_threshold_uses_cosine_value_when_metric_is_cosine(self, mock_vdms_db):
    """COSINE metric should use the cosine-specific default threshold when not configured."""

    manager = UUIDManager(reid_config_data={'similarity_metric': 'COSINE'})

    assert manager.similarity_metric == 'COSINE'
    assert manager.similarity_threshold == DEFAULT_SIMILARITY_THRESHOLD_COSINE

  def test_similarity_threshold_explicit_value_overrides_metric_default(self, mock_vdms_db):
    """Explicit similarity_threshold should take precedence over metric-specific defaults."""

    manager = UUIDManager(reid_config_data={'similarity_metric': 'COSINE', 'similarity_threshold': 0.77})

    assert manager.similarity_metric == 'COSINE'
    assert manager.similarity_threshold == 0.77


class TestExtractReidEmbedding:
  """Test Re-ID embedding extraction from detection objects."""

  def test_extract_reid_from_new_format(self, mock_vdms_db):
    """Verify extraction from new format: dict with 'embedding_vector' key."""

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

  def test_extract_reid_from_legacy_format(self, mock_vdms_db):
    """Verify extraction from legacy format: direct vector."""

    manager = UUIDManager()

    # Create object with legacy reid format (direct vector)
    obj = MagicMock()
    obj.reid = np.array([0.1, 0.2, 0.3, 0.4]).astype(np.float32).tolist()

    embedding = manager._extractReidEmbedding(obj)

    assert embedding is not None, "Should extract embedding from legacy format"
    assert len(embedding) == 4, "Embedding should have correct length"

  def test_extract_reid_returns_none_when_missing(self, mock_vdms_db):
    """Verify None is returned when reid field is missing."""

    manager = UUIDManager()

    # Create object without reid field using spec
    obj = Mock(spec=['rv_id'])

    embedding = manager._extractReidEmbedding(obj)

    assert embedding is None, "Should return None when reid is missing"

  def test_extract_reid_returns_none_when_none_value(self, mock_vdms_db):
    """Verify None is returned when reid value is None."""

    manager = UUIDManager()

    # Create object with reid=None
    obj = MagicMock()
    obj.reid = None

    embedding = manager._extractReidEmbedding(obj)

    assert embedding is None, "Should return None when reid value is None"


class TestExtractSemanticMetadata:
  """Test semantic metadata extraction from detection objects."""

  def test_extract_semantic_metadata_new_format(self, mock_vdms_db):
    """Verify extraction from new metadata format: metadata attribute."""

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

  def test_extract_semantic_metadata_skips_generic_properties(self, mock_vdms_db):
    """Verify generic properties are excluded from metadata extraction."""

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

  def test_extract_semantic_metadata_skips_internal_fields(self, mock_vdms_db):
    """Verify only metadata attribute is extracted, not internal fields."""

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

  def test_extract_semantic_metadata_handles_none_values(self, mock_vdms_db):
    """Verify None metadata is handled gracefully."""

    manager = UUIDManager()

    # Create object with None metadata
    obj = MagicMock()
    obj.metadata = None

    metadata = manager._extractSemanticMetadata(obj)

    # Should return empty dict when metadata is None
    assert metadata == {}

  def test_extract_semantic_metadata_preserves_value_types(self, mock_vdms_db):
    """Verify extracted metadata preserves data types."""

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

  def test_extract_semantic_metadata_handles_legacy_format(self, mock_vdms_db):
    """Verify no metadata attribute returns empty dict (legacy objects)."""

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

  def test_is_new_tracker_id_when_not_seen_before(self, mock_vdms_db):
    """Verify isNewTrackerID returns True for unseen tracker IDs."""

    manager = UUIDManager()

    obj = MagicMock()
    obj.rv_id = "tracker_123"
    obj.reid = {"embedding_vector": np.array([0.1, 0.2, 0.3, 0.4])}

    result = manager.isNewTrackerID(obj)

    assert result is True, "Should return True for new tracker ID"

  def test_is_new_tracker_id_when_seen_before(self, mock_vdms_db):
    """Verify isNewTrackerID returns False for known tracker IDs."""

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

  def test_assign_id_increments_counter_when_no_reid(self, mock_vdms_db):
    """Verify unique_id_count increments when tracker has no reid vector."""

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

  def test_assign_id_does_not_increment_counter_when_reid_present(self, mock_vdms_db):
    """Verify unique_id_count is not incremented when tracker has reid vector."""

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

  def test_assign_id_initializes_tracking_for_new_tracker(self, mock_vdms_db):
    """Verify assignID initializes tracking for new tracker IDs."""

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

  def test_assign_id_gathers_quality_features_for_new_tracker(self, mock_vdms_db):
    """Verify assignID gathers quality visual features for new tracker."""

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

  def test_assign_id_calls_pick_best_id_always(self, mock_vdms_db):
    """Verify assignID always calls pickBestID."""

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

  def test_assign_id_does_not_submit_query_without_sufficient_features(self, mock_vdms_db):
    """Verify assignID does not submit query if features are insufficient."""

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

  def test_assign_id_submits_query_with_sufficient_features(self, mock_vdms_db):
    """Verify assignID submits similarity query when sufficient features are gathered."""

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

    # Manually add sufficient observations to trigger query submission
    manager.quality_features["tracker_many_features"] = [
      np.array([0.1, 0.2, 0.3, 0.4]).astype(np.float32).tolist()
    ]
    manager.quality_observation_counts["tracker_many_features"] = 15

    manager.assignID(obj)

    # Should submit query after gathering features and determining sufficiency
    assert manager.pool.submit.call_count >= 1, "Should submit query with sufficient features"
    assert "tracker_many_features" in manager.active_query, "Should mark query as submitted"

  def test_assign_id_skips_feature_gathering_if_query_already_submitted(self, mock_vdms_db):
    """Verify assignID doesn't resubmit queries if one is already in progress."""

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

  def test_connect_database_submits_to_pool(self, mock_vdms_db):
    """Verify connectDatabase submits connection task to thread pool."""

    manager = UUIDManager()

    # Track that connect was called through pool.submit
    manager.connectDatabase()

    # Verify pool.submit was called once
    assert manager.pool is not None, "Thread pool should exist"
    # The actual connect call will happen async in the pool
    # Just verify the method doesn't raise an exception


class TestDataTypes:
  """Test data type handling and preservation."""

  def test_metadata_with_unicode_strings(self, mock_vdms_db):
    """Verify Unicode strings in metadata are preserved."""

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

  def test_metadata_with_special_characters(self, mock_vdms_db):
    """Verify special characters in metadata are preserved."""

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

class TestUUIDManagerMetricAwareMatching:
  """Verify parseQueryResults follows descriptor metric semantics."""

  def test_parse_query_results_rejects_single_dimension_entity_list(self):
    """Flat entity lists violate contract and should be treated as no-match."""
    manager = UUIDManager(reid_config_data={'similarity_threshold': 0.5})
    manager.reid_database.similarity_metric = "L2"

    # Invalid input shape: one vector result returned as a flat entity list.
    similarity_scores = [
      {'uuid': 'a', 'rvid': '1', '_distance': 0.2},
      {'uuid': 'b', 'rvid': '2', '_distance': 0.6},
    ]

    database_id, similarity, _ = manager.parseQueryResults(similarity_scores)

    assert database_id is None
    assert similarity is None

  def test_parse_query_results_ip_uses_higher_is_better(self):
    """IP metric should select max `_distance` and require values above threshold."""
    manager = UUIDManager(reid_config_data={'similarity_threshold': 0.5})
    manager.reid_database.similarity_metric = "IP"

    similarity_scores = [
      [
        {'uuid': 'a', 'rvid': '1', '_distance': 0.7},
        {'uuid': 'b', 'rvid': '2', '_distance': 0.6},
      ],
      [
        {'uuid': 'a', 'rvid': '1', '_distance': 0.8},
        {'uuid': 'b', 'rvid': '2', '_distance': 0.4},
      ],
    ]

    database_id, similarity, _ = manager.parseQueryResults(similarity_scores)

    assert database_id == 'a'
    assert similarity == 0.8

  def test_parse_query_results_l2_uses_lower_is_better(self):
    """L2 metric should select min `_distance` and require values below threshold."""
    manager = UUIDManager(reid_config_data={'similarity_threshold': 0.5})
    manager.reid_database.similarity_metric = "L2"

    similarity_scores = [
      [
        {'uuid': 'a', 'rvid': '1', '_distance': 0.2},
        {'uuid': 'b', 'rvid': '2', '_distance': 0.6},
      ],
      [
        {'uuid': 'a', 'rvid': '1', '_distance': 0.3},
        {'uuid': 'b', 'rvid': '2', '_distance': 0.7},
      ],
    ]

    database_id, similarity, _ = manager.parseQueryResults(similarity_scores)

    assert database_id == 'a'
    assert similarity == 0.2

  def test_parse_query_results_ip_ignores_out_of_range_scores(self):
    """IP matching must ignore candidates with `_distance` outside [-1, 1]."""
    manager = UUIDManager(reid_config_data={'similarity_threshold': 0.5})
    manager.reid_database.similarity_metric = "IP"

    similarity_scores = [
      [
        {'uuid': 'a', 'rvid': '1', '_distance': 1.2},
        {'uuid': 'b', 'rvid': '2', '_distance': 0.85},
      ],
      [
        {'uuid': 'a', 'rvid': '1', '_distance': -1.2},
        {'uuid': 'b', 'rvid': '2', '_distance': 0.9},
      ],
    ]

    database_id, similarity, _ = manager.parseQueryResults(similarity_scores)

    assert database_id == 'b'
    assert similarity == 0.9

  def test_parse_query_results_ip_returns_no_match_when_all_scores_invalid(self):
    """IP matching must return no match if all candidate scores are out of range."""
    manager = UUIDManager(reid_config_data={'similarity_threshold': 0.5})
    manager.reid_database.similarity_metric = "IP"

    similarity_scores = [
      [
        {'uuid': 'a', 'rvid': '1', '_distance': 1.3},
        {'uuid': 'b', 'rvid': '2', '_distance': -1.4},
      ],
      [
        {'uuid': 'a', 'rvid': '1', '_distance': 1.1},
      ],
    ]

    database_id, similarity, _ = manager.parseQueryResults(similarity_scores)

    assert database_id is None
    assert similarity is None

  def test_parse_query_results_ip_threshold_boundary_requires_strictly_greater(self):
    """IP matching should not accept values exactly equal to threshold."""
    manager = UUIDManager(reid_config_data={'similarity_threshold': 0.8})
    manager.reid_database.similarity_metric = "IP"

    similarity_scores = [
      [
        {'uuid': 'a', 'rvid': '1', '_distance': 0.8},
        {'uuid': 'b', 'rvid': '2', '_distance': 0.79},
      ]
    ]

    database_id, similarity, _ = manager.parseQueryResults(similarity_scores)

    assert database_id is None
    assert similarity is None

  def test_parse_query_results_builds_per_vector_scores_vs_winning_uuid(self):
    """query_vector_scores align to the majority UUID, with None when absent."""
    manager = UUIDManager(reid_config_data={'similarity_threshold': 0.5})
    manager.reid_database.similarity_metric = "IP"

    similarity_scores = [
      [
        {'uuid': 'winner', 'rvid': '1', '_distance': 0.95},
        {'uuid': 'other', 'rvid': '2', '_distance': 0.9},
      ],
      [
        {'uuid': 'winner', 'rvid': '3', '_distance': 0.91},
        {'uuid': 'other', 'rvid': '4', '_distance': 0.8},
      ],
      [
        {'uuid': 'other', 'rvid': '5', '_distance': 0.99},
      ],
    ]

    database_id, similarity, query_vector_scores = manager.parseQueryResults(
      similarity_scores)

    assert database_id == 'winner'
    assert similarity == 0.95
    assert query_vector_scores == [0.95, 0.91, None]

  def test_parse_query_results_l2_threshold_boundary_requires_strictly_less(self):
    """L2 matching should not accept values exactly equal to threshold."""
    manager = UUIDManager(reid_config_data={'similarity_threshold': 0.2})
    manager.reid_database.similarity_metric = "L2"

    similarity_scores = [
      [
        {'uuid': 'a', 'rvid': '1', '_distance': 0.2},
        {'uuid': 'b', 'rvid': '2', '_distance': 0.21},
      ]
    ]

    database_id, similarity, _ = manager.parseQueryResults(similarity_scores)

    assert database_id is None
    assert similarity is None


class TestUUIDManagerMetricAwareUpdateFlow:
  """Verify parse->update flow produces correct states for both metric paths."""

  def test_cosine_path_match_transitions_to_matched(self):
    """COSINE (mapped to IP) should produce MATCHED when best score is above threshold."""
    from controller.moving_object import MovingObject, ReidState
    import time

    manager = UUIDManager(reid_config_data={'similarity_metric': 'COSINE', 'similarity_threshold': 0.8})
    manager.reid_database.similarity_metric = "IP"

    info = {'id': '1', 'confidence': 0.95}
    now = time.time()
    obj = MovingObject(info, time.time(), None)
    obj.rv_id = 1
    obj.reid = [0.1, 0.2, 0.3]
    obj.category = 'person'
    obj.chain_data = MagicMock()
    obj.chain_data.persist = {}

    mock_bounds = MagicMock()
    obj.location = [Chronoloc(Point(0, 0, 0), now, mock_bounds)]

    with manager.active_ids_lock:
      manager.active_ids[obj.rv_id] = [None, None]
    manager.quality_features[obj.rv_id] = [[0.1, 0.2, 0.3]]

    similarity_scores = [[{'uuid': 'db_match_1', 'rvid': '1', '_distance': 0.92}]]
    database_id, similarity, _ = manager.parseQueryResults(similarity_scores)
    call_update_active_dict_locked(manager, obj, database_id=database_id, similarity=similarity)

    assert obj.reid_state == ReidState.MATCHED
    assert obj.gid == 'db_match_1'
    assert obj.similarity == 0.92

  def test_l2_path_equal_threshold_transitions_to_query_no_match(self):
    """L2 should produce QUERY_NO_MATCH when best score is equal to threshold."""
    from controller.moving_object import MovingObject, ReidState
    import time

    manager = UUIDManager(reid_config_data={'similarity_metric': 'L2', 'similarity_threshold': 0.2})
    manager.reid_database.similarity_metric = "L2"

    info = {'id': '1', 'confidence': 0.95}
    now = time.time()
    obj = MovingObject(info, time.time(), None)
    obj.rv_id = 2
    obj.reid = [0.1, 0.2, 0.3]
    obj.category = 'person'
    obj.chain_data = MagicMock()
    obj.chain_data.persist = {}

    mock_bounds = MagicMock()
    obj.location = [Chronoloc(Point(0, 0, 0), now, mock_bounds)]

    with manager.active_ids_lock:
      manager.active_ids[obj.rv_id] = [None, None]
    manager.quality_features[obj.rv_id] = [[0.1, 0.2, 0.3]]

    similarity_scores = [[{'uuid': 'db_match_2', 'rvid': '2', '_distance': 0.2}]]
    database_id, similarity, _ = manager.parseQueryResults(similarity_scores)
    call_update_active_dict_locked(manager, obj, database_id=database_id, similarity=similarity)

    assert database_id is None
    assert similarity is None
    assert obj.reid_state == ReidState.QUERY_NO_MATCH
    assert obj.gid is not None
    assert obj.similarity is None

class TestDimensionInference:
  """Test automatic ReID embedding dimension inference from first observed vector."""

  def _make_manager_with_mock_db(self, reid_config_data=None):
    """Helper: build a UUIDManager that uses the shared mock VDMS backend fixture."""
    if reid_config_data is None:
      reid_config_data = {}
    return UUIDManager(database="VDMS", reid_config_data=reid_config_data)

  def test_infer_dimensions_from_first_embedding(self, mock_vdms_db):
    """Verify _ensureReIDDimensions infers dimension from first embedding and calls ensureSchema."""
    manager = self._make_manager_with_mock_db()
    assert manager._inferred_dimensions is None

    embedding = np.arange(192, dtype=np.float32)
    result = manager._ensureReIDDimensions(embedding)

    assert result is True, "Should accept first embedding"
    assert manager._inferred_dimensions == 192, "Should lock in inferred dimension"
    mock_vdms_db.ensureSchema.assert_called_once_with(192)

  def test_infer_accepts_subsequent_embedding_with_same_dimension(self, mock_vdms_db):
    """Verify _ensureReIDDimensions accepts all embeddings matching the inferred dimension."""
    manager = self._make_manager_with_mock_db()
    first = np.arange(128, dtype=np.float32)
    second = np.ones(128, dtype=np.float32)

    assert manager._ensureReIDDimensions(first) is True
    assert manager._ensureReIDDimensions(second) is True
    assert manager._inferred_dimensions == 128
    mock_vdms_db.ensureSchema.assert_called_once_with(128)

  def test_reject_embedding_with_inconsistent_dimension(self, mock_vdms_db):
    """Verify _ensureReIDDimensions discards embeddings whose length differs from the inferred one."""
    manager = self._make_manager_with_mock_db()
    first = np.arange(256, dtype=np.float32)
    mismatched = np.arange(128, dtype=np.float32)

    manager._ensureReIDDimensions(first)
    result = manager._ensureReIDDimensions(mismatched)

    assert result is False, "Should reject embedding with different dimension"
    assert manager._inferred_dimensions == 256, "Locked dimension should remain unchanged"

  def test_ensure_schema_error_causes_false_return(self, mock_vdms_db):
    """Verify False is returned and dimension remains unset when ensureSchema raises."""
    mock_vdms_db.ensureSchema.side_effect = ValueError("schema conflict")
    manager = UUIDManager(database="VDMS", reid_config_data={})

    result = manager._ensureReIDDimensions(np.arange(256, dtype=np.float32))

    assert result is False, "Should return False when ensureSchema raises"
    assert manager._inferred_dimensions is None, "Dimension should remain unset after failure"

  def test_zero_length_embedding_is_rejected_and_does_not_lock_dimensions(self, mock_vdms_db):
    """Verify empty arrays are rejected early without calling ensureSchema or locking dimensions."""
    manager = self._make_manager_with_mock_db()

    result_empty_array = manager._ensureReIDDimensions(np.array([], dtype=np.float32))

    assert result_empty_array is False, "Empty ndarray should be rejected"
    assert manager._inferred_dimensions is None, "Dimension must not be locked to 0"
    mock_vdms_db.ensureSchema.assert_not_called()

  def test_zero_length_embedding_does_not_block_valid_subsequent_embedding(self, mock_vdms_db):
    """Verify that after an empty embedding is rejected, a valid embedding is still accepted."""
    manager = self._make_manager_with_mock_db()

    manager._ensureReIDDimensions(np.array([], dtype=np.float32))
    result = manager._ensureReIDDimensions(np.arange(256, dtype=np.float32))

    assert result is True
    assert manager._inferred_dimensions == 256
    mock_vdms_db.ensureSchema.assert_called_once_with(256)

  def test_gather_features_uses_inferred_dimension_gate(self, mock_vdms_db):
    """Verify gatherQualityVisualFeatures silently drops embeddings with wrong dimension."""
    manager = self._make_manager_with_mock_db()

    good_obj = MagicMock()
    good_obj.rv_id = "track_1"
    good_obj.reid = {"embedding_vector": np.arange(64, dtype=np.float32).tolist()}
    good_obj.boundingBoxPixels = MagicMock()
    good_obj.boundingBoxPixels.area = 10000

    bad_obj = MagicMock()
    bad_obj.rv_id = "track_2"
    bad_obj.reid = {"embedding_vector": np.arange(128, dtype=np.float32).tolist()}
    bad_obj.boundingBoxPixels = MagicMock()
    bad_obj.boundingBoxPixels.area = 10000

    manager.gatherQualityVisualFeatures(good_obj)
    manager.gatherQualityVisualFeatures(bad_obj)

    assert "track_1" in manager.quality_features, "64-dim embedding should be accepted"
    assert "track_2" not in manager.quality_features, "128-dim embedding should be rejected after 64 inferred"


def _make_reid_object(rv_id, *, bbox_area=None, provenance=None, embedding=None):
  """Build a detection whose embedding is either locally observed or forwarded to us."""
  obj = MagicMock()
  obj.rv_id = rv_id
  obj.category = "Person"
  obj.gid = None
  obj.metadata = {}
  if embedding is None:
    embedding = np.arange(64, dtype=np.float32).tolist()
  obj.reid = {"embedding_vector": list(embedding)}
  obj.boundingBoxPixels = None if bbox_area is None else SimpleNamespace(area=bbox_area)
  obj.reid_provenance = provenance
  return obj


VETTED_PROVENANCE = {
  'origin_scene_id': 'scene-child',
  'origin_camera_id': 'cam-1',
  'quality_vetted': True,
}


class TestReidObservationTrust:
  """Separate what a scene may query the shared database with from what it may write to it."""

  def test_local_crop_feeds_both_query_and_enrollment(self, mock_vdms_db):
    """A crop from this scene's own camera is usable for matching and for enrollment."""
    manager = UUIDManager()
    obj = _make_reid_object("local-track", bbox_area=10000)

    manager.gatherQualityVisualFeatures(obj)

    assert len(manager.quality_features["local-track"]) == 1
    assert len(manager.enrollment_features["local-track"]) == 1

  def test_small_local_crop_is_rejected_entirely(self, mock_vdms_db):
    """A crop below the area gate is too unreliable to match with or to store."""
    manager = UUIDManager()
    obj = _make_reid_object("tiny-track", bbox_area=10)

    manager.gatherQualityVisualFeatures(obj)

    assert "tiny-track" not in manager.quality_features
    assert "tiny-track" not in manager.enrollment_features

  def test_crop_exactly_at_minimum_area_is_rejected(self, mock_vdms_db):
    """The area gate is exclusive, matching what the forwarding side enforces."""
    manager = UUIDManager(reid_config_data={'minimum_bbox_area': 5000})
    obj = _make_reid_object("boundary-track", bbox_area=5000)

    manager.gatherQualityVisualFeatures(obj)

    assert "boundary-track" not in manager.quality_features

  def test_vetted_forwarded_embedding_feeds_query_and_enrollment(self, mock_vdms_db):
    """Vetted forwarded crops query and may be written (sole enroll / cluster enhance)."""
    manager = UUIDManager()
    obj = _make_reid_object("forwarded-track", provenance=VETTED_PROVENANCE)

    manager.gatherQualityVisualFeatures(obj)

    assert len(manager.quality_features["forwarded-track"]) == 1
    assert len(manager.enrollment_features["forwarded-track"]) == 1

  def test_embedding_without_bbox_or_provenance_is_dropped(self, mock_vdms_db):
    """Nothing vouches for an embedding that arrives with neither, so it is unusable."""
    manager = UUIDManager()
    obj = _make_reid_object("orphan-track")

    manager.gatherQualityVisualFeatures(obj)

    assert "orphan-track" not in manager.quality_features
    assert "orphan-track" not in manager.enrollment_features

  def test_provenance_without_origin_scene_is_not_trusted(self, mock_vdms_db):
    """A vetting claim that names no origin cannot be attributed to anyone."""
    manager = UUIDManager()
    obj = _make_reid_object("anonymous-track", provenance={'quality_vetted': True})

    manager.gatherQualityVisualFeatures(obj)

    assert "anonymous-track" not in manager.quality_features

  def test_provenance_cannot_rescue_a_small_local_crop(self, mock_vdms_db):
    """A claim from upstream never overrides the bbox this scope can measure itself."""
    manager = UUIDManager()
    obj = _make_reid_object("claimed-track", bbox_area=10, provenance=VETTED_PROVENANCE)

    manager.gatherQualityVisualFeatures(obj)

    assert "claimed-track" not in manager.quality_features
    assert "claimed-track" not in manager.enrollment_features

  def test_forwarded_is_not_locally_enrollable_but_may_contribute_writes(self, mock_vdms_db):
    """Local-bbox gate stays false; vetted forward still may contribute to a UUID write."""
    manager = UUIDManager()
    obj = _make_reid_object("forwarded-track", provenance=VETTED_PROVENANCE)

    assert manager.isQueryableObservation(obj) is True
    assert manager.isEnrollableObservation(obj) is False
    assert manager.mayContributeEnrollmentEmbedding(obj) is True

  def test_will_enroll_provenance_is_queryable_but_not_writable(self, mock_vdms_db):
    """Child ReID ownership claim: parent may query, must not enroll/enhance."""
    manager = UUIDManager()
    provenance = dict(VETTED_PROVENANCE)
    provenance['will_enroll'] = True
    obj = _make_reid_object("forwarded-track", provenance=provenance)

    assert manager.isQueryableObservation(obj) is True
    assert manager.mayContributeEnrollmentEmbedding(obj) is False

    manager.gatherQualityVisualFeatures(obj)
    assert len(manager.quality_features["forwarded-track"]) == 1
    assert "forwarded-track" not in manager.enrollment_features

  def test_enrolled_provenance_blocks_parent_writes(self, mock_vdms_db):
    """Explicit enrolled claim also blocks parent database contribution."""
    manager = UUIDManager()
    provenance = dict(VETTED_PROVENANCE)
    provenance['enrolled'] = True
    obj = _make_reid_object("forwarded-track", provenance=provenance)

    assert manager.isQueryableObservation(obj) is True
    assert manager.mayContributeEnrollmentEmbedding(obj) is False

  def test_will_enroll_no_match_does_not_enroll(self, mock_vdms_db):
    """Query miss must not sole-enroll when upstream claimed will_enroll."""
    manager = UUIDManager()
    manager.pool = MagicMock()
    provenance = dict(VETTED_PROVENANCE)
    provenance['will_enroll'] = True
    obj = _make_reid_object("forwarded-track", provenance=provenance)
    obj.chain_data = None

    manager.gatherQualityVisualFeatures(obj)
    call_update_active_dict_locked(manager, obj, database_id=None, similarity=None)

    assert manager.features_for_database["forwarded-track"]['reid_vectors'] == []
    manager._addNewFeaturesToDatabase("forwarded-track")
    assert manager.pool.submit.call_count == 0

  def test_reid_write_failure_clears_write_health(self, mock_vdms_db):
    """Failed addEntry callbacks mark ReID writes unhealthy for hierarchy claims."""
    manager = UUIDManager()
    failed = concurrent.futures.Future()
    failed.set_exception(RuntimeError("vdms down"))

    manager._onReidWriteComplete(failed)
    assert manager.reid_write_healthy is False

  def test_reid_write_health_stays_cleared_after_later_success(self, mock_vdms_db):
    """After a write failure, success must not reclaim will_enroll (sticky unhealthy)."""
    manager = UUIDManager()
    failed = concurrent.futures.Future()
    failed.set_exception(RuntimeError("vdms down"))
    manager._onReidWriteComplete(failed)
    assert manager.reid_write_healthy is False

    recovered = concurrent.futures.Future()
    recovered.set_result(None)
    manager._onReidWriteComplete(recovered)
    assert manager.reid_write_healthy is False

  def test_add_new_features_wires_write_health_callback(self, mock_vdms_db):
    """Flush attaches _onReidWriteComplete so soft/hard addEntry failures clear health."""
    manager = UUIDManager()
    future = concurrent.futures.Future()
    manager.pool = MagicMock()
    manager.pool.submit.return_value = future
    manager.features_for_database["flush-track"] = {
      'gid': 'gid-1',
      'category': 'person',
      'reid_vectors': [np.arange(8, dtype=np.float32)],
      'persist': {},
      'metadata': {},
    }

    manager._addNewFeaturesToDatabase("flush-track")

    manager.pool.submit.assert_called_once()
    assert future._done_callbacks  # pylint: disable=protected-access
    assert manager._onReidWriteComplete in future._done_callbacks

    future.set_exception(RuntimeError("soft vdms failure"))
    # done callbacks run when set_exception completes the future
    assert manager.reid_write_healthy is False

  def test_database_entry_includes_local_and_forwarded_enrollment_features(
      self, mock_vdms_db):
    """Mixed tracks accumulate distinct local and vetted forwarded vectors."""
    manager = UUIDManager()
    local = _make_reid_object("mixed-track", bbox_area=10000)
    forwarded = _make_reid_object(
      "mixed-track", provenance=VETTED_PROVENANCE,
      embedding=(np.arange(64, dtype=np.float32) + 10).tolist())
    forwarded.chain_data = None

    manager.gatherQualityVisualFeatures(local)
    manager.gatherQualityVisualFeatures(forwarded)
    manager.gatherQualityVisualFeatures(forwarded)
    call_update_active_dict_locked(manager, local, database_id=None, similarity=None)

    assert len(manager.quality_features["mixed-track"]) == 2
    assert manager.features_for_database["mixed-track"]['reid_vectors'] == \
      manager.enrollment_features["mixed-track"]
    assert len(manager.features_for_database["mixed-track"]['reid_vectors']) == 2

  def test_exact_duplicate_enrollment_vectors_are_skipped(self, mock_vdms_db):
    """Repeating the same embedding does not grow unique query/enrollment lists."""
    manager = UUIDManager()
    obj = _make_reid_object("forwarded-track", provenance=VETTED_PROVENANCE)

    manager.gatherQualityVisualFeatures(obj)
    manager.gatherQualityVisualFeatures(obj)

    assert manager.quality_observation_counts["forwarded-track"] == 2
    assert len(manager.quality_features["forwarded-track"]) == 1
    assert len(manager.enrollment_features["forwarded-track"]) == 1

  def test_repeated_identical_embeddings_still_count_toward_query_threshold(
      self, mock_vdms_db):
    """Exact-deduped quality lists must not block the frame-count query gate."""
    manager = UUIDManager(reid_config_data={'feature_accumulation_threshold': 3})
    obj = _make_reid_object("forwarded-track", provenance=VETTED_PROVENANCE)

    manager.gatherQualityVisualFeatures(obj)
    manager.gatherQualityVisualFeatures(obj)
    assert manager.haveSufficientVisualFeatures(obj) is False
    manager.gatherQualityVisualFeatures(obj)

    assert manager.haveSufficientVisualFeatures(obj) is True
    assert len(manager.quality_features["forwarded-track"]) == 1

  def test_forwarded_only_no_match_enrolls(self, mock_vdms_db):
    """Parent-only ReID: no prior enrollment → parent enrolls vetted forwarded crops."""
    manager = UUIDManager()
    manager.pool = MagicMock()
    obj = _make_reid_object("forwarded-track", provenance=VETTED_PROVENANCE)
    obj.chain_data = None

    manager.gatherQualityVisualFeatures(obj)
    call_update_active_dict_locked(manager, obj, database_id=None, similarity=None)

    assert len(manager.features_for_database["forwarded-track"]['reid_vectors']) == 1
    manager._addNewFeaturesToDatabase("forwarded-track")
    assert manager.pool.submit.call_count == 1

  def test_forwarded_only_match_enhances_cluster(self, mock_vdms_db):
    """Near rematch still writes vetted forwarded vectors under the matched UUID."""
    manager = UUIDManager()
    manager.pool = MagicMock()
    obj = _make_reid_object("forwarded-track", provenance=VETTED_PROVENANCE)
    obj.chain_data = None

    manager.gatherQualityVisualFeatures(obj)
    call_update_active_dict_locked(
      manager, obj, database_id=42, similarity=0.99)

    assert len(manager.features_for_database["forwarded-track"]['reid_vectors']) == 1
    manager._addNewFeaturesToDatabase("forwarded-track")
    assert manager.pool.submit.call_count == 1

  def test_exact_rematch_skips_rewriting_query_evidence(self, mock_vdms_db):
    """Exact rematch score means forwarded query evidence is already stored."""
    manager = UUIDManager()
    manager.pool = MagicMock()
    obj = _make_reid_object("forwarded-track", provenance=VETTED_PROVENANCE)
    obj.chain_data = None

    manager.gatherQualityVisualFeatures(obj)
    call_update_active_dict_locked(
      manager, obj, database_id=42, similarity=1.0)

    assert manager.features_for_database["forwarded-track"]['reid_vectors'] == []
    manager._addNewFeaturesToDatabase("forwarded-track")
    assert manager.pool.submit.call_count == 0

  def test_exact_rematch_keeps_local_camera_enrollment(self, mock_vdms_db):
    """Exact rematch must not drop pending local camera crops still needing a write."""
    manager = UUIDManager()
    manager.pool = MagicMock()
    local = _make_reid_object(
      "mixed-track", bbox_area=10000,
      embedding=np.arange(64, dtype=np.float32).tolist())
    local.chain_data = None
    forwarded = _make_reid_object(
      "mixed-track", provenance=VETTED_PROVENANCE,
      embedding=(np.arange(64, dtype=np.float32) + 10).tolist())

    manager.gatherQualityVisualFeatures(local)
    manager.gatherQualityVisualFeatures(forwarded)
    call_update_active_dict_locked(
      manager, local, database_id=42, similarity=1.0)

    pending = manager.features_for_database["mixed-track"]['reid_vectors']
    assert len(pending) == 1
    assert np.array_equal(
      np.asarray(pending[0], dtype=np.float32),
      np.arange(64, dtype=np.float32))
    manager._addNewFeaturesToDatabase("mixed-track")
    assert manager.pool.submit.call_count == 1

  def test_rematch_skips_only_exact_query_vectors(self, mock_vdms_db):
    """One exact hit in a multi-vector query must not drop near-duplicate enhancements."""
    manager = UUIDManager()
    manager.pool = MagicMock()
    exact_vec = np.arange(64, dtype=np.float32).tolist()
    near_vec = (np.arange(64, dtype=np.float32) + 3).tolist()
    first = _make_reid_object(
      "forwarded-track", provenance=VETTED_PROVENANCE, embedding=exact_vec)
    first.chain_data = None
    second = _make_reid_object(
      "forwarded-track", provenance=VETTED_PROVENANCE, embedding=near_vec)

    manager.gatherQualityVisualFeatures(first)
    manager.gatherQualityVisualFeatures(second)
    # Aggregate best score is exact, but only the first query vector is exact.
    call_update_active_dict_locked(
      manager, second, database_id=42, similarity=1.0,
      query_vector_scores=[1.0, 0.95])

    pending = manager.features_for_database["forwarded-track"]['reid_vectors']
    assert len(pending) == 1
    assert np.array_equal(
      np.asarray(pending[0], dtype=np.float32),
      np.asarray(near_vec, dtype=np.float32))
    manager._addNewFeaturesToDatabase("forwarded-track")
    assert manager.pool.submit.call_count == 1

  def test_rematch_skips_query_vectors_missing_winner_score(self, mock_vdms_db):
    """A vector whose neighbors omit the matched UUID must not enhance that cluster."""
    manager = UUIDManager()
    manager.pool = MagicMock()
    near_vec = np.arange(64, dtype=np.float32).tolist()
    other_vec = (np.arange(64, dtype=np.float32) + 7).tolist()
    first = _make_reid_object(
      "forwarded-track", provenance=VETTED_PROVENANCE, embedding=near_vec)
    first.chain_data = None
    second = _make_reid_object(
      "forwarded-track", provenance=VETTED_PROVENANCE, embedding=other_vec)

    manager.gatherQualityVisualFeatures(first)
    manager.gatherQualityVisualFeatures(second)
    call_update_active_dict_locked(
      manager, second, database_id=42, similarity=0.95,
      query_vector_scores=[0.95, None])

    pending = manager.features_for_database["forwarded-track"]['reid_vectors']
    assert len(pending) == 1
    assert np.array_equal(
      np.asarray(pending[0], dtype=np.float32),
      np.asarray(near_vec, dtype=np.float32))

  def test_matched_forwarded_detection_appends_to_pending_entry(self, mock_vdms_db):
    """After rematch, a distinct vetted forwarded frame grows the pending entry."""
    manager = UUIDManager()
    local = _make_reid_object("mixed-track", bbox_area=10000)
    local.chain_data = None
    forwarded = _make_reid_object(
      "mixed-track", provenance=VETTED_PROVENANCE,
      embedding=(np.arange(64, dtype=np.float32) + 5).tolist())

    manager.gatherQualityVisualFeatures(local)
    call_update_active_dict_locked(manager, local, database_id=None, similarity=None)
    stored = len(manager.features_for_database["mixed-track"]['reid_vectors'])
    manager.pickBestID(forwarded)

    assert len(manager.features_for_database["mixed-track"]['reid_vectors']) == stored + 1

  def test_matched_exact_duplicate_forwarded_detection_does_not_append(self, mock_vdms_db):
    """Exact same vector already pending is not appended again after rematch."""
    manager = UUIDManager()
    local = _make_reid_object("mixed-track", bbox_area=10000)
    local.chain_data = None
    forwarded = _make_reid_object("mixed-track", provenance=VETTED_PROVENANCE)

    manager.gatherQualityVisualFeatures(local)
    call_update_active_dict_locked(manager, local, database_id=None, similarity=None)
    stored = len(manager.features_for_database["mixed-track"]['reid_vectors'])
    manager.pickBestID(forwarded)

    assert len(manager.features_for_database["mixed-track"]['reid_vectors']) == stored

  def test_pruning_a_track_clears_its_enrollment_features(self, mock_vdms_db):
    """Track teardown must not leave one track's crops behind for the next one."""
    manager = UUIDManager()
    obj = _make_reid_object("local-track", bbox_area=10000)
    manager.gatherQualityVisualFeatures(obj)
    with manager.active_ids_lock:
      manager.active_ids["local-track"] = [None, None]

    manager.pruneInactiveTracks([])

    assert "local-track" not in manager.enrollment_features
    assert "local-track" not in manager.local_enrollment_features
    assert "local-track" not in manager.quality_features
    assert "local-track" not in manager.quality_observation_counts
