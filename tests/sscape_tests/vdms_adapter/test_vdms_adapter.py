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
    
    # Verify blob items are bytes
    for blob_item in blob:
      assert isinstance(blob_item, list), "Blob item should be a list"
      assert isinstance(blob_item[0], bytes), "Blob item should contain bytes"

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
    
    # Additional constraints for semantic metadata
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
    
    # Verify all TIER 1 constraints are applied
    assert query_constraints['type'] == ["==", test_type]
    assert 'gender' in query_constraints, "Additional constraints should be applied in TIER 1"
    assert 'age_range' in query_constraints

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
    
    # Verify blob items are bytes for vector similarity
    for blob_item in blob:
      assert isinstance(blob_item, list)
      assert isinstance(blob_item[0], bytes), "TIER 2 requires vectors as bytes"

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
    
    # Verify k_neighbors is set correctly
    assert query['FindDescriptor']['k_neighbors'] == custom_k, \
      "k_neighbors parameter should control number of results returned"
