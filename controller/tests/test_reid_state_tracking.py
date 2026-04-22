#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for ReID state tracking and ID chaining functionality in MovingObject.

Tests cover:
- ReidState enum definition and transitions
- previous_ids_chain recording and retrieval
- Similarity score tracking
- State transition logic (PENDING_COLLECTION → MATCHED/QUERY_NO_MATCH)
"""

import pytest
import time
from unittest.mock import Mock
from pathlib import Path

# Add controller/src to path
import sys
controller_src = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(controller_src))

from controller.moving_object import MovingObject, ReidState


class TestReidStateEnum:
  """Test ReidState enum definition and values."""

  def test_reid_state_enum_has_four_states(self):
    """Verify ReidState enum has all required states."""
    states = [state.value for state in ReidState]
    assert len(states) == 4
    assert "pending_collection" in states
    assert "query_no_match" in states
    assert "matched" in states
    assert "reid_disabled" in states

  def test_reid_state_enum_values_are_strings(self):
    """Verify ReidState enum values are properly formatted strings."""
    assert ReidState.PENDING_COLLECTION.value == "pending_collection"
    assert ReidState.QUERY_NO_MATCH.value == "query_no_match"
    assert ReidState.MATCHED.value == "matched"
    assert ReidState.REID_DISABLED.value == "reid_disabled"

  def test_reid_state_enum_equality(self):
    """Verify ReidState enum comparison works correctly."""
    state1 = ReidState.MATCHED
    state2 = ReidState.MATCHED
    state3 = ReidState.PENDING_COLLECTION

    assert state1 == state2
    assert state1 != state3
    assert state1.value == state2.value


class TestMovingObjectReidStateInitialization:
  """Test MovingObject initialization with reid state tracking."""

  def setup_method(self):
    """Set up mock camera for each test."""
    self.mock_camera = Mock()
    self.mock_camera.pose = Mock()
    self.mock_camera.pose.intrinsics = Mock()
    self.mock_camera.pose.intrinsics.mapPixelToNormalizedImagePlane = Mock(
        return_value=Mock()
    )

  def test_moving_object_initializes_with_pending_collection_state(self):
    """Verify new MovingObject starts in PENDING_COLLECTION state."""
    info = {'id': '1', 'confidence': 0.95}
    timestamp = time.time()

    obj = MovingObject(info, timestamp, self.mock_camera)

    assert obj.reid_state == ReidState.PENDING_COLLECTION
    assert obj.reid_state.value == "pending_collection"

  def test_moving_object_initializes_with_none_similarity(self):
    """Verify similarity score is None at initialization."""
    info = {'id': '1', 'confidence': 0.95}
    timestamp = time.time()

    obj = MovingObject(info, timestamp, self.mock_camera)

    assert obj.similarity is None

  def test_moving_object_initializes_with_empty_chain(self):
    """Verify previous_ids_chain is empty list at initialization."""
    info = {'id': '1', 'confidence': 0.95}
    timestamp = time.time()

    obj = MovingObject(info, timestamp, self.mock_camera)

    assert isinstance(obj.previous_ids_chain, list)
    assert len(obj.previous_ids_chain) == 0


class TestRecordIdChange:
  """Test record_id_change() method for ID chain tracking."""

  def setup_method(self):
    """Set up mock camera and object for each test."""
    self.mock_camera = Mock()
    self.mock_camera.pose = Mock()
    self.mock_camera.pose.intrinsics = Mock()
    self.mock_camera.pose.intrinsics.mapPixelToNormalizedImagePlane = Mock(
        return_value=Mock()
    )

    self.info = {'id': '1', 'confidence': 0.95}
    self.timestamp = time.time()
    self.obj = MovingObject(self.info, self.timestamp, self.mock_camera)

  def test_record_id_change_adds_entry_to_chain(self):
    """Verify record_id_change() adds entry to previous_ids_chain."""
    new_id = "gid_123"
    similarity = 0.87
    ts = time.time()

    self.obj.record_id_change(new_id, similarity_score=similarity, timestamp=ts)

    assert len(self.obj.previous_ids_chain) == 1
    assert self.obj.previous_ids_chain[0]['id'] == new_id
    assert self.obj.previous_ids_chain[0]['similarity_score'] == similarity
    assert self.obj.previous_ids_chain[0]['timestamp'] == ts

  def test_record_id_change_with_none_similarity(self):
    """Verify record_id_change() handles None similarity (new object case)."""
    new_id = "gid_456"
    ts = time.time()

    self.obj.record_id_change(new_id, similarity_score=None, timestamp=ts)

    assert len(self.obj.previous_ids_chain) == 1
    assert self.obj.previous_ids_chain[0]['id'] == new_id
    assert self.obj.previous_ids_chain[0]['similarity_score'] is None
    assert self.obj.previous_ids_chain[0]['timestamp'] == ts

  def test_record_id_change_uses_current_time_when_timestamp_not_provided(self):
    """Verify record_id_change() uses current time if timestamp is None."""
    new_id = "gid_789"
    before = time.time()

    self.obj.record_id_change(new_id, similarity_score=0.92, timestamp=None)

    after = time.time()
    recorded_time = self.obj.previous_ids_chain[0]['timestamp']

    assert before <= recorded_time <= after

  def test_record_id_change_appends_multiple_entries(self):
    """Verify multiple record_id_change() calls build chain correctly."""
    ts1 = time.time()
    self.obj.record_id_change("gid_1", similarity_score=0.85, timestamp=ts1)

    ts2 = time.time() + 1.0
    self.obj.record_id_change("gid_2", similarity_score=0.90, timestamp=ts2)

    ts3 = time.time() + 2.0
    self.obj.record_id_change("gid_3", similarity_score=0.88, timestamp=ts3)

    assert len(self.obj.previous_ids_chain) == 3
    assert self.obj.previous_ids_chain[0]['id'] == "gid_1"
    assert self.obj.previous_ids_chain[1]['id'] == "gid_2"
    assert self.obj.previous_ids_chain[2]['id'] == "gid_3"

  def test_record_id_change_maintains_chronological_order(self):
    """Verify entries in chain maintain insertion order (chronological)."""
    timestamps = []
    for i in range(5):
      ts = time.time() + i * 0.1
      timestamps.append(ts)
      self.obj.record_id_change(f"gid_{i}", similarity_score=0.80 + i * 0.02, timestamp=ts)

    for i, entry in enumerate(self.obj.previous_ids_chain):
      assert entry['timestamp'] == timestamps[i]


class TestIsReided:
  """Test is_reided() helper method."""

  def setup_method(self):
    """Set up mock camera and object for each test."""
    self.mock_camera = Mock()
    self.mock_camera.pose = Mock()
    self.mock_camera.pose.intrinsics = Mock()
    self.mock_camera.pose.intrinsics.mapPixelToNormalizedImagePlane = Mock(
        return_value=Mock()
    )

    self.info = {'id': '1', 'confidence': 0.95}
    self.obj = MovingObject(self.info, time.time(), self.mock_camera)

  def test_is_reided_returns_false_for_pending_collection(self):
    """Verify is_reided() returns False when state is PENDING_COLLECTION."""
    self.obj.reid_state = ReidState.PENDING_COLLECTION

    assert self.obj.is_reided() is False

  def test_is_reided_returns_false_for_query_no_match(self):
    """Verify is_reided() returns False when state is QUERY_NO_MATCH."""
    self.obj.reid_state = ReidState.QUERY_NO_MATCH

    assert self.obj.is_reided() is False

  def test_is_reided_returns_true_for_matched(self):
    """Verify is_reided() returns True when state is MATCHED."""
    self.obj.reid_state = ReidState.MATCHED

    assert self.obj.is_reided() is True

  def test_is_reided_returns_false_for_reid_disabled(self):
    """Verify is_reided() returns False when state is REID_DISABLED."""
    self.obj.reid_state = ReidState.REID_DISABLED

    assert self.obj.is_reided() is False

  def test_is_reided_reflects_state_changes(self):
    """Verify is_reided() reflects dynamic state changes."""
    assert self.obj.is_reided() is False

    self.obj.reid_state = ReidState.MATCHED
    assert self.obj.is_reided() is True

    self.obj.reid_state = ReidState.QUERY_NO_MATCH
    assert self.obj.is_reided() is False

    self.obj.reid_state = ReidState.REID_DISABLED
    assert self.obj.is_reided() is False


class TestGetPreviousIds:
  """Test get_previous_ids() method for chain retrieval."""

  def setup_method(self):
    """Set up mock camera and object for each test."""
    self.mock_camera = Mock()
    self.mock_camera.pose = Mock()
    self.mock_camera.pose.intrinsics = Mock()
    self.mock_camera.pose.intrinsics.mapPixelToNormalizedImagePlane = Mock(
        return_value=Mock()
    )

    self.info = {'id': '1', 'confidence': 0.95}
    self.obj = MovingObject(self.info, time.time(), self.mock_camera)

  def test_get_previous_ids_returns_empty_list_on_new_object(self):
    """Verify get_previous_ids() returns empty list for new object."""
    ids = self.obj.get_previous_ids()

    assert isinstance(ids, list)
    assert len(ids) == 0

  def test_get_previous_ids_returns_copy_not_reference(self):
    """Verify get_previous_ids() returns copy, not direct reference."""
    ts = time.time()
    self.obj.record_id_change("gid_1", similarity_score=0.85, timestamp=ts)

    ids1 = self.obj.get_previous_ids()
    ids2 = self.obj.get_previous_ids()

    # Modify returned list (should not affect internal state)
    ids1.append({'id': 'fake_gid', 'timestamp': ts, 'similarity_score': 0.5})

    # Second retrieval should not include the fake entry
    assert len(ids2) == 1
    assert ids2[0]['id'] == "gid_1"

  def test_get_previous_ids_returns_all_chain_entries(self):
    """Verify get_previous_ids() returns all entries in chain."""
    ts_base = time.time()
    for i in range(5):
      ts = ts_base + i * 0.1
      self.obj.record_id_change(f"gid_{i}", similarity_score=0.80 + i * 0.02, timestamp=ts)

    ids = self.obj.get_previous_ids()

    assert len(ids) == 5
    assert ids[0]['id'] == "gid_0"
    assert ids[4]['id'] == "gid_4"

  def test_get_previous_ids_preserves_entry_structure(self):
    """Verify get_previous_ids() preserves complete entry structure."""
    ts = time.time()
    self.obj.record_id_change("gid_test", similarity_score=0.92, timestamp=ts)

    ids = self.obj.get_previous_ids()
    entry = ids[0]

    assert 'id' in entry
    assert 'timestamp' in entry
    assert 'similarity_score' in entry
    assert entry['id'] == "gid_test"
    assert entry['similarity_score'] == 0.92
    assert entry['timestamp'] == ts


class TestStateTransitions:
  """Test state transitions in realistic scenarios."""

  def setup_method(self):
    """Set up mock camera and object for each test."""
    self.mock_camera = Mock()
    self.mock_camera.pose = Mock()
    self.mock_camera.pose.intrinsics = Mock()
    self.mock_camera.pose.intrinsics.mapPixelToNormalizedImagePlane = Mock(
        return_value=Mock()
    )

    self.info = {'id': '1', 'confidence': 0.95}
    self.obj = MovingObject(self.info, time.time(), self.mock_camera)

  def test_transition_pending_to_matched(self):
    """Simulate state transition: PENDING_COLLECTION → MATCHED."""
    assert self.obj.reid_state == ReidState.PENDING_COLLECTION
    assert self.obj.is_reided() is False

    # Simulate successful reid match
    self.obj.reid_state = ReidState.MATCHED
    self.obj.similarity = 0.95
    ts = time.time()
    self.obj.record_id_change("matched_gid_123", similarity_score=0.95, timestamp=ts)

    assert self.obj.reid_state == ReidState.MATCHED
    assert self.obj.is_reided() is True
    assert self.obj.similarity == 0.95
    assert len(self.obj.previous_ids_chain) == 1
    assert self.obj.previous_ids_chain[0]['id'] == "matched_gid_123"

  def test_transition_pending_to_query_no_match(self):
    """Simulate state transition: PENDING_COLLECTION → QUERY_NO_MATCH."""
    assert self.obj.reid_state == ReidState.PENDING_COLLECTION

    # Simulate query with no match (new object)
    self.obj.reid_state = ReidState.QUERY_NO_MATCH
    self.obj.similarity = None
    ts = time.time()
    self.obj.record_id_change("new_gid_456", similarity_score=None, timestamp=ts)

    assert self.obj.reid_state == ReidState.QUERY_NO_MATCH
    assert self.obj.is_reided() is False
    assert self.obj.similarity is None
    assert len(self.obj.previous_ids_chain) == 1
    assert self.obj.previous_ids_chain[0]['id'] == "new_gid_456"
    assert self.obj.previous_ids_chain[0]['similarity_score'] is None

  def test_multi_frame_tracking_with_state_persistence(self):
    """Test realistic scenario: object tracked across multiple frames with state persistence."""
    # Frame 1: New detection, pending reid collection
    assert self.obj.reid_state == ReidState.PENDING_COLLECTION

    # Frame 2: Query made, matched to previous object
    self.obj.reid_state = ReidState.MATCHED
    self.obj.similarity = 0.92
    ts1 = time.time()
    self.obj.record_id_change("gid_1", similarity_score=0.92, timestamp=ts1)

    # Frame 3: Still same object, state persists
    assert self.obj.reid_state == ReidState.MATCHED
    assert self.obj.gid is None  # gid set via uuid_manager, not in this test

    # Frame 4: Object re-identified in different camera (hypothetical scenario)
    ts2 = time.time() + 1.0
    self.obj.record_id_change("gid_2", similarity_score=0.88, timestamp=ts2)

    chain = self.obj.get_previous_ids()
    assert len(chain) == 2
    assert chain[0]['id'] == "gid_1"
    assert chain[0]['similarity_score'] == 0.92
    assert chain[1]['id'] == "gid_2"
    assert chain[1]['similarity_score'] == 0.88

  def test_transition_pending_to_reid_disabled(self):
    """Simulate state transition: PENDING_COLLECTION → REID_DISABLED (when VDMS disabled)."""
    assert self.obj.reid_state == ReidState.PENDING_COLLECTION
    assert len(self.obj.previous_ids_chain) == 0

    # Simulate case where reid system is disabled (e.g., VDMS not available)
    self.obj.reid_state = ReidState.REID_DISABLED
    self.obj.similarity = None
    # No record_id_change() - no query happened

    assert self.obj.reid_state == ReidState.REID_DISABLED
    assert self.obj.is_reided() is False
    assert self.obj.similarity is None
    assert len(self.obj.previous_ids_chain) == 0  # No chain entry - no query/match occurred


class TestChainDataIntegrity:
  """Test chain data integrity under various conditions."""

  def setup_method(self):
    """Set up mock camera and object for each test."""
    self.mock_camera = Mock()
    self.mock_camera.pose = Mock()
    self.mock_camera.pose.intrinsics = Mock()
    self.mock_camera.pose.intrinsics.mapPixelToNormalizedImagePlane = Mock(
        return_value=Mock()
    )

    self.info = {'id': '1', 'confidence': 0.95}
    self.obj = MovingObject(self.info, time.time(), self.mock_camera)

  def test_chain_with_mixed_similarity_scores(self):
    """Test chain tracking with varying similarity scores."""
    ts_base = time.time()

    # High similarity match
    self.obj.record_id_change("gid_1", similarity_score=0.99, timestamp=ts_base)
    # Low but valid similarity match
    self.obj.record_id_change("gid_2", similarity_score=0.51, timestamp=ts_base + 1.0)
    # No match (new object)
    self.obj.record_id_change("gid_3", similarity_score=None, timestamp=ts_base + 2.0)

    chain = self.obj.get_previous_ids()

    assert chain[0]['similarity_score'] == 0.99
    assert chain[1]['similarity_score'] == 0.51
    assert chain[2]['similarity_score'] is None

  def test_chain_with_float_similarity_precision(self):
    """Test that similarity scores maintain floating-point precision."""
    ts = time.time()
    precision_value = 0.8675309

    self.obj.record_id_change("gid_precise", similarity_score=precision_value, timestamp=ts)

    chain = self.obj.get_previous_ids()
    assert chain[0]['similarity_score'] == precision_value

  def test_chain_with_boundary_similarity_values(self):
    """Test chain with boundary similarity values (0.0 and 1.0)."""
    ts_base = time.time()

    # Perfect match
    self.obj.record_id_change("gid_perfect", similarity_score=1.0, timestamp=ts_base)
    # Worst possible match (still valid)
    self.obj.record_id_change("gid_worst", similarity_score=0.0, timestamp=ts_base + 1.0)

    chain = self.obj.get_previous_ids()

    assert chain[0]['similarity_score'] == 1.0
    assert chain[1]['similarity_score'] == 0.0

  def test_large_chain_integrity(self):
    """Test chain integrity with large number of entries."""
    ts_base = time.time()
    chain_size = 1000

    for i in range(chain_size):
      ts = ts_base + i * 0.01
      similarity = 0.5 + (i % 50) * 0.01  # Varying similarities
      self.obj.record_id_change(f"gid_{i}", similarity_score=similarity, timestamp=ts)

    chain = self.obj.get_previous_ids()

    assert len(chain) == chain_size
    assert chain[0]['id'] == "gid_0"
    assert chain[chain_size - 1]['id'] == f"gid_{chain_size - 1}"
    # Verify chronological order is maintained
    for i in range(len(chain) - 1):
      assert chain[i]['timestamp'] <= chain[i + 1]['timestamp']


if __name__ == '__main__':
  pytest.main([__file__, '-v'])
