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

from controller.vdms_adapter import VDMSDatabase, SCHEMA_NAME, DIMENSIONS, K_NEIGHBORS, SCHEMA_MARKER_CLASS
from controller.reid import ReIDDatabase


class TestVDMSDatabaseInterface:
  """Test that VDMSDatabase implements ReIDDatabase interface."""

  def test_vdms_database_implements_reid_database(self):
    """Verify VDMSDatabase is a subclass of ReIDDatabase."""
    assert issubclass(VDMSDatabase, ReIDDatabase)

  def test_required_methods_exist(self):
    """Verify all required ReIDDatabase methods are implemented."""
    required_methods = [
      'addEntry', 'findSchema', 'findMatches', 'getPersistedAttributes', 'ensureSchema']

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
    assert db.similarity_metric == "IP"
    mock_vdms.assert_called()

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_initialization_with_custom_parameters(self, mock_vdms):
    """Verify VDMS can be initialized with custom schema parameters."""
    custom_set_name = "custom_reid"
    custom_metric = "IP"
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


class TestSchemaValidation:
  """Test descriptor set schema validation and mismatch handling."""

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_find_schema_details_extracts_top_level_dimensions(self, mock_vdms_class):
    """Verify FindDescriptorSet top-level dimensions are parsed."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 1,
      'dimensions': 256
    }], []))

    exists, dimensions = db.findSchemaDetails(SCHEMA_NAME)

    assert exists is True
    assert dimensions == 256

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_find_schema_details_extracts_nested_dimensions(self, mock_vdms_class):
    """Verify dimensions nested under entities are parsed."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 1,
      'entities': [{
        'name': SCHEMA_NAME,
        'dimensions': 512
      }]
    }], []))

    exists, dimensions = db.findSchemaDetails(SCHEMA_NAME)

    assert exists is True
    assert dimensions == 512

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_find_schema_metadata_extracts_metric(self, mock_vdms_class):
    """Verify FindDescriptorSet metric is extracted for schema compatibility checks."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 1,
      'dimensions': 256,
      'metric': 'L2'
    }], []))

    exists, dimensions, metric = db.findSchemaMetadata(SCHEMA_NAME)

    assert exists is True
    assert dimensions == 256
    assert metric == 'L2'

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_ensure_schema_add_descriptor_set_success_path(self, mock_vdms_class):
    """Verify ensureSchema succeeds directly when AddDescriptorSet returns success."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(dimensions=None)
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    db.ensureSchema(256)

    assert db._schema_ready is True
    assert db.dimensions == 256
    assert db.sendQuery.call_count == 2
    first_query = db.sendQuery.call_args_list[0][0][0]
    second_query = db.sendQuery.call_args_list[1][0][0]
    assert 'AddDescriptorSet' in first_query[0]
    assert 'AddEntity' in second_query[0]
    marker = second_query[0]['AddEntity']
    assert marker['properties']['set_name'] == SCHEMA_NAME
    assert marker['properties']['dimensions'] == 256
    assert marker['properties']['metric'] == 'IP'
  @patch('controller.vdms_adapter.vdms.vdms')
  def test_ensure_schema_raises_on_existing_dimension_mismatch(self, mock_vdms_class):
    """Verify fallback metadata check fails when existing descriptor dimensions differ."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(dimensions=None)
    db.sendQuery = Mock(side_effect=[
      ([{'status': 1}], []),
      ([{
        'status': 0,
        'returned': 1,
        'dimensions': 128,
        'metric': 'IP'
      }], []),
    ])

    with pytest.raises(RuntimeError, match="has 128 dimensions"):
      db.ensureSchema(256)

    assert db._schema_ready is False
    assert db.dimensions is None
    assert db.sendQuery.call_count == 2

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_ensure_schema_raises_when_dimensions_not_reported(self, mock_vdms_class):
    """Verify ensureSchema refuses existing descriptor sets without dimension info."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(dimensions=None)
    db.sendQuery = Mock(side_effect=[
      ([{'status': 1}], []),
      ([{
        'status': 0,
        'returned': 1,
        'name': SCHEMA_NAME
      }], []),
    ])

    with pytest.raises(RuntimeError, match="returned no dimensions"):
      db.ensureSchema(256)

    assert db._schema_ready is False
    assert db.dimensions is None
    assert db.sendQuery.call_count == 2

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_ensure_schema_raises_on_existing_metric_mismatch(self, mock_vdms_class):
    """Verify fallback metadata check fails when existing descriptor metric differs."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(similarity_metric="IP", dimensions=None)
    db.sendQuery = Mock(side_effect=[
      ([{'status': 1}], []),
      ([{
        'status': 0,
        'returned': 1,
        'dimensions': 256,
        'metric': 'L2'
      }], []),
    ])

    with pytest.raises(RuntimeError, match="uses metric L2"):
      db.ensureSchema(256)

    assert db._schema_ready is False
    assert db.dimensions is None
    assert db.sendQuery.call_count == 2

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_ensure_schema_accepts_matching_existing_dimensions(self, mock_vdms_class):
    """Verify fallback metadata check succeeds when schema already exists and matches."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(side_effect=[
      ([{'status': 1}], []),
      ([{
        'status': 0,
        'returned': 1,
        'dimensions': 256,
        'metric': 'IP'
      }], []),
    ])

    db.ensureSchema(256)

    assert db._schema_ready is True
    assert db.dimensions == 256
    assert db.sendQuery.call_count == 2
    first_query = db.sendQuery.call_args_list[0][0][0]
    second_query = db.sendQuery.call_args_list[1][0][0]
    assert 'AddDescriptorSet' in first_query[0]
    assert 'FindEntity' in second_query[0]


class TestAddEntry:
  """Test adding entries to VDMS."""

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_prepare_reid_dict_infers_dimensions_from_row_vector(self, mock_vdms_class):
    """Verify prepareReidDict infers dimensions and flattens (1, N) input."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    row_vector = np.arange(12, dtype=np.float32).reshape(1, 12)

    prepared = db.prepareReidDict(row_vector, dimensions=None)

    assert prepared is not None
    assert prepared['dimensions'] == 12
    assert prepared['embedded_vector'].shape == (12,)
    assert np.array_equal(prepared['embedded_vector'], row_vector.reshape(-1))

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_prepare_reid_dict_rejects_dimension_mismatch(self, mock_vdms_class):
    """Verify prepareReidDict returns None when expected dimensions do not match."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    row_vector = np.arange(16, dtype=np.float32).reshape(1, 16)

    prepared = db.prepareReidDict(row_vector, dimensions=32)

    assert prepared is None

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_prepare_reid_dict_normalizes_for_ip_metric(self, mock_vdms_class):
    """Verify prepareReidDict normalizes vectors when normalize_embeddings=True (IP metric)."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(similarity_metric="IP")
    vec = np.zeros(256, dtype=np.float32)
    vec[0] = 3.0
    vec[1] = 4.0

    prepared = db.prepareReidDict(vec, dimensions=256, normalize_embeddings=True)

    assert prepared is not None
    normalized = prepared['embedded_vector']
    assert np.isclose(np.linalg.norm(normalized), 1.0), "Vector should be normalized to unit norm"
    assert np.isclose(normalized[0], 0.6), "Normalized [0] should be 3/5 = 0.6"
    assert np.isclose(normalized[1], 0.8), "Normalized [1] should be 4/5 = 0.8"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_prepare_reid_dict_preserves_for_l2_metric(self, mock_vdms_class):
    """Verify prepareReidDict preserves raw vectors when normalize_embeddings=False (L2 metric)."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(similarity_metric="L2")
    vec = np.zeros(256, dtype=np.float32)
    vec[0] = 3.0
    vec[1] = 4.0

    prepared = db.prepareReidDict(vec, dimensions=256, normalize_embeddings=False)

    assert prepared is not None
    raw = prepared['embedded_vector']
    assert np.isclose(raw[0], 3.0), "Raw [0] should remain 3.0"
    assert np.isclose(raw[1], 4.0), "Raw [1] should remain 4.0"
    assert np.isclose(np.linalg.norm(raw), 5.0), "Raw norm should be 5.0 (3-4-5 triangle)"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_add_entry_requires_standard_fields(self, mock_vdms_class):
    """Verify addEntry includes uuid, rvid, and type in properties."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.dimensions = 256
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
  def test_add_entry_accepts_row_vector_shape(self, mock_vdms_class):
    """Verify addEntry accepts (1, N) vectors through prepareReidDict."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.dimensions = 256
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    row_vector = np.random.randn(1, 256).astype(np.float32)

    db.addEntry("test-uuid", "rvid", "Person", [row_vector])

    db.sendQuery.assert_called_once()
    blob = db.sendQuery.call_args[0][1]
    assert len(blob) == 1
    stored = np.frombuffer(blob[0], dtype=np.float32)
    assert stored.shape == (256,)

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_add_entry_handles_new_metadata_format(self, mock_vdms_class):
    """Verify addEntry extracts label from metadata dict for VDMS constraint matching."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.dimensions = 256
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
  def test_add_entry_normalizes_vectors_before_blob(self, mock_vdms_class):
    """Verify addEntry normalizes vectors before sending them to VDMS when metric is IP."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(similarity_metric="IP")
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    vec = np.zeros(256, dtype=np.float32)
    vec[0] = 3.0
    vec[1] = 4.0

    db.addEntry("test-uuid", "rvid", "Person", [vec])

    call_args = db.sendQuery.call_args
    blob = call_args[0][1]
    normalized = np.frombuffer(blob[0], dtype=np.float32)

    assert np.isclose(np.linalg.norm(normalized), 1.0)
    assert np.isclose(normalized[0], 0.6)
    assert np.isclose(normalized[1], 0.8)

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_add_entry_preserves_raw_vectors_for_l2_metric(self, mock_vdms_class):
    """Verify non-IP metrics do not force vector normalization before sending to VDMS."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(similarity_metric="L2")
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    vec = np.zeros(256, dtype=np.float32)
    vec[0] = 3.0
    vec[1] = 4.0

    db.addEntry("test-uuid", "rvid", "Person", [vec])

    call_args = db.sendQuery.call_args
    blob = call_args[0][1]
    stored = np.frombuffer(blob[0], dtype=np.float32)

    assert np.isclose(stored[0], 3.0)
    assert np.isclose(stored[1], 4.0)
    assert np.isclose(np.linalg.norm(stored), 5.0)

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_add_entry_handles_multiple_vectors(self, mock_vdms_class):
    """Verify addEntry can handle multiple embeddings per object."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.dimensions = 256
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
  def test_find_matches_normalizes_query_vectors(self, mock_vdms_class):
    """Verify findMatches normalizes query vectors before similarity search when metric is IP."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(similarity_metric="IP")
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 0
    }], []))

    vec = np.zeros(256, dtype=np.float32)
    vec[0] = 3.0
    vec[1] = 4.0

    db.findMatches("Person", [vec])

    call_args = db.sendQuery.call_args
    blob = call_args[0][1]
    normalized = np.frombuffer(blob[0], dtype=np.float32)

    assert np.isclose(np.linalg.norm(normalized), 1.0)
    assert np.isclose(normalized[0], 0.6)
    assert np.isclose(normalized[1], 0.8)

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_find_matches_preserves_query_vectors_for_l2_metric(self, mock_vdms_class):
    """Verify findMatches preserves raw vectors for the L2 metric path."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(similarity_metric="L2")
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 0
    }], []))

    vec = np.zeros(256, dtype=np.float32)
    vec[0] = 3.0
    vec[1] = 4.0

    db.findMatches("Person", [vec])

    call_args = db.sendQuery.call_args
    blob = call_args[0][1]
    stored = np.frombuffer(blob[0], dtype=np.float32)

    assert np.isclose(stored[0], 3.0)
    assert np.isclose(stored[1], 4.0)
    assert np.isclose(np.linalg.norm(stored), 5.0)

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_find_matches_skips_zero_norm_vectors(self, mock_vdms_class):
    """Verify findMatches ignores zero-norm vectors for IP metric and avoids empty VDMS queries."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(similarity_metric="IP")
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 0
    }], []))

    zero_vec = np.zeros(256, dtype=np.float32)
    result = db.findMatches("Person", [zero_vec])

    assert result is None
    db.sendQuery.assert_not_called()

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
  def test_find_matches_filters_invalid_ip_similarity_scores(self, mock_vdms_class):
    """Verify findMatches filters entities with IP scores outside [-1, 1]."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(similarity_metric="IP")
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 3,
      'entities': [
        {'uuid': 'valid', 'rvid': 'rvid-1', '_distance': 0.9},
        {'uuid': 'too-high', 'rvid': 'rvid-2', '_distance': 1.2},
        {'uuid': 'too-low', 'rvid': 'rvid-3', '_distance': -1.1},
      ]
    }], []))

    test_vectors = [np.random.randn(256).astype(np.float32)]
    result = db.findMatches("Person", test_vectors)

    assert result is not None
    assert len(result) == 1
    assert len(result[0]) == 1
    assert result[0][0]['uuid'] == 'valid'

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_find_matches_preserves_per_vector_slot_when_all_entities_invalid(self, mock_vdms_class):
    """Verify successful per-vector responses with only invalid IP scores return an empty slot."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(similarity_metric="IP")
    db.sendQuery = Mock(return_value=([
      {
        'status': 0,
        'returned': 2,
        'entities': [
          {'uuid': 'too-high', 'rvid': 'rvid-2', '_distance': 1.4},
          {'uuid': 'too-low', 'rvid': 'rvid-3', '_distance': -1.2},
        ]
      },
      {
        'status': 0,
        'returned': 1,
        'entities': [
          {'uuid': 'valid', 'rvid': 'rvid-1', '_distance': 0.9},
        ]
      }
    ], []))

    test_vectors = [
      np.random.randn(256).astype(np.float32),
      np.random.randn(256).astype(np.float32),
    ]
    result = db.findMatches("Person", test_vectors)

    assert result is not None
    assert len(result) == 2
    assert result[0] == []
    assert len(result[1]) == 1
    assert result[1][0]['uuid'] == 'valid'

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_find_matches_returns_none_when_all_ip_scores_invalid(self, mock_vdms_class):
    """Verify findMatches returns no matches if all IP scores are out of range."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(similarity_metric="IP")
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 2,
      'entities': [
        {'uuid': 'too-high', 'rvid': 'rvid-2', '_distance': 1.4},
        {'uuid': 'too-low', 'rvid': 'rvid-3', '_distance': -1.2},
      ]
    }], []))

    test_vectors = [np.random.randn(256).astype(np.float32)]
    result = db.findMatches("Person", test_vectors)

    assert result == [[]]

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_find_matches_keeps_out_of_range_scores_for_l2_metric(self, mock_vdms_class):
    """Verify L2 keeps large positive distances but rejects negative distances."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(similarity_metric="L2")
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 2,
      'entities': [
        {'uuid': 'dist-high', 'rvid': 'rvid-1', '_distance': 1.4},
        {'uuid': 'dist-negative', 'rvid': 'rvid-2', '_distance': -1.2},
      ]
    }], []))

    test_vectors = [np.random.randn(256).astype(np.float32)]
    result = db.findMatches("Person", test_vectors)

    assert result is not None
    assert len(result) == 1
    assert len(result[0]) == 1
    assert result[0][0]['uuid'] == 'dist-high'
    assert result[0][0]['_distance'] == 1.4

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_find_matches_handles_no_results(self, mock_vdms_class):
    """Verify findMatches preserves one empty slot when a query returns nothing."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 0
    }], []))

    test_vectors = [np.random.randn(256).astype(np.float32)]
    result = db.findMatches("Person", test_vectors)

    assert result == [[]]

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

    result = db._buildQueryConstraints("Person", **constraints)

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

    result = db._buildQueryConstraints("Person", **constraints)

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

    result = db._buildQueryConstraints("Person", **constraints)

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

    result = db._buildQueryConstraints("Person", **constraints)

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

    result = db._buildQueryConstraints("Person", **constraints)

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
    constraints = db._buildQueryConstraints(test_type)

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

    constraints = db._buildQueryConstraints("Person", **high_confidence_constraints)

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

    constraints = db._buildQueryConstraints("Person", **low_confidence_constraints)

    assert constraints == {"type": ["==", "Person"]}, "Low-confidence constraints should all be ignored"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_build_constraints_empty_constraints(self, mock_vdms_class):
    """Verify empty constraints dict returns only object_type constraint."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    constraints = db._buildQueryConstraints("Vehicle")

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

    constraints = db._buildQueryConstraints("Person", **constraints_with_none)

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

    constraints = db._buildQueryConstraints("Person", **boundary_constraints)

    assert "attribute_exact" in constraints
    assert constraints["attribute_exact"] == ["==", "test_value"]


class TestFindMatchesIntegration:
  """Test findMatches integration with constraint building."""

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_find_matches_uses_constraint_builder(self, mock_vdms_class):
    """Verify findMatches delegates to _buildQueryConstraints."""
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


class TestConfigurationParameters:
  """Test that VDMSDatabase respects configuration parameters."""

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_default_parameters_initialization(self, mock_vdms_class):
    """Verify VDMSDatabase initializes with expected defaults."""
    from controller.vdms_adapter import SCHEMA_NAME, SIMILARITY_METRIC
    from controller.reid_env import DEFAULT_CONFIDENCE_THRESHOLD

    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()

    assert db.set_name == SCHEMA_NAME, f"Expected set_name={SCHEMA_NAME}, got {db.set_name}"
    assert db.dimensions is None, f"Expected dimensions=None, got {db.dimensions}"
    assert db.similarity_metric == SIMILARITY_METRIC, f"Expected metric={SIMILARITY_METRIC}, got {db.similarity_metric}"
    assert db.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD, f"Expected threshold={DEFAULT_CONFIDENCE_THRESHOLD}, got {db.confidence_threshold}"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_custom_confidence_threshold_in_constraints(self, mock_vdms_class):
    """Verify custom confidence_threshold parameter is used in constraint building."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    custom_threshold = 0.95
    db = VDMSDatabase(confidence_threshold=custom_threshold)
    db.sendQuery = Mock(return_value=([{'status': 0, 'returned': 0}], []))

    # High-confidence constraint that meets custom threshold
    constraints_high = {
      "gender": {"label": "Female", "model_name": "gender_v2", "confidence": 0.96}
    }

    result = db._buildQueryConstraints("Person", **constraints_high)
    assert "gender" in result, "Confidence 0.96 should exceed custom threshold 0.95"

    # Medium-confidence constraint that fails custom threshold
    constraints_medium = {
      "age": {"label": 25, "model_name": "age_v2", "confidence": 0.90}
    }

    result = db._buildQueryConstraints("Person", **constraints_medium)
    assert "age" not in result, "Confidence 0.90 should fail custom threshold 0.95"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_similarity_metric_affects_normalization(self, mock_vdms_class):
    """Verify similarity_metric parameter properly controls normalization in addEntry."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    vec = np.zeros(256, dtype=np.float32)
    vec[0] = 3.0
    vec[1] = 4.0

    # Test IP metric (should normalize)
    db_ip = VDMSDatabase(similarity_metric="IP")
    db_ip.sendQuery = Mock(return_value=([{'status': 0}], []))
    db_ip.addEntry("uuid-ip", "rvid", "Person", [vec])

    blob_ip = db_ip.sendQuery.call_args[0][1]
    normalized_ip = np.frombuffer(blob_ip[0], dtype=np.float32)
    assert np.isclose(np.linalg.norm(normalized_ip), 1.0), "IP metric should normalize"

    # Test L2 metric (should NOT normalize)
    db_l2 = VDMSDatabase(similarity_metric="L2")
    db_l2.sendQuery = Mock(return_value=([{'status': 0}], []))
    db_l2.addEntry("uuid-l2", "rvid", "Person", [vec])

    blob_l2 = db_l2.sendQuery.call_args[0][1]
    stored_l2 = np.frombuffer(blob_l2[0], dtype=np.float32)
    assert np.isclose(np.linalg.norm(stored_l2), 5.0), "L2 metric should preserve raw vectors"


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
    db.dimensions = 256
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
    db.dimensions = 256
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


class TestDimensionInferenceAndArbitraryDimensions:
  """Test that ReID works with arbitrary dimensions, not just 256."""

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_add_entry_with_128_dimensions(self, mock_vdms_class):
    """Verify addEntry works with 128-dimension vectors."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(dimensions=128)
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    test_vectors = [np.random.randn(128).astype(np.float32)]
    db.addEntry("uuid", "rvid", "Person", test_vectors)

    call_args = db.sendQuery.call_args
    blob = call_args[0][1]
    assert len(blob) == 1
    stored = np.frombuffer(blob[0], dtype=np.float32)
    assert stored.shape == (128,), f"Expected (128,) but got {stored.shape}"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_add_entry_with_512_dimensions(self, mock_vdms_class):
    """Verify addEntry works with 512-dimension vectors."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(dimensions=512)
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    test_vectors = [np.random.randn(512).astype(np.float32)]
    db.addEntry("uuid", "rvid", "Person", test_vectors)

    call_args = db.sendQuery.call_args
    blob = call_args[0][1]
    stored = np.frombuffer(blob[0], dtype=np.float32)
    assert stored.shape == (512,), f"Expected (512,) but got {stored.shape}"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_add_entry_with_1024_dimensions(self, mock_vdms_class):
    """Verify addEntry works with 1024-dimension vectors."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(dimensions=1024)
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    test_vectors = [np.random.randn(1024).astype(np.float32)]
    db.addEntry("uuid", "rvid", "Person", test_vectors)

    call_args = db.sendQuery.call_args
    blob = call_args[0][1]
    stored = np.frombuffer(blob[0], dtype=np.float32)
    assert stored.shape == (1024,), f"Expected (1024,) but got {stored.shape}"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_dimension_inference_none_with_128_vectors(self, mock_vdms_class):
    """Verify dimension inference works when dimensions=None and vectors are 128D."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(dimensions=None)
    vec = np.random.randn(128).astype(np.float32)

    prepared = db.prepareReidDict(vec, dimensions=None)

    assert prepared is not None
    assert prepared['dimensions'] == 128
    assert prepared['embedded_vector'].shape == (128,)

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_dimension_inference_none_with_512_vectors(self, mock_vdms_class):
    """Verify dimension inference works when dimensions=None and vectors are 512D."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(dimensions=None)
    vec = np.random.randn(512).astype(np.float32)

    prepared = db.prepareReidDict(vec, dimensions=None)

    assert prepared is not None
    assert prepared['dimensions'] == 512
    assert prepared['embedded_vector'].shape == (512,)

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_find_matches_with_128_dimensions(self, mock_vdms_class):
    """Verify findMatches works correctly with 128-dimension vectors."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(dimensions=128)
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 1,
      'entities': [{'uuid': 'match-1', '_distance': 0.95}]
    }], []))

    test_vectors = [np.random.randn(128).astype(np.float32)]
    result = db.findMatches("Person", test_vectors)

    call_args = db.sendQuery.call_args
    blob = call_args[0][1]
    query_vec = np.frombuffer(blob[0], dtype=np.float32)
    assert query_vec.shape == (128,), f"Expected query vector (128,) but got {query_vec.shape}"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_find_matches_with_512_dimensions(self, mock_vdms_class):
    """Verify findMatches works correctly with 512-dimension vectors."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(dimensions=512)
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 1,
      'entities': [{'uuid': 'match-1', '_distance': 0.95}]
    }], []))

    test_vectors = [np.random.randn(512).astype(np.float32)]
    result = db.findMatches("Person", test_vectors)

    call_args = db.sendQuery.call_args
    blob = call_args[0][1]
    query_vec = np.frombuffer(blob[0], dtype=np.float32)
    assert query_vec.shape == (512,), f"Expected query vector (512,) but got {query_vec.shape}"

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_dimension_mismatch_rejected_for_128(self, mock_vdms_class):
    """Verify dimension mismatch is rejected for 128-dimension adapter."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(dimensions=128)
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    # Try to add 256-dimension vector to 128-dimension adapter
    wrong_vec = np.random.randn(256).astype(np.float32)
    db.addEntry("uuid", "rvid", "Person", [wrong_vec])

    # Should not have sent query (vector was rejected)
    db.sendQuery.assert_not_called()

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_dimension_mismatch_rejected_for_512(self, mock_vdms_class):
    """Verify dimension mismatch is rejected for 512-dimension adapter."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(dimensions=512)
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    # Try to add 256-dimension vector to 512-dimension adapter
    wrong_vec = np.random.randn(256).astype(np.float32)
    db.addEntry("uuid", "rvid", "Person", [wrong_vec])

    # Should not have sent query (vector was rejected)
    db.sendQuery.assert_not_called()

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_normalization_works_for_non_256_dimensions(self, mock_vdms_class):
    """Verify IP normalization works correctly for non-256 dimensions."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(dimensions=128, similarity_metric="IP")
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    vec = np.zeros(128, dtype=np.float32)
    vec[0] = 3.0
    vec[1] = 4.0

    db.addEntry("uuid", "rvid", "Person", [vec])

    call_args = db.sendQuery.call_args
    blob = call_args[0][1]
    normalized = np.frombuffer(blob[0], dtype=np.float32)

    assert np.isclose(np.linalg.norm(normalized), 1.0), "Should normalize to unit norm"
    assert np.isclose(normalized[0], 0.6)
    assert np.isclose(normalized[1], 0.8)

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_l2_preservation_for_non_256_dimensions(self, mock_vdms_class):
    """Verify L2 metric preserves raw vectors for non-256 dimensions."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(dimensions=512, similarity_metric="L2")
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    vec = np.zeros(512, dtype=np.float32)
    vec[0] = 3.0
    vec[1] = 4.0

    db.addEntry("uuid", "rvid", "Person", [vec])

    call_args = db.sendQuery.call_args
    blob = call_args[0][1]
    stored = np.frombuffer(blob[0], dtype=np.float32)

    assert np.isclose(stored[0], 3.0)
    assert np.isclose(stored[1], 4.0)
    assert np.isclose(np.linalg.norm(stored), 5.0)

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_row_vector_shape_inference_128(self, mock_vdms_class):
    """Verify (1, 128) row vector is properly flattened and inferred."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(dimensions=128)
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    row_vector = np.random.randn(1, 128).astype(np.float32)
    db.addEntry("uuid", "rvid", "Person", [row_vector])

    call_args = db.sendQuery.call_args
    blob = call_args[0][1]
    stored = np.frombuffer(blob[0], dtype=np.float32)
    assert stored.shape == (128,)

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_row_vector_shape_inference_512(self, mock_vdms_class):
    """Verify (1, 512) row vector is properly flattened and inferred."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(dimensions=512)
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    row_vector = np.random.randn(1, 512).astype(np.float32)
    db.addEntry("uuid", "rvid", "Person", [row_vector])

    call_args = db.sendQuery.call_args
    blob = call_args[0][1]
    stored = np.frombuffer(blob[0], dtype=np.float32)
    assert stored.shape == (512,)

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_mixed_dimension_vectors_rejected(self, mock_vdms_class):
    """Verify mixed-dimension vectors are rejected in same addEntry call."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(dimensions=256)
    db.sendQuery = Mock(return_value=([{'status': 0}, {'status': 0}], []))

    vectors = [
      np.random.randn(256).astype(np.float32),  # Correct dimension
      np.random.randn(512).astype(np.float32)   # Wrong dimension (should be skipped)
    ]

    db.addEntry("uuid", "rvid", "Person", vectors)

    call_args = db.sendQuery.call_args
    query_list = call_args[0][0]
    # Should only have one AddDescriptor query (the 512D vector was skipped)
    assert len(query_list) == 1, "Expected 1 query for valid vector, got {}".format(len(query_list))

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_arbitrary_dimension_64(self, mock_vdms_class):
    """Verify adapter works with small (64-dimension) vectors."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(dimensions=64)
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    vec = np.random.randn(64).astype(np.float32)
    db.addEntry("uuid", "rvid", "Person", [vec])

    call_args = db.sendQuery.call_args
    blob = call_args[0][1]
    stored = np.frombuffer(blob[0], dtype=np.float32)
    assert stored.shape == (64,)

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_arbitrary_dimension_2048(self, mock_vdms_class):
    """Verify adapter works with large (2048-dimension) vectors."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase(dimensions=2048)
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    vec = np.random.randn(2048).astype(np.float32)
    db.addEntry("uuid", "rvid", "Person", [vec])

    call_args = db.sendQuery.call_args
    blob = call_args[0][1]
    stored = np.frombuffer(blob[0], dtype=np.float32)
    assert stored.shape == (2048,)

class TestAddEntryWithPersist:
  """Test addEntry stores persist attributes alongside reid vectors."""

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_add_entry_stores_persist_as_json(self, mock_vdms_class):
    """Verify addEntry serializes persist dict as JSON in properties."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.dimensions = 256
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    persist = {'gender': 'Female', 'age_group': 'adult', 'timestamp': 1678924070.942}
    test_vectors = [np.random.randn(256).astype(np.float32)]

    db.addEntry("uuid", "rvid", "Person", test_vectors, persist=persist)

    call_args = db.sendQuery.call_args
    properties = call_args[0][0][0]['AddDescriptor']['properties']

    assert 'persist' in properties
    assert json.loads(properties['persist']) == {'gender': 'Female', 'age_group': 'adult'}

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_add_entry_stores_persist_timestamp(self, mock_vdms_class):
    """Verify addEntry stores persist_timestamp when persist is provided."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.dimensions = 256
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    persist = {'gender': 'Female', 'timestamp': 1678924070.942}
    test_vectors = [np.random.randn(256).astype(np.float32)]

    db.addEntry("uuid", "rvid", "Person", test_vectors, persist=persist)

    call_args = db.sendQuery.call_args
    properties = call_args[0][0][0]['AddDescriptor']['properties']

    assert 'persist_timestamp' in properties
    assert properties['persist_timestamp'] == 1678924070.942

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_add_entry_no_persist_omits_persist_fields(self, mock_vdms_class):
    """Verify addEntry does not add persist fields when persist is None."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.dimensions = 256
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    test_vectors = [np.random.randn(256).astype(np.float32)]
    db.addEntry("uuid", "rvid", "Person", test_vectors, persist=None)

    call_args = db.sendQuery.call_args
    properties = call_args[0][0][0]['AddDescriptor']['properties']

    assert 'persist' not in properties
    assert 'persist_timestamp' not in properties

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_add_entry_empty_persist_omits_persist_fields(self, mock_vdms_class):
    """Verify addEntry does not add persist fields when persist is empty dict."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.dimensions = 256
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    test_vectors = [np.random.randn(256).astype(np.float32)]
    db.addEntry("uuid", "rvid", "Person", test_vectors, persist={})

    call_args = db.sendQuery.call_args
    properties = call_args[0][0][0]['AddDescriptor']['properties']

    assert 'persist' not in properties
    assert 'persist_timestamp' not in properties

class TestGetPersistedAttributes:
  """Test retrieving persist attributes from VDMS by UUID."""

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_get_persisted_attributes_returns_latest_by_timestamp(self, mock_vdms_class):
    """Verify getPersistedAttributes returns the entry with the highest persist_timestamp."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 2,
      'entities': [
        {'uuid': 'test-uuid', 'persist': json.dumps({'gender': 'Female'}), 'persist_timestamp': 1678924070.942},
        {'uuid': 'test-uuid', 'persist': json.dumps({'gender': 'Male'}), 'persist_timestamp': 1678924130.512},
      ]
    }], []))

    result = db.getPersistedAttributes('test-uuid')

    assert result == {'gender': 'Male'}

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_get_persisted_attributes_returns_empty_when_not_found(self, mock_vdms_class):
    """Verify getPersistedAttributes returns empty dict when no entry exists."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 0,
      'entities': []
    }], []))

    result = db.getPersistedAttributes('unknown-uuid')

    assert result == {}

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_get_persisted_attributes_returns_empty_on_no_response(self, mock_vdms_class):
    """Verify getPersistedAttributes returns empty dict when VDMS returns no response."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([], []))

    result = db.getPersistedAttributes('test-uuid')

    assert result == {}

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_get_persisted_attributes_skips_entities_without_persist(self, mock_vdms_class):
    """Verify getPersistedAttributes ignores entities missing the persist field."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 2,
      'entities': [
        {'uuid': 'test-uuid', 'persist_timestamp': 1678924070.942},
        {'uuid': 'test-uuid', 'persist': json.dumps({'gender': 'Male'}), 'persist_timestamp': 1678924130.512},
      ]
    }], []))

    result = db.getPersistedAttributes('test-uuid')

    assert result == {'gender': 'Male'}

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_get_persisted_attributes_handles_corrupt_json(self, mock_vdms_class):
    """Verify getPersistedAttributes returns empty dict on JSON decode error."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 1,
      'entities': [
        {'uuid': 'test-uuid', 'persist': 'not valid json', 'persist_timestamp': 1678924070.942},
      ]
    }], []))

    result = db.getPersistedAttributes('test-uuid')

    assert result == {}

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_get_persisted_attributes_queries_by_uuid(self, mock_vdms_class):
    """Verify getPersistedAttributes sends correct UUID constraint to VDMS."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{'status': 0, 'returned': 0, 'entities': []}], []))

    db.getPersistedAttributes('my-test-uuid')

    call_args = db.sendQuery.call_args
    query = call_args[0][0][0]
    assert 'FindDescriptor' in query
    constraints = query['FindDescriptor']['constraints']
    assert constraints == {'uuid': ['==', 'my-test-uuid']}

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_get_persisted_attributes_requests_persist_fields(self, mock_vdms_class):
    """Verify getPersistedAttributes requests uuid, persist and persist_timestamp in results."""
    mock_vdms_instance = MagicMock()
    mock_vdms_class.return_value = mock_vdms_instance

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{'status': 0, 'returned': 0, 'entities': []}], []))

    db.getPersistedAttributes('test-uuid')

    call_args = db.sendQuery.call_args
    query = call_args[0][0][0]
    results_list = query['FindDescriptor']['results']['list']
    assert 'uuid' in results_list
    assert 'persist' in results_list
    assert 'persist_timestamp' in results_list

class TestUpdateActiveDictPersistMerge:
  """Test persist attribute merging in updateActiveDict on REID match."""

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_historical_attributes_restored_when_current_persist_is_empty_dict(self, mock_vdms_class):
    """Verify historical persist attributes are merged into current track on REID match."""
    mock_vdms_class.return_value = MagicMock()

    from controller.uuid_manager import UUIDManager
    manager = UUIDManager()
    manager.reid_database = MagicMock()
    manager.reid_database.getPersistedAttributes.return_value = {'gender': 'Female'}

    obj = MagicMock()
    obj.rv_id = 1
    obj.gid = 2
    obj.when = 1000.0
    obj.category = "person"
    obj.reid_state = MagicMock()
    obj.similarity = None
    obj.metadata = {}
    obj.chain_data = MagicMock()
    obj.chain_data.persist = {}

    database_id = 3
    similarity = 12.5

    with patch.object(manager, 'isNewID', return_value=True), \
         patch.object(manager, '_activeGidIndex', return_value={}), \
         patch.object(manager, '_logLiveGidIntegrity'), \
         patch.object(manager, '_extractReidEmbedding', return_value=None), \
         patch.object(manager, '_extractSemanticMetadata', return_value={}), \
         patch.object(manager, 'quality_features', {1: []}):
      manager.active_ids = {1: [None, None]}
      manager.updateActiveDict(obj, database_id, similarity)

    assert obj.chain_data.persist.get('gender') == 'Female'

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_existing_attribute_not_overwritten_on_reid_match(self, mock_vdms_class):
    """Verify current session attributes take precedence over historical on REID match."""
    mock_vdms_class.return_value = MagicMock()

    from controller.uuid_manager import UUIDManager
    manager = UUIDManager()
    manager.reid_database = MagicMock()
    manager.reid_database.getPersistedAttributes.return_value = {'gender': 'Male'}

    obj = MagicMock()
    obj.rv_id = 1
    obj.gid = 2
    obj.when = 1000.0
    obj.category = "person"
    obj.reid_state = MagicMock()
    obj.similarity = None
    obj.metadata = {}
    obj.chain_data = MagicMock()
    obj.chain_data.persist = {'gender': 'Female'}

    database_id = 3
    similarity = 12.5

    with patch.object(manager, 'isNewID', return_value=True), \
         patch.object(manager, '_activeGidIndex', return_value={}), \
         patch.object(manager, '_logLiveGidIntegrity'), \
         patch.object(manager, '_extractReidEmbedding', return_value=None), \
         patch.object(manager, '_extractSemanticMetadata', return_value={}), \
         patch.object(manager, 'quality_features', {1: []}):
      manager.active_ids = {1: [None, None]}
      manager.updateActiveDict(obj, database_id, similarity)

    assert obj.chain_data.persist.get('gender') == 'Female'

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_no_op_when_chain_data_is_none(self, mock_vdms_class):
    """Verify no crash or mutation when chain_data is None on REID match."""
    mock_vdms_class.return_value = MagicMock()

    from controller.uuid_manager import UUIDManager
    manager = UUIDManager()
    manager.reid_database = MagicMock()
    manager.reid_database.getPersistedAttributes.return_value = {'gender': 'Female'}

    obj = MagicMock()
    obj.rv_id = 1
    obj.gid = 2
    obj.when = 1000.0
    obj.category = "person"
    obj.reid_state = MagicMock()
    obj.similarity = None
    obj.metadata = {}
    obj.chain_data = None

    database_id = 3
    similarity = 12.5

    with patch.object(manager, 'isNewID', return_value=True), \
         patch.object(manager, '_activeGidIndex', return_value={}), \
         patch.object(manager, '_logLiveGidIntegrity'), \
         patch.object(manager, '_extractReidEmbedding', return_value=None), \
         patch.object(manager, '_extractSemanticMetadata', return_value={}), \
         patch.object(manager, 'quality_features', {1: []}):
      manager.active_ids = {1: [None, None]}
      manager.updateActiveDict(obj, database_id, similarity)

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_features_for_database_stores_persist_when_attributes_present(self, mock_vdms_class):
    """Verify features_for_database includes persist with timestamp when chain_data has attributes."""
    mock_vdms_class.return_value = MagicMock()

    from controller.uuid_manager import UUIDManager
    manager = UUIDManager()
    manager.reid_database = MagicMock()
    manager.reid_database.getPersistedAttributes.return_value = {}

    obj = MagicMock()
    obj.rv_id = 1
    obj.gid = 2
    obj.when = 1678924070.942
    obj.category = "person"
    obj.reid_state = MagicMock()
    obj.similarity = None
    obj.metadata = {}
    obj.chain_data = MagicMock()
    obj.chain_data.persist = {'gender': 'Female'}

    database_id = 3
    similarity = 12.5

    with patch.object(manager, 'isNewID', return_value=True), \
         patch.object(manager, '_activeGidIndex', return_value={}), \
         patch.object(manager, '_logLiveGidIntegrity'), \
         patch.object(manager, '_extractReidEmbedding', return_value=None), \
         patch.object(manager, '_extractSemanticMetadata', return_value={}), \
         patch.object(manager, 'quality_features', {1: []}):
      manager.active_ids = {1: [None, None]}
      manager.updateActiveDict(obj, database_id, similarity)

    stored = manager.features_for_database.get(1)
    assert stored is not None
    assert 'persist' in stored
    assert stored['persist'].get('gender') == 'Female'
    assert stored['persist'].get('timestamp') == 1678924070.942

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_features_for_database_omits_persist_when_no_attributes(self, mock_vdms_class):
    """Verify features_for_database omits persist entirely when chain_data.persist is empty."""
    mock_vdms_class.return_value = MagicMock()

    from controller.uuid_manager import UUIDManager
    manager = UUIDManager()
    manager.reid_database = MagicMock()
    manager.reid_database.getPersistedAttributes.return_value = {}

    obj = MagicMock()
    obj.rv_id = 1
    obj.gid = 2
    obj.when = 1234.5
    obj.category = "person"
    obj.reid_state = MagicMock()
    obj.similarity = None
    obj.metadata = {}
    obj.chain_data = MagicMock()
    obj.chain_data.persist = {}  # empty — no attributes to persist

    database_id = 3
    similarity = 12.5

    with patch.object(manager, 'isNewID', return_value=True), \
         patch.object(manager, '_activeGidIndex', return_value={}), \
         patch.object(manager, '_logLiveGidIntegrity'), \
         patch.object(manager, '_extractReidEmbedding', return_value=None), \
         patch.object(manager, '_extractSemanticMetadata', return_value={}), \
         patch.object(manager, 'quality_features', {1: []}):
      manager.active_ids = {1: [None, None]}
      manager.updateActiveDict(obj, database_id, similarity)

    stored = manager.features_for_database.get(1)
    assert stored is not None
    assert 'persist' not in stored

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_features_for_database_omits_persist_when_chain_data_is_none(self, mock_vdms_class):
    """Verify features_for_database omits persist entirely when chain_data is None."""
    mock_vdms_class.return_value = MagicMock()

    from controller.uuid_manager import UUIDManager
    manager = UUIDManager()
    manager.reid_database = MagicMock()
    manager.reid_database.getPersistedAttributes.return_value = {}

    obj = MagicMock()
    obj.rv_id = 1
    obj.gid = 2
    obj.when = 1234.5
    obj.category = "person"
    obj.reid_state = MagicMock()
    obj.similarity = None
    obj.metadata = {}
    obj.chain_data = None  # no chain data at all

    database_id = 3
    similarity = 12.5

    with patch.object(manager, 'isNewID', return_value=True), \
         patch.object(manager, '_activeGidIndex', return_value={}), \
         patch.object(manager, '_logLiveGidIntegrity'), \
         patch.object(manager, '_extractReidEmbedding', return_value=None), \
         patch.object(manager, '_extractSemanticMetadata', return_value={}), \
         patch.object(manager, 'quality_features', {1: []}):
      manager.active_ids = {1: [None, None]}
      manager.updateActiveDict(obj, database_id, similarity)

    stored = manager.features_for_database.get(1)
    assert stored is not None
    assert 'persist' not in stored

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_historical_attributes_restored_on_reid_match(self, mock_vdms_class):
    """Verify historical persist attributes are merged into current track on REID match
    when the attribute is absent from the current session."""
    mock_vdms_class.return_value = MagicMock()

    from controller.uuid_manager import UUIDManager
    manager = UUIDManager()
    manager.reid_database = MagicMock()
    manager.reid_database.getPersistedAttributes.return_value = {'gender': 'Female'}

    obj = MagicMock()
    obj.rv_id = 1
    obj.gid = 2
    obj.when = 1000.0
    obj.category = "person"
    obj.reid_state = MagicMock()
    obj.similarity = None
    obj.metadata = {}
    obj.chain_data = MagicMock()
    # Current session has no gender — detector hasn't classified yet this appearance
    obj.chain_data.persist = {'gender': None}

    database_id = 3
    similarity = 12.5

    with patch.object(manager, 'isNewID', return_value=True), \
         patch.object(manager, '_activeGidIndex', return_value={}), \
         patch.object(manager, '_logLiveGidIntegrity'), \
         patch.object(manager, '_extractReidEmbedding', return_value=None), \
         patch.object(manager, '_extractSemanticMetadata', return_value={}), \
         patch.object(manager, 'quality_features', {1: []}):
      manager.active_ids = {1: [None, None]}
      manager.updateActiveDict(obj, database_id, similarity)

    # Historical 'Female' should fill in since current was None
    assert obj.chain_data.persist.get('gender') == 'Female'

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_historical_attribute_not_restored_when_current_has_value(self, mock_vdms_class):
    """Verify historical persist is ignored when current session already has the attribute."""
    mock_vdms_class.return_value = MagicMock()

    from controller.uuid_manager import UUIDManager
    manager = UUIDManager()
    manager.reid_database = MagicMock()
    manager.reid_database.getPersistedAttributes.return_value = {'gender': 'Female'}

    obj = MagicMock()
    obj.rv_id = 1
    obj.gid = 2
    obj.when = 1000.0
    obj.category = "person"
    obj.reid_state = MagicMock()
    obj.similarity = None
    obj.metadata = {}
    obj.chain_data = MagicMock()
    # Current session already classified gender this appearance
    obj.chain_data.persist = {'gender': 'Male'}

    database_id = 3
    similarity = 12.5

    with patch.object(manager, 'isNewID', return_value=True), \
         patch.object(manager, '_activeGidIndex', return_value={}), \
         patch.object(manager, '_logLiveGidIntegrity'), \
         patch.object(manager, '_extractReidEmbedding', return_value=None), \
         patch.object(manager, '_extractSemanticMetadata', return_value={}), \
         patch.object(manager, 'quality_features', {1: []}):
      manager.active_ids = {1: [None, None]}
      manager.updateActiveDict(obj, database_id, similarity)

    # Current 'Male' wins, historical 'Female' is ignored
    assert obj.chain_data.persist.get('gender') == 'Male'

class TestSchemaMarker:
  """Unit tests for _writeSchemaMarker and _readSchemaMarker"""

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_read_schema_marker_sends_correct_query(self, mock_vdms_class):
    """Verify _readSchemaMarker sends a FindEntity query scoped to this set_name."""
    mock_vdms_class.return_value = MagicMock()

    db = VDMSDatabase(set_name="custom_set")
    db.sendQuery = Mock(return_value=([{'status': 0, 'returned': 0, 'entities': []}], []))

    db._readSchemaMarker()

    call_args = db.sendQuery.call_args
    query = call_args[0][0][0]
    assert 'FindEntity' in query
    find_entity = query['FindEntity']
    assert find_entity['class'] == SCHEMA_MARKER_CLASS
    assert find_entity['constraints'] == {'set_name': ['==', 'custom_set']}
    assert find_entity['results']['list'] == ['set_name', 'dimensions', 'metric']

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_read_schema_marker_returns_false_on_no_response(self, mock_vdms_class):
    """Verify _readSchemaMarker returns (False, None, None) when sendQuery returns nothing."""
    mock_vdms_class.return_value = MagicMock()

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([], []))

    exists, dimensions, metric = db._readSchemaMarker()

    assert exists is False
    assert dimensions is None
    assert metric is None

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_read_schema_marker_returns_false_on_nonzero_status(self, mock_vdms_class):
    """Verify _readSchemaMarker returns (False, None, None) when VDMS reports a failure status."""
    mock_vdms_class.return_value = MagicMock()

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{'status': 1}], []))

    exists, dimensions, metric = db._readSchemaMarker()

    assert exists is False
    assert dimensions is None
    assert metric is None

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_read_schema_marker_returns_false_when_not_found(self, mock_vdms_class):
    """Verify _readSchemaMarker returns (False, None, None) when no marker entity exists."""
    mock_vdms_class.return_value = MagicMock()

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{'status': 0, 'returned': 0, 'entities': []}], []))

    exists, dimensions, metric = db._readSchemaMarker()

    assert exists is False
    assert dimensions is None
    assert metric is None

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_read_schema_marker_parses_flat_payload(self, mock_vdms_class):
    """Verify _readSchemaMarker parses dimensions/metric returned at the top level."""
    mock_vdms_class.return_value = MagicMock()

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 1,
      'dimensions': 256,
      'metric': 'L2'
    }], []))

    exists, dimensions, metric = db._readSchemaMarker()

    assert exists is True
    assert dimensions == 256
    assert metric == 'L2'

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_read_schema_marker_parses_nested_entities_payload(self, mock_vdms_class):
    """Verify _readSchemaMarker parses dimensions/metric nested under 'entities'."""
    mock_vdms_class.return_value = MagicMock()

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 1,
      'entities': [{
        'set_name': SCHEMA_NAME,
        'dimensions': 512,
        'metric': 'IP'
      }]
    }], []))

    exists, dimensions, metric = db._readSchemaMarker()

    assert exists is True
    assert dimensions == 512
    assert metric == 'IP'

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_read_schema_marker_exists_via_entities_without_returned_count(self, mock_vdms_class):
    """Verify a non-empty 'entities' list is enough to mark the marker as existing,
    even if VDMS omits or zeroes the 'returned' count."""
    mock_vdms_class.return_value = MagicMock()

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'entities': [{'set_name': SCHEMA_NAME, 'dimensions': 256, 'metric': 'L2'}]
    }], []))

    exists, dimensions, metric = db._readSchemaMarker()

    assert exists is True
    assert dimensions == 256
    assert metric == 'L2'

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_read_schema_marker_exists_but_missing_dimensions(self, mock_vdms_class):
    """Verify a marker that exists but is missing dimensions returns (True, None, metric)."""
    mock_vdms_class.return_value = MagicMock()

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 1,
      'metric': 'L2'
    }], []))

    exists, dimensions, metric = db._readSchemaMarker()

    assert exists is True
    assert dimensions is None
    assert metric == 'L2'

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_read_schema_marker_exists_but_missing_metric(self, mock_vdms_class):
    """Verify a marker that exists but is missing metric returns (True, dimensions, None)."""
    mock_vdms_class.return_value = MagicMock()

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 1,
      'dimensions': 256
    }], []))

    exists, dimensions, metric = db._readSchemaMarker()

    assert exists is True
    assert dimensions == 256
    assert metric is None

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_write_schema_marker_skips_existence_check_when_flag_set(self, mock_vdms_class):
    """Verify skip_exists_check=True writes the marker without querying for it first."""
    mock_vdms_class.return_value = MagicMock()

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    db._writeSchemaMarker(256, 'L2', skip_exists_check=True)

    assert db.sendQuery.call_count == 1
    query = db.sendQuery.call_args_list[0][0][0]
    assert 'AddEntity' in query[0]

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_write_schema_marker_sends_correct_add_entity_query(self, mock_vdms_class):
    """Verify _writeSchemaMarker's AddEntity query has the expected class and properties."""
    mock_vdms_class.return_value = MagicMock()

    db = VDMSDatabase(set_name="custom_set")
    db.sendQuery = Mock(return_value=([{'status': 0}], []))

    db._writeSchemaMarker(512, 'IP', skip_exists_check=True)

    query = db.sendQuery.call_args_list[0][0][0][0]
    add_entity = query['AddEntity']
    assert add_entity['class'] == SCHEMA_MARKER_CLASS
    assert add_entity['properties'] == {
      'set_name': 'custom_set',
      'dimensions': 512,
      'metric': 'IP'
    }

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_write_schema_marker_checks_existence_by_default(self, mock_vdms_class):
    """Verify skip_exists_check=False (default) reads the marker before writing."""
    mock_vdms_class.return_value = MagicMock()

    db = VDMSDatabase()
    db.sendQuery = Mock(side_effect=[
      ([{'status': 0, 'returned': 0, 'entities': []}], []),
      ([{'status': 0}], []),
    ])

    db._writeSchemaMarker(256, 'L2')

    assert db.sendQuery.call_count == 2
    first_query = db.sendQuery.call_args_list[0][0][0]
    second_query = db.sendQuery.call_args_list[1][0][0]
    assert 'FindEntity' in first_query[0]
    assert 'AddEntity' in second_query[0]

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_write_schema_marker_skips_write_when_marker_already_exists(self, mock_vdms_class):
    """Verify _writeSchemaMarker does not write a duplicate marker when one already exists."""
    mock_vdms_class.return_value = MagicMock()

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{
      'status': 0,
      'returned': 1,
      'dimensions': 256,
      'metric': 'L2'
    }], []))

    db._writeSchemaMarker(256, 'L2')

    assert db.sendQuery.call_count == 1
    query = db.sendQuery.call_args_list[0][0][0]
    assert 'FindEntity' in query[0]

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_write_schema_marker_raises_on_failed_write(self, mock_vdms_class):
    """Verify a failed AddEntity write raises rather than leaving a half-ready schema."""
    mock_vdms_class.return_value = MagicMock()

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([{'status': 1}], []))

    with pytest.raises(RuntimeError, match="Failed to write schema marker"):
      db._writeSchemaMarker(256, 'L2', skip_exists_check=True)

    assert db.sendQuery.call_count == 1

  @patch('controller.vdms_adapter.vdms.vdms')
  def test_write_schema_marker_raises_on_no_response(self, mock_vdms_class):
    """Verify a missing response from VDMS on write raises."""
    mock_vdms_class.return_value = MagicMock()

    db = VDMSDatabase()
    db.sendQuery = Mock(return_value=([], []))

    with pytest.raises(RuntimeError, match="Failed to write schema marker"):
      db._writeSchemaMarker(256, 'L2', skip_exists_check=True)

    assert db.sendQuery.call_count == 1
