#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for QdrantDatabase adapter."""

import json
import pytest
import numpy as np
from unittest.mock import MagicMock, patch

from controller.qdrant_adapter import QdrantDatabase
from controller.reid import ReIDDatabase, ReidNoValidVectorsError
from controller.reid_constants import SCHEMA_NAME


class TestQdrantDatabaseInterface:
  def test_qdrant_database_implements_reid_database(self):
    assert issubclass(QdrantDatabase, ReIDDatabase)

  def test_required_methods_exist(self):
    required_methods = [
      'addEntry', 'findSchema', 'findMatches', 'getPersistedAttributes', 'ensureSchema']
    db = QdrantDatabase()
    for method_name in required_methods:
      assert hasattr(db, method_name)
      assert callable(getattr(db, method_name))


class TestQdrantDatabaseInitialization:
  def test_initialization_defaults(self):
    db = QdrantDatabase()
    assert db.set_name == SCHEMA_NAME
    assert db.similarity_metric == "IP"
    assert db.dimensions is None
    assert db.use_tls is True
    assert hasattr(db, 'lock')

  def test_initialization_with_custom_parameters(self):
    db = QdrantDatabase(set_name="custom_reid", similarity_metric="IP", dimensions=512)
    assert db.set_name == "custom_reid"
    assert db.similarity_metric == "IP"
    assert db.dimensions == 512


class TestQdrantConstraintBuilding:
  def test_build_query_constraints_applies_high_confidence_metadata(self):
    db = QdrantDatabase(confidence_threshold=0.8)
    constraints = db._buildQueryConstraints(
      "person",
      gender={"label": "Female", "confidence": 0.95},
      eyewear={"label": "glasses", "confidence": 0.4})
    assert constraints["type"] == ["==", "person"]
    assert constraints["gender"] == ["==", "Female"]
    assert "eyewear" not in constraints

  def test_build_qdrant_filter_from_constraints(self):
    db = QdrantDatabase()
    query_filter = db._buildQdrantFilter({
      "type": ["==", "person"],
      "gender": ["==", "Female"],
    })
    assert query_filter is not None
    assert len(query_filter.must) == 2


class TestQdrantSchemaManagement:
  def test_ensure_schema_creates_collection_and_marker(self):
    db = QdrantDatabase(dimensions=None)
    db.client = MagicMock()
    db.connected = True
    db._collectionExists = MagicMock(return_value=False)
    db._createCollection = MagicMock()
    db._writeSchemaMarker = MagicMock()

    db.ensureSchema(256)

    assert db._schema_ready is True
    assert db.dimensions == 256
    db._createCollection.assert_called_once_with(SCHEMA_NAME, 256, "IP")
    db._writeSchemaMarker.assert_called_once()

  def test_ensure_schema_raises_on_dimension_mismatch(self):
    db = QdrantDatabase(dimensions=None)
    db.client = MagicMock()
    db.connected = True
    db._collectionExists = MagicMock(return_value=True)
    db._readSchemaMarker = MagicMock(return_value=(True, 128, "IP"))
    db._ensurePayloadIndexes = MagicMock()

    with pytest.raises(RuntimeError, match="has 128 dimensions"):
      db.ensureSchema(256)

  def test_ensure_schema_creates_payload_indexes_for_existing_collection(self):
    db = QdrantDatabase(dimensions=None)
    db.client = MagicMock()
    db.connected = True
    db._collectionExists = MagicMock(return_value=True)
    db._readSchemaMarker = MagicMock(return_value=(True, 256, "IP"))
    db._ensurePayloadIndexes = MagicMock()

    db.ensureSchema(256)

    db._ensurePayloadIndexes.assert_called_once_with(SCHEMA_NAME)

  def test_create_collection_creates_payload_indexes(self):
    db = QdrantDatabase()
    db.client = MagicMock()
    db.connected = True
    db.client.get_collection.return_value = MagicMock(payload_schema={})

    db._createCollection(SCHEMA_NAME, 256, "L2")

    db.client.create_collection.assert_called_once()
    assert db.client.create_payload_index.call_count == 2
    indexed_fields = {
      call.kwargs["field_name"] for call in db.client.create_payload_index.call_args_list}
    assert indexed_fields == {"uuid", "persist_timestamp"}


class TestQdrantDataOperations:
  def test_add_entry_upserts_points(self):
    db = QdrantDatabase(dimensions=4)
    db.client = MagicMock()
    db.connected = True
    vector = np.array([0.1, 0.2, 0.3, 0.4], dtype="float32")

    db.addEntry("uuid-1", "track-1", "person", [vector])

    db.client.upsert.assert_called_once()
    points = db.client.upsert.call_args.kwargs["points"]
    assert len(points) == 1
    assert points[0].payload["uuid"] == "uuid-1"
    assert points[0].payload["type"] == "person"

  def test_add_entry_reraises_upsert_failure(self):
    """Upsert errors must propagate so hierarchy write-health can clear."""
    db = QdrantDatabase(dimensions=4)
    db.client = MagicMock()
    db.connected = True
    db.client.upsert.side_effect = RuntimeError("qdrant unavailable")
    vector = np.array([0.1, 0.2, 0.3, 0.4], dtype="float32")

    with pytest.raises(RuntimeError, match="qdrant unavailable"):
      db.addEntry("uuid-1", "track-1", "person", [vector])

  def test_add_entry_raises_when_no_valid_vectors(self):
    """Empty prepared batches must raise ReidNoValidVectorsError (non-sticky)."""
    db = QdrantDatabase(dimensions=4)
    db.client = MagicMock()
    db.connected = True
    wrong = np.array([0.1, 0.2], dtype="float32")

    with pytest.raises(ReidNoValidVectorsError, match="No valid vectors"):
      db.addEntry("uuid-1", "track-1", "person", [wrong])
    db.client.upsert.assert_not_called()

  def test_get_persisted_attributes_uses_ordered_scroll(self):
    db = QdrantDatabase()
    db.client = MagicMock()
    db.connected = True
    db.client.scroll.return_value = ([
      MagicMock(payload={
        "persist": json.dumps({"gender": "Female"}),
        "persist_timestamp": 20,
      }),
    ], None)

    result = db.getPersistedAttributes("uuid-1")
    assert result == {"gender": "Female"}

    scroll_kwargs = db.client.scroll.call_args.kwargs
    assert scroll_kwargs["limit"] == 1
    assert scroll_kwargs["with_payload"] == ["persist", "persist_timestamp"]
    assert scroll_kwargs["order_by"].key == "persist_timestamp"
    assert scroll_kwargs["order_by"].direction.name == "DESC"

  def test_get_persisted_attributes_falls_back_to_full_scroll(self):
    """Legacy collections without payload indexes still find the latest persist."""
    db = QdrantDatabase()
    db.client = MagicMock()
    db.connected = True
    db.client.scroll.side_effect = [
      RuntimeError("No payload index for persist_timestamp"),
      ([
        MagicMock(payload={
          "persist": json.dumps({"gender": "Male"}),
          "persist_timestamp": 10,
        }),
      ], "page-2"),
      ([
        MagicMock(payload={
          "persist": json.dumps({"gender": "Female"}),
          "persist_timestamp": 30,
        }),
      ], None),
    ]

    result = db.getPersistedAttributes("uuid-1")
    assert result == {"gender": "Female"}
    assert db.client.scroll.call_count == 3
    assert "order_by" in db.client.scroll.call_args_list[0].kwargs
    assert db.client.scroll.call_args_list[2].kwargs["offset"] == "page-2"

  def test_find_matches_returns_vdms_compatible_entities(self):
    db = QdrantDatabase(dimensions=4, similarity_metric="L2")
    db.client = MagicMock()
    db.connected = True
    db.client.query_points.return_value = MagicMock(points=[
      MagicMock(score=0.5, payload={"uuid": "uuid-1", "rvid": "track-1"}),
    ])

    vector = np.array([0.1, 0.2, 0.3, 0.4], dtype="float32")
    result = db.findMatches("person", [vector], k_neighbors=1)

    assert result == [[{
      "uuid": "uuid-1",
      "rvid": "track-1",
      "_distance": 0.5,
    }]]

  def test_find_matches_normalizes_ip_vectors(self):
    db = QdrantDatabase(dimensions=3, similarity_metric="IP")
    db.client = MagicMock()
    db.connected = True
    db.client.query_points.return_value = MagicMock(points=[
      MagicMock(score=0.99, payload={"uuid": "uuid-1", "rvid": "track-1"}),
    ])

    vector = np.array([3.0, 4.0, 0.0], dtype="float32")
    db.findMatches("person", [vector], k_neighbors=1)

    query_vector = db.client.query_points.call_args.kwargs["query"]
    norm = np.linalg.norm(query_vector)
    assert np.isclose(norm, 1.0)


class TestQdrantSimilarityScoreValidation:
  def test_is_valid_similarity_score_rejects_out_of_range_ip(self):
    db = QdrantDatabase(similarity_metric="IP")
    assert db._isValidSimilarityScore(0.5) is True
    assert db._isValidSimilarityScore(1.5) is False

  def test_to_similarity_score_converts_euclidean_score(self):
    db = QdrantDatabase(similarity_metric="L2")
    assert db._toSimilarityScore(2.5) == 2.5
    assert db._toSimilarityScore(-2.5) == 2.5
