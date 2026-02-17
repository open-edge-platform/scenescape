#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for VDMSDatabase adapter.
Tests the interface contract without relying on implementation details.
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
    # Methods that must be implemented for ReIDDatabase interface
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

    # Verify database was instantiated
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

    # Extract the query - sendQuery receives a list of queries
    call_args = db.sendQuery.call_args
    query_list = call_args[0][0]
    query = query_list[0]

    # Verify required fields are in properties
    assert 'AddDescriptor' in query
    properties = query['AddDescriptor']['properties']
    assert properties['uuid'] == test_uuid
    assert properties['rvid'] == test_rvid
    assert properties['type'] == test_type

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_add_entry_handles_new_metadata_format(self, mock_vdms_class):
    """Verify addEntry serializes new metadata format (dict with value/model_name/confidence)."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    test_uuid = "test-uuid"
    test_rvid = "rvid"
    test_type = "Person"
    test_vectors = [np.random.randn(256).astype(np.float32)]

    # New metadata format with model_name and confidence
    metadata = {
      "gender": {"value": "Female", "model_name": "gender_v2", "confidence": 0.95},
      "age": {"value": 28, "model_name": "age_estimator", "confidence": 0.87}
    }

    db.addEntry(test_uuid, test_rvid, test_type, test_vectors, **metadata)

    # Extract the query - sendQuery receives a list of queries
    call_args = db.sendQuery.call_args
    query_list = call_args[0][0]
    query = query_list[0]
    properties = query['AddDescriptor']['properties']

    # Verify metadata is serialized to JSON
    assert 'gender' in properties
    assert 'age' in properties

    # Verify it's a JSON string (not a dict)
    gender_data = json.loads(properties['gender'])
    assert gender_data['value'] == "Female"
    assert gender_data['model_name'] == "gender_v2"
    assert gender_data['confidence'] == 0.95

    age_data = json.loads(properties['age'])
    assert age_data['value'] == 28

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

    # Create test vectors
    test_vectors = [
      np.random.randn(256).astype(np.float32),
      np.random.randn(256).astype(np.float32)
    ]

    db.addEntry(test_uuid, test_rvid, test_type, test_vectors)

    # Extract the blob
    call_args = db.sendQuery.call_args
    blob = call_args[0][1]

    # Verify blob is created for each vector
    assert blob is not None
    assert len(blob) == len(test_vectors), "Blob should have one entry per vector"

    # Verify blob items are bytes (flat list format for VDMS API)
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

    # Multiple vectors from different detection models
    test_vectors = [
      np.random.randn(256).astype(np.float32),
      np.random.randn(256).astype(np.float32),
      np.random.randn(256).astype(np.float32)
    ]

    db.addEntry(test_uuid, test_rvid, test_type, test_vectors)

    # Verify sendQuery was called with multiple queries (one per vector)
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

    # Extract the query - sendQuery receives a list of queries
    call_args = db.sendQuery.call_args
    query_list = call_args[0][0]
    query = query_list[0]

    # Verify TIER 1: constraints include object_type filter
    assert 'FindDescriptor' in query
    constraints = query['FindDescriptor']['constraints']
    assert 'type' in constraints, "TIER 1 must filter by object type"
    assert constraints['type'] == ["==", test_type]

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_find_matches_tier1_applies_additional_constraints(self, mock_vdms_class):
    """Verify findMatches applies additional metadata filters (TIER 1: metadata filtering)."""
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

    # Additional constraints for semantic metadata (non-numeric strings go to OR array)
    constraints = {
      'gender': 'Female',
      'age_range': 'adult'
    }

    db.findMatches(test_type, test_vectors, **constraints)

    # Extract the query - sendQuery receives a list of queries
    call_args = db.sendQuery.call_args
    query_list = call_args[0][0]
    query = query_list[0]
    query_constraints = query['FindDescriptor']['constraints']

    # Verify TIER 1 constraints are applied
    # Type is always AND constraint
    assert query_constraints['type'] == ["==", test_type]

    # Non-numeric string constraints go to OR array (flexible matching)
    assert 'or' in query_constraints, "String constraints should be in OR array"
    or_array = query_constraints['or']
    or_keys = [list(item.keys())[0] for item in or_array]
    assert 'gender' in or_keys, "gender should be in OR array"
    assert 'age_range' in or_keys, "age_range should be in OR array"

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

    # Extract the blob (used for TIER 2)
    call_args = db.sendQuery.call_args
    blob = call_args[0][1]

    # Verify TIER 2: blob is created for each vector (for similarity search)
    assert blob is not None, "TIER 2 requires blob with query vectors"
    assert len(blob) == len(test_vectors), "Blob should have one entry per query vector"

    # Verify blob items are bytes for vector similarity (flat list format)
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

    # Verify result contains the entities
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

    # Should handle gracefully when no results
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

    # Extract the query - sendQuery receives a list of queries
    call_args = db.sendQuery.call_args
    query_list = call_args[0][0]
    query = query_list[0]

    # Verify k_neighbors is set correctly
    assert query['FindDescriptor']['k_neighbors'] == custom_k, \
      "k_neighbors parameter should control number of results returned"


class TestConstraintBuilding:
  """Test constraint building logic for AND/OR routing."""

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_dict_metadata_high_confidence(self, mock_vdms_class):
    """Verify dict metadata with high confidence (>= 0.8) becomes AND constraint."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    # Dict metadata with high confidence
    constraints = {
      "gender": {
        "value": "Female",
        "model_name": "gender_v2",
        "confidence": 0.95
      }
    }

    result = db._build_query_constraints("Person", **constraints)

    # Verify dict is extracted and high-confidence becomes AND
    assert "gender" in result
    assert result["gender"] == ["==", "Female"]
    assert "or" not in result or len(result.get("or", [])) == 0

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_dict_metadata_low_confidence(self, mock_vdms_class):
    """Verify dict metadata with low confidence (< 0.8) becomes OR constraint."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    # Dict metadata with low confidence
    constraints = {
      "age": {
        "value": 25,
        "model_name": "age_estimator",
        "confidence": 0.65
      }
    }

    result = db._build_query_constraints("Person", **constraints)

    # Verify dict is extracted and low-confidence becomes OR
    assert "or" in result
    or_keys = [list(item.keys())[0] for item in result["or"]]
    assert "age" in or_keys

    # Verify value is extracted correctly
    age_constraint = next((item for item in result["or"] if "age" in item), {})
    assert age_constraint.get("age") == ["==", "25"]

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_mixed_dict_and_plain_values(self, mock_vdms_class):
    """Verify mixed dict and plain values are handled correctly."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    # Mix of dict metadata and plain values
    constraints = {
      "gender": {
        "value": "Male",
        "model_name": "gender_v2",
        "confidence": 0.92
      },
      "color": "blue"  # Plain string
    }

    result = db._build_query_constraints("Person", **constraints)

    # Dict with high confidence should be AND
    assert "gender" in result
    assert result["gender"] == ["==", "Male"]

    # Plain string should be OR
    assert "or" in result
    or_keys = [list(item.keys())[0] for item in result["or"]]
    assert "color" in or_keys

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_dict_without_confidence(self, mock_vdms_class):
    """Verify dict metadata without confidence field is treated as OR."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    # Dict without confidence field (legacy or partial format)
    constraints = {
      "descriptor": {
        "value": "some_description"
      }
    }

    result = db._build_query_constraints("Person", **constraints)

    # Dict without confidence should be OR (flexible matching)
    assert "or" in result
    or_keys = [list(item.keys())[0] for item in result["or"]]
    assert "descriptor" in or_keys

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_dict_value_extraction(self, mock_vdms_class):
    """Verify 'value' field is properly extracted from dict metadata."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    # Dict with various value types
    constraints = {
      "age": {"value": 28, "model_name": "age", "confidence": 0.88},
      "height": {"value": 5.8, "model_name": "height", "confidence": 0.75},
      "name": {"value": "John", "model_name": "name", "confidence": 0.99}
    }

    result = db._build_query_constraints("Person", **constraints)

    # Verify values are extracted correctly
    assert result["age"] == ["==", "28"]  # High confidence AND
    assert result["name"] == ["==", "John"]  # High confidence AND

    # Low confidence in OR
    assert "or" in result
    or_items = result["or"]
    height_constraint = next((item for item in or_items if "height" in item), {})
    assert height_constraint.get("height") == ["==", "5.8"]
    """Verify object_type is always an AND constraint (required field)."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    test_type = "Person"
    constraints = db._build_query_constraints(test_type)

    # Verify type is always present and is AND constraint
    assert "type" in constraints, "Object type must always be present"
    assert constraints["type"] == ["==", test_type], "Object type must be AND constraint format"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_high_confidence_to_and(self, mock_vdms_class):
    """Verify high-confidence constraints (>= 0.8) become AND constraints."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    # High confidence values that should become AND constraints
    high_confidence_constraints = {
      "gender": 0.95,      # >= 0.8
      "age_range": 0.87,   # >= 0.8
      "color": 0.8         # Exactly 0.8
    }

    constraints = db._build_query_constraints("Person", **high_confidence_constraints)

    # Verify high-confidence values are direct AND constraints
    assert "gender" in constraints, "High-confidence gender should be in constraints"
    assert "age_range" in constraints, "High-confidence age_range should be in constraints"
    assert "color" in constraints, "Exactly 0.8 should be treated as AND constraint"

    # Verify they are AND format (not in "or" array)
    assert constraints["gender"] == ["==", "0.95"]
    assert constraints["age_range"] == ["==", "0.87"]
    assert constraints["color"] == ["==", "0.8"]

    # Verify "or" is not present or is empty
    assert "or" not in constraints or len(constraints.get("or", [])) == 0, \
      "No OR constraints should exist for high-confidence values"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_low_confidence_to_or(self, mock_vdms_class):
    """Verify low-confidence constraints (< 0.8) become OR constraints."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    # Low confidence values that should become OR constraints
    low_confidence_constraints = {
      "gender": 0.75,      # < 0.8
      "age_range": 0.5,    # < 0.8
      "color": 0.01        # < 0.8
    }

    constraints = db._build_query_constraints("Person", **low_confidence_constraints)

    # Verify type is AND constraint
    assert constraints["type"] == ["==", "Person"]

    # Verify low-confidence values are NOT direct AND constraints
    assert "gender" not in constraints or constraints["gender"] == ["==", "0.75"]  # Might be duplicated
    assert "age_range" not in constraints or constraints["age_range"] == ["==", "0.5"]

    # Verify "or" constraints exist
    assert "or" in constraints, "OR constraints should exist for low-confidence values"

    or_constraints = constraints["or"]
    assert len(or_constraints) >= 3, "Should have at least 3 OR constraints"

    # Verify each low-confidence value is in or array
    or_keys = [list(oc.keys())[0] for oc in or_constraints]
    assert "gender" in or_keys
    assert "age_range" in or_keys
    assert "color" in or_keys

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_string_values_to_or(self, mock_vdms_class):
    """Verify non-numeric (string) values become OR constraints."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    # String (non-numeric) values should become OR constraints
    string_constraints = {
      "gender": "Female",
      "clothing_color": "red",
      "vehicle_make": "Toyota"
    }

    constraints = db._build_query_constraints("Person", **string_constraints)

    # Verify type is AND constraint
    assert constraints["type"] == ["==", "Person"]

    # Verify string values are in "or" constraints
    assert "or" in constraints, "OR constraints should exist for non-numeric values"

    or_constraints = constraints["or"]
    or_keys = [list(oc.keys())[0] for oc in or_constraints]

    assert "gender" in or_keys
    assert "clothing_color" in or_keys
    assert "vehicle_make" in or_keys

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_mixed_confidence_levels(self, mock_vdms_class):
    """Verify mixed high and low confidence constraints are properly separated."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    # Mix of high confidence (AND), low confidence (OR), and non-numeric (OR)
    mixed_constraints = {
      "gender": 0.95,              # High confidence -> AND
      "age_range": 0.75,           # Low confidence -> OR
      "clothing_color": "red",     # Non-numeric -> OR
      "age": 0.87                  # High confidence -> AND
    }

    constraints = db._build_query_constraints("Person", **mixed_constraints)

    # Verify AND constraints (high confidence)
    assert "gender" in constraints
    assert constraints["gender"] == ["==", "0.95"]
    assert "age" in constraints
    assert constraints["age"] == ["==", "0.87"]

    # Verify OR constraints (low confidence and non-numeric)
    assert "or" in constraints
    or_constraints = constraints["or"]
    or_keys = [list(oc.keys())[0] for oc in or_constraints]

    assert "age_range" in or_keys
    assert "clothing_color" in or_keys

    # Verify low confidence is not in direct AND constraints
    assert "age_range" not in constraints or constraints["age_range"] == ["==", "0.75"]

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_empty_constraints(self, mock_vdms_class):
    """Verify empty constraints dict returns only object_type constraint."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    constraints = db._build_query_constraints("Vehicle")

    # Verify only type constraint exists
    assert constraints == {"type": ["==", "Vehicle"]}, \
      "Empty constraints should only have type constraint"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_none_values_ignored(self, mock_vdms_class):
    """Verify None values in constraints are ignored."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    constraints_with_none = {
      "gender": 0.95,
      "age": None,              # Should be ignored
      "color": "blue"
    }

    constraints = db._build_query_constraints("Person", **constraints_with_none)

    # Verify None value is not in constraints
    assert "age" not in constraints, "None values should be ignored"

    # Verify high-confidence numeric constraint (gender 0.95) is direct AND
    assert "gender" in constraints
    assert constraints["gender"] == ["==", "0.95"]

    # Verify non-numeric string constraint is in OR array
    assert "or" in constraints
    or_keys = [list(item.keys())[0] for item in constraints["or"]]
    assert "color" in or_keys, "Non-numeric string should be in OR array"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_numeric_string_to_confidence(self, mock_vdms_class):
    """Verify numeric strings are converted to float for confidence evaluation."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    # Numeric strings should be converted to float for evaluation
    numeric_string_constraints = {
      "confidence_1": "0.95",     # String, but numeric -> convert to float -> AND
      "confidence_2": "0.75"      # String, but numeric -> convert to float -> OR
    }

    constraints = db._build_query_constraints("Person", **numeric_string_constraints)

    # Verify high confidence string is AND constraint
    assert "confidence_1" in constraints
    assert constraints["confidence_1"] == ["==", "0.95"]

    # Verify low confidence string is OR constraint
    assert "or" in constraints
    or_constraints = constraints["or"]
    or_keys = [list(oc.keys())[0] for oc in or_constraints]
    assert "confidence_2" in or_keys

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_boundary_confidence_0_8(self, mock_vdms_class):
    """Verify confidence exactly 0.8 is treated as AND constraint (boundary case)."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    boundary_constraints = {
      "confidence_exact": 0.8        # Exactly 0.8 -> AND (inclusive boundary)
    }

    constraints = db._build_query_constraints("Person", **boundary_constraints)

    # Verify exactly 0.8 is treated as AND constraint
    assert "confidence_exact" in constraints
    assert constraints["confidence_exact"] == ["==", "0.8"]

    # Should not be in OR constraints
    assert "or" not in constraints or \
           not any("confidence_exact" in list(oc.keys()) for oc in constraints.get("or", []))

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_just_below_boundary(self, mock_vdms_class):
    """Verify confidence just below 0.8 is treated as OR constraint."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    near_boundary_constraints = {
      "confidence_below": 0.79        # Just below 0.8 -> OR
    }

    constraints = db._build_query_constraints("Person", **near_boundary_constraints)

    # Should not be in direct AND constraints (except type)
    and_keys = [k for k in constraints.keys() if k != "type" and k != "or"]
    assert "confidence_below" not in and_keys or constraints.get("confidence_below") == ["==", "0.79"]

    # Should be in OR constraints
    assert "or" in constraints
    or_keys = [list(oc.keys())[0] for oc in constraints["or"]]
    assert "confidence_below" in or_keys


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

    # Call findMatches with high-confidence constraint
    db.findMatches("Person", test_vectors, gender=0.95)

    # Extract the query
    call_args = db.sendQuery.call_args
    query_list = call_args[0][0]
    query = query_list[0]
    query_constraints = query['FindDescriptor']['constraints']

    # Verify high-confidence constraint is AND (direct in constraints)
    assert "gender" in query_constraints
    assert query_constraints["gender"] == ["==", "0.95"]

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_find_matches_or_constraints_in_vdms_format(self, mock_vdms_class):
    """Verify findMatches formats OR constraints correctly for VDMS."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 0
    }], []))

    test_vectors = [np.random.randn(256).astype(np.float32)]

    # Call findMatches with low-confidence constraint
    db.findMatches("Person", test_vectors, color=0.75, clothing="red")

    # Extract the query
    call_args = db.sendQuery.call_args
    query_list = call_args[0][0]
    query = query_list[0]
    query_constraints = query['FindDescriptor']['constraints']

    # Verify OR constraints exist and are in correct format
    assert "or" in query_constraints, "OR constraints should be present for low-confidence values"
    or_array = query_constraints["or"]

    # Each OR item should be a dict with single key
    assert isinstance(or_array, list)
    for or_item in or_array:
      assert isinstance(or_item, dict)
      assert len(or_item) == 1, "Each OR item should have single key-value pair"
