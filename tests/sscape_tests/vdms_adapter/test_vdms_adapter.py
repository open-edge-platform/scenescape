#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Simplified Unit tests for VDMSDatabase adapter.
Tests the interface contract with AND-only constraint support (>= 0.8 confidence).
These tests can be run inside the controller container where all dependencies are available.
"""

import pytest
import json
import numpy as np
from unittest.mock import Mock, MagicMock, patch

from controller.vdms_adapter import VDMSDatabase, SCHEMA_NAME, DIMENSIONS, K_NEIGHBORS
from controller.reid import ReIDDatabase


class TestVDMSDatabaseInterface:
  """Test that VDMSDatabase implements ReIDDatabase interface."""

  def test_vdms_database_implements_reid_database(self):
    """Verify VDMSDatabase is a subclass of ReIDDatabase."""
    assert issubclass(VDMSDatabase, ReIDDatabase)

  def test_required_methods_exist(self):
    """Verify all required ReIDDatabase methods are implemented."""
    required_methods = ['addSchema', 'addEntry', 'findSchema', 'findMatches']

    with patch('controller.vdms_adapter.vdms.vdms'):
      db = VDMSDatabase()
      for method_name in required_methods:
        assert hasattr(db, method_name), f"Missing required method: {method_name}"
        assert callable(getattr(db, method_name)), f"{method_name} is not callable"


class TestVDMSDatabaseInitialization:
  """Test VDMSDatabase initialization."""

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_initialization_creates_database_instance(self, mock_vdms):
    """Verify VDMS database instance is created during initialization."""
    mock_vdms_instance = MagicMock()
    mock_vdms.return_value = mock_vdms_instance

    db = VDMSDatabase()

    assert db.db is not None
    mock_vdms.assert_called()

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_initialization_with_custom_parameters(self, mock_vdms):
    """Verify VDMS can be initialized with custom schema parameters."""
    custom_set_name = "custom_reid"
    custom_metric = "L2"
    custom_dims = 512

    db = VDMSDatabase(
      set_name=custom_set_name,
      similarity_metric=custom_metric,
      dimensions=custom_dims
    )

    assert db.set_name == custom_set_name
    assert db.similarity_metric == custom_metric
    assert db.dimensions == custom_dims

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_has_threading_lock(self, mock_vdms):
    """Verify thread safety mechanism exists."""
    db = VDMSDatabase()
    assert hasattr(db, 'lock'), "VDMSDatabase must have a lock for thread safety"


class TestAddEntry:
  """Test adding entries to VDMS."""

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_add_entry_requires_standard_fields(self, mock_vdms_class):
    """Verify addEntry includes uuid, rvid, and type in properties."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    test_uuid = "test-uuid-123"
    test_rvid = "rvid-456"
    test_type = "Person"
    test_vectors = [np.random.randn(256).astype(np.float32)]

    db.addEntry(test_uuid, test_rvid, test_type, test_vectors)

    call_args = db.sendQuery.call_args
    query_list = call_args[0][0]
    query = query_list[0]

    assert 'AddDescriptor' in query
    properties = query['AddDescriptor']['properties']
    assert properties['uuid'] == test_uuid
    assert properties['rvid'] == test_rvid
    assert properties['type'] == test_type

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_add_entry_handles_new_metadata_format(self, mock_vdms_class):
    """Verify addEntry extracts label from metadata dict for VDMS constraint matching."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    test_uuid = "test-uuid"
    test_rvid = "rvid"
    test_type = "Person"
    test_vectors = [np.random.randn(256).astype(np.float32)]

    metadata = {
      "gender": {"label": "Female", "model_name": "gender_v2", "confidence": 0.95},
      "age": {"label": 28, "model_name": "age_estimator", "confidence": 0.87}
    }

    db.addEntry(test_uuid, test_rvid, test_type, test_vectors, **metadata)

    call_args = db.sendQuery.call_args
    query_list = call_args[0][0]
    query = query_list[0]
    properties = query['AddDescriptor']['properties']

    assert 'gender' in properties
    assert 'age' in properties

    # Now properties should store only the label values (not JSON)
    # This allows VDMS constraints like gender=['==', 'Female'] to match
    assert properties['gender'] == "Female"
    assert properties['age'] == "28"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_add_entry_converts_vectors_to_bytes(self, mock_vdms_class):
    """Verify addEntry converts numpy vectors to bytes for blob transmission."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{'status': 0}, {'status': 0}], []))

    test_uuid = "test-uuid"
    test_rvid = "rvid"
    test_type = "Person"

    test_vectors = [
      np.random.randn(256).astype(np.float32),
      np.random.randn(256).astype(np.float32)
    ]

    db.addEntry(test_uuid, test_rvid, test_type, test_vectors)

    call_args = db.sendQuery.call_args
    blob = call_args[0][1]

    assert blob is not None
    assert len(blob) == len(test_vectors), "Blob should have one entry per vector"

    for blob_item in blob:
      assert isinstance(blob_item, bytes), "Blob item should be bytes"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_add_entry_handles_multiple_vectors(self, mock_vdms_class):
    """Verify addEntry can handle multiple embeddings per object."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{'status': 0}, {'status': 0}, {'status': 0}], []))

    test_uuid = "test-uuid"
    test_rvid = "rvid"
    test_type = "Person"

    test_vectors = [
      np.random.randn(256).astype(np.float32),
      np.random.randn(256).astype(np.float32),
      np.random.randn(256).astype(np.float32)
    ]

    db.addEntry(test_uuid, test_rvid, test_type, test_vectors)

    call_args = db.sendQuery.call_args
    query_list = call_args[0][0]
    assert len(query_list) == 3, "Should have one query per vector"


class TestFindMatches:
  """Test finding similar entries (2-tier hybrid search)."""

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_find_matches_tier1_filters_by_object_type(self, mock_vdms_class):
    """Verify findMatches always filters by object_type (TIER 1: metadata filtering)."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 1,
      'entities': [{'uuid': 'match-1', '_distance': 0.1}]
    }], []))

    test_vectors = [np.random.randn(256).astype(np.float32)]
    test_type = "Person"

    db.findMatches(test_type, test_vectors)

    call_args = db.sendQuery.call_args
    query_list = call_args[0][0]
    query = query_list[0]

    assert 'FindDescriptor' in query
    constraints = query['FindDescriptor']['constraints']
    assert 'type' in constraints, "TIER 1 must filter by object type"
    assert constraints['type'] == ["==", test_type]

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_find_matches_tier1_applies_high_confidence_constraints(self, mock_vdms_class):
    """Verify findMatches applies only high-confidence metadata filters (TIER 1: metadata filtering)."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 1,
      'entities': [{'uuid': 'match-1', '_distance': 0.1}]
    }], []))

    test_vectors = [np.random.randn(256).astype(np.float32)]
    test_type = "Person"

    # High-confidence metadata constraints (>= 0.8)
    constraints = {
      'gender': {'label': 'Female', 'model_name': 'gender_v2', 'confidence': 0.95},
      'age_range': {'label': 'adult', 'model_name': 'age_v2', 'confidence': 0.88}
    }

    db.findMatches(test_type, test_vectors, **constraints)

    call_args = db.sendQuery.call_args
    query_list = call_args[0][0]
    query = query_list[0]
    query_constraints = query['FindDescriptor']['constraints']

    assert query_constraints['type'] == ["==", test_type]
    assert query_constraints['gender'] == ["==", "Female"], "High-confidence gender should be AND constraint"
    assert query_constraints['age_range'] == ["==", "adult"], "High-confidence age_range should be AND constraint"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_find_matches_tier2_vector_similarity_search(self, mock_vdms_class):
    """Verify findMatches performs vector similarity search (TIER 2: vector matching)."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 0
    }, {
      'status': 0,
      'returned': 0
    }], []))

    test_vectors = [
      np.random.randn(256).astype(np.float32),
      np.random.randn(256).astype(np.float32)
    ]

    db.findMatches("Person", test_vectors)

    call_args = db.sendQuery.call_args
    blob = call_args[0][1]

    assert blob is not None, "TIER 2 requires blob with query vectors"
    assert len(blob) == len(test_vectors), "Blob should have one entry per query vector"

    for blob_item in blob:
      assert isinstance(blob_item, bytes), "TIER 2 requires vectors as bytes"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_find_matches_returns_matched_entities(self, mock_vdms_class):
    """Verify findMatches returns matched entities from VDMS."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    expected_entities = [
      {'uuid': 'match-1', 'rvid': 'rvid-1', '_distance': 0.1},
      {'uuid': 'match-2', 'rvid': 'rvid-2', '_distance': 0.2}
    ]

    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 2,
      'entities': expected_entities
    }], []))

    test_vectors = [np.random.randn(256).astype(np.float32)]
    result = db.findMatches("Person", test_vectors)

    assert result is not None, "findMatches should return results when matches found"
    assert len(result) == 1
    assert result[0] == expected_entities

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_find_matches_handles_no_results(self, mock_vdms_class):
    """Verify findMatches handles case with no matches."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 0
    }], []))

    test_vectors = [np.random.randn(256).astype(np.float32)]
    result = db.findMatches("Person", test_vectors)

    assert result is None or (isinstance(result, list) and len(result) == 0)

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_find_matches_respects_k_neighbors_parameter(self, mock_vdms_class):
    """Verify findMatches respects k_neighbors parameter."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 0
    }], []))

    test_vectors = [np.random.randn(256).astype(np.float32)]
    custom_k = 10

    db.findMatches("Person", test_vectors, k_neighbors=custom_k)

    call_args = db.sendQuery.call_args
    query_list = call_args[0][0]
    query = query_list[0]

    assert query['FindDescriptor']['k_neighbors'] == custom_k


class TestConstraintBuilding:
  """Test constraint building logic for AND-only support."""

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_dict_metadata_high_confidence(self, mock_vdms_class):
    """Verify dict metadata with high confidence (>= 0.8) becomes AND constraint."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    constraints = {
      "gender": {
        "label": "Female",
        "model_name": "gender_v2",
        "confidence": 0.95
      }
    }

    result = db._build_query_constraints("Person", **constraints)

    assert "gender" in result
    assert result["gender"] == ["==", "Female"]

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_dict_metadata_low_confidence(self, mock_vdms_class):
    """Verify dict metadata with low confidence (< 0.8) is ignored (TIER 2 vector similarity)."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    constraints = {
      "age": {
        "label": 25,
        "model_name": "age_estimator",
        "confidence": 0.65
      }
    }

    result = db._build_query_constraints("Person", **constraints)

    assert result == {"type": ["==", "Person"]}, "Low-confidence constraints should be ignored"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_mixed_dict_and_plain_values(self, mock_vdms_class):
    """Verify mixed dict and plain values - only high-confidence dict values are used."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    constraints = {
      "gender": {
        "label": "Male",
        "model_name": "gender_v2",
        "confidence": 0.92
      },
      "color": "blue"
    }

    result = db._build_query_constraints("Person", **constraints)

    assert "gender" in result
    assert result["gender"] == ["==", "Male"]

    assert "color" not in result, "Plain string values are ignored"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_dict_without_confidence(self, mock_vdms_class):
    """Verify dict metadata without confidence field is ignored (TIER 2 vector similarity)."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    constraints = {
      "descriptor": {
        "label": "some_description"
      }
    }

    result = db._build_query_constraints("Person", **constraints)

    assert result == {"type": ["==", "Person"]}, "Dict without confidence should be ignored"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_dict_value_extraction(self, mock_vdms_class):
    """Verify 'label' field is properly extracted from dict metadata."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    constraints = {
      "age": {"label": 28, "model_name": "age", "confidence": 0.88},
      "height": {"label": 5.8, "model_name": "height", "confidence": 0.75},
      "name": {"label": "John", "model_name": "name", "confidence": 0.99}
    }

    result = db._build_query_constraints("Person", **constraints)

    assert result["age"] == ["==", "28"], "High confidence (0.88 >= 0.8) should be AND"
    assert result["name"] == ["==", "John"], "High confidence (0.99 >= 0.8) should be AND"

    assert "height" not in result, "Low confidence (0.75 < 0.8) should be ignored"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_object_type_always_and(self, mock_vdms_class):
    """Verify object_type is always an AND constraint (required field)."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    test_type = "Person"
    constraints = db._build_query_constraints(test_type)

    assert "type" in constraints, "Object type must always be present"
    assert constraints["type"] == ["==", test_type], "Object type must be AND constraint format"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_high_confidence_to_and(self, mock_vdms_class):
    """Verify high-confidence constraints (>= 0.8) become AND constraints."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    high_confidence_constraints = {
      "gender": {"label": "Female", "model_name": "gender_v2", "confidence": 0.95},
      "age_range": {"label": "25-30", "model_name": "age_v2", "confidence": 0.87},
      "color": {"label": "blue", "model_name": "color_v1", "confidence": 0.8}
    }

    constraints = db._build_query_constraints("Person", **high_confidence_constraints)

    assert "gender" in constraints
    assert "age_range" in constraints
    assert "color" in constraints

    assert constraints["gender"] == ["==", "Female"]
    assert constraints["age_range"] == ["==", "25-30"]
    assert constraints["color"] == ["==", "blue"]

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_low_confidence_ignored(self, mock_vdms_class):
    """Verify low-confidence constraints (< 0.8) are ignored."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    low_confidence_constraints = {
      "gender": {"label": "Female", "model_name": "gender", "confidence": 0.75},
      "age_range": {"label": "18-25", "model_name": "age", "confidence": 0.5},
      "color": {"label": "blue", "model_name": "color", "confidence": 0.01}
    }

    constraints = db._build_query_constraints("Person", **low_confidence_constraints)

    assert constraints == {"type": ["==", "Person"]}, "Low-confidence constraints should all be ignored"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_empty_constraints(self, mock_vdms_class):
    """Verify empty constraints dict returns only object_type constraint."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    constraints = db._build_query_constraints("Vehicle")

    assert constraints == {"type": ["==", "Vehicle"]}, \
      "Empty constraints should only have type constraint"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_none_values_ignored(self, mock_vdms_class):
    """Verify None values in constraints are ignored."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    constraints_with_none = {
      "gender": {"label": "Female", "model_name": "gender_v2", "confidence": 0.95},
      "age": None,
      "color": "blue"
    }

    constraints = db._build_query_constraints("Person", **constraints_with_none)

    assert "age" not in constraints, "None values should be ignored"
    assert "gender" in constraints
    assert constraints["gender"] == ["==", "Female"]
    assert "color" not in constraints, "Plain string values should be ignored"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_boundary_confidence_0_8(self, mock_vdms_class):
    """Verify confidence exactly 0.8 is treated as AND constraint (boundary case)."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    boundary_constraints = {
      "attribute_exact": {"label": "test_value", "model_name": "model", "confidence": 0.8}
    }

    constraints = db._build_query_constraints("Person", **boundary_constraints)

    assert "attribute_exact" in constraints
    assert constraints["attribute_exact"] == ["==", "test_value"]


class TestFindMatchesIntegration:
  """Test findMatches integration with constraint building."""

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_find_matches_uses_constraint_builder(self, mock_vdms_class):
    """Verify findMatches delegates to _build_query_constraints."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 0
    }], []))

    test_vectors = [np.random.randn(256).astype(np.float32)]

    db.findMatches("Person", test_vectors, gender={"label": "Female", "model_name": "gender_v2", "confidence": 0.95})

    call_args = db.sendQuery.call_args
    query_list = call_args[0][0]
    query = query_list[0]
    query_constraints = query['FindDescriptor']['constraints']

    assert "gender" in query_constraints
    assert query_constraints["gender"] == ["==", "Female"]


class TestMetadataStorageQueryConsistency:
  """Test that stored metadata matches what is queried (no storage/query mismatch)."""

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_metadata_stored_matches_constraint_query(self, mock_vdms_class):
    """Ensure metadata stored in addEntry matches constraint values in findMatches.

    This prevents the bug where metadata was stored as JSON strings but queried
    as plain strings, causing TIER 1 filtering to fail.

    The contract:
      - addEntry: Extract 'label' from dict metadata, store as plain string
      - findMatches: Use 'label' in constraint, query as plain string
      - Result: Stored value == queried value (they match!)
    """
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    test_uuid = "test-uuid"
    test_rvid = "rvid"
    test_type = "Person"
    test_vectors = [np.random.randn(256).astype(np.float32)]

    # Metadata as it comes from tracker
    metadata_dict = {
      "gender": {"label": "Female", "model_name": "gender_v2", "confidence": 0.95},
      "age": {"label": 28, "model_name": "age_estimator", "confidence": 0.87}
    }

    # STEP 1: Store metadata via addEntry
    db.addEntry(test_uuid, test_rvid, test_type, test_vectors, **metadata_dict)

    call_args_add = db.sendQuery.call_args
    query_list_add = call_args_add[0][0]
    properties_stored = query_list_add[0]['AddDescriptor']['properties']

    # Verify: Labels extracted and stored as plain strings
    assert properties_stored['gender'] == "Female", "Gender label should be stored as plain string"
    assert properties_stored['age'] == "28", "Age label should be stored as plain string"

    # STEP 2: Query with same metadata via findMatches
    db.sendQuery.reset_mock()
    db.sendQuery.return_value = ([{'status': 0, 'returned': 0}], [])

    query_vectors = [np.random.randn(256).astype(np.float32)]
    db.findMatches(test_type, query_vectors, **metadata_dict)

    call_args_find = db.sendQuery.call_args
    query_list_find = call_args_find[0][0]
    query_constraints = query_list_find[0]['FindDescriptor']['constraints']

    # Verify: Constraints use plain string values (matching what was stored)
    assert query_constraints['gender'] == ["==", "Female"], \
      "Query constraint should use plain string 'Female', matching stored value"
    assert query_constraints['age'] == ["==", "28"], \
      "Query constraint should use plain string '28', matching stored value"

    # CRITICAL ASSERTION: Storage format == Query format
    # This ensures VDMS can match: stored 'Female' matches constraint gender='Female'
    assert properties_stored['gender'] == query_constraints['gender'][1], \
      f"MISMATCH: Stored '{properties_stored['gender']}' != Queried '{query_constraints['gender'][1]}'"
    assert properties_stored['age'] == query_constraints['age'][1], \
      f"MISMATCH: Stored '{properties_stored['age']}' != Queried '{query_constraints['age'][1]}'"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_metadata_consistency_multiple_types(self, mock_vdms_class):
    """Verify storage/query consistency across different metadata types."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    # Test various data types in metadata labels
    test_cases = [
      ("gender", "Male", "Male"),
      ("age", 42, "42"),
      ("height", 5.9, "5.9"),
      ("color", "blue", "blue"),
      ("count", 100, "100"),
    ]

    for attr_name, label_value, expected_stored in test_cases:
      db.sendQuery.reset_mock()
      db.sendQuery.return_value = ([{'status': 0}], [])

      metadata = {
        attr_name: {"label": label_value, "model_name": "model", "confidence": 0.9}
      }

      # Store via addEntry
      test_vectors = [np.random.randn(256).astype(np.float32)]
      db.addEntry("uuid", "rvid", "Person", test_vectors, **metadata)

      call_args_add = db.sendQuery.call_args
      properties = call_args_add[0][0][0]['AddDescriptor']['properties']

      # Query via findMatches
      db.sendQuery.reset_mock()
      db.sendQuery.return_value = ([{'status': 0, 'returned': 0}], [])
      db.findMatches("Person", test_vectors, **metadata)

      call_args_find = db.sendQuery.call_args
      constraints = call_args_find[0][0][0]['FindDescriptor']['constraints']

      # Verify consistency for each type
      stored_value = properties[attr_name]
      queried_value = constraints[attr_name][1]

      assert stored_value == expected_stored, \
        f"{attr_name}: Expected stored '{expected_stored}' but got '{stored_value}'"
      assert queried_value == expected_stored, \
        f"{attr_name}: Expected constraint '{expected_stored}' but got '{queried_value}'"
      assert stored_value == queried_value, \
        f"{attr_name}: Storage/Query mismatch - stored='{stored_value}' vs queried='{queried_value}'"
