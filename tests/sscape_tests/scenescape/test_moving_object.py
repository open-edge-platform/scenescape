# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import base64
import datetime
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from controller.moving_object import ChainData, Chronoloc, MovingObject, decodeReIDEmbeddingVector
from scene_common.geometry import Point, Rectangle


def _camera():
  return SimpleNamespace(cameraID='cam-1')


def _base_info(*, object_id='obj-1', metadata=None):
  info = {
    'id': object_id,
    'category': 'person',
    'confidence': 0.9,
    'bounding_box': {'x': 0.1, 'y': 0.2, 'width': 0.3, 'height': 0.4}
  }
  if metadata is not None:
    info['metadata'] = metadata
  return info


class TestChainData:
  def test_chain_data_defaults_include_sensor_maps(self):
    chain_data = ChainData(regions={}, publishedLocations=[], persist={})

    assert chain_data.active_sensors == set()
    assert chain_data.env_sensor_state == {}
    assert chain_data.attr_sensor_events == {}


class TestMovingObject:
  def test_init_extracts_reid_and_keeps_metadata(self):
    when = datetime.datetime.now(datetime.timezone.utc)
    metadata = {
      'age': 'adult',
      'reid': {'embedding_vector': [0.1, 0.2], 'model_name': 'reid-v1'}
    }

    obj = MovingObject(_base_info(metadata=metadata), when, _camera())

    assert obj.metadata['age'] == 'adult'
    assert obj.reid['model_name'] == 'reid-v1'
    assert np.allclose(obj.reid['embedding_vector'], np.array([[0.1, 0.2]], dtype=np.float32))
    assert 'metadata' not in obj.info

  def test_init_decodes_base64_reid_vector_with_runtime_length(self):
    when = datetime.datetime.now(datetime.timezone.utc)
    vector = np.arange(192, dtype=np.float32)
    encoded = base64.b64encode(vector.tobytes()).decode('utf-8')
    metadata = {
      'reid': {
        'embedding_vector': encoded,
        'embedding_dimensions': 192,
        'model_name': 'reid-v2'
      }
    }

    obj = MovingObject(_base_info(metadata=metadata), when, _camera())

    assert obj.reid['model_name'] == 'reid-v2'
    assert obj.reid['embedding_dimensions'] == 192
    assert obj.reid['embedding_vector'].shape == (1, 192)
    assert np.allclose(obj.reid['embedding_vector'], vector.reshape(1, -1))

  def test_dump_and_load_round_trip_reid_with_embedding_dimensions(self):
    when = datetime.datetime.now(datetime.timezone.utc)
    obj = MovingObject(_base_info(metadata={'age': 'adult'}), when, _camera())
    obj.gid = 'gid-1'
    obj.reid = {
      'embedding_vector': np.arange(64, dtype=np.float32).reshape(1, -1),
      'model_name': 'reid-v3'
    }
    obj.location = [Chronoloc(Point(1.0, 2.0, 3.0), when, obj.boundingBox)]
    obj.vectors = [SimpleNamespace(camera=_camera(), point=Point(1.0, 2.0, 3.0), last_seen=when)]

    dumped = obj.dump()

    assert dumped['reid']['embedding_dimensions'] == 64
    assert isinstance(dumped['reid']['embedding_vector'], str)

    loaded = MovingObject(_base_info(object_id='obj-2'), when, _camera())
    loaded.load(dumped, SimpleNamespace(cameras={'cam-1': _camera()}))

    assert loaded.reid['model_name'] == 'reid-v3'
    assert loaded.reid['embedding_dimensions'] == 64
    assert loaded.reid['embedding_vector'].shape == (1, 64)
    assert np.allclose(loaded.reid['embedding_vector'], obj.reid['embedding_vector'])

  def test_set_persistent_attributes_stores_full_and_partial_values(self):
    when = datetime.datetime.now(datetime.timezone.utc)
    obj = MovingObject(_base_info(), when, _camera())
    info = {
      'color': [{'value': 'red', 'model_name': 'palette-v1', 'confidence': 0.88}],
      'license': {'plate': 'ABC123', 'state': 'CA', 'country': 'US'}
    }

    obj.setPersistentAttributes(info, ['color', {'license': 'plate,state'}])

    assert obj.chain_data.persist['color']['value'] == 'red'
    assert obj.chain_data.persist['color']['model_name'] == 'palette-v1'
    assert obj.chain_data.persist['license']['plate'] == 'ABC123'
    assert obj.chain_data.persist['license']['state'] == 'CA'
    assert 'country' not in obj.chain_data.persist['license']

  def test_set_previous_merges_persistent_data_and_carries_chain_fields(self):
    when = datetime.datetime.now(datetime.timezone.utc)
    bounds = Rectangle({'x': 0.0, 'y': 0.0, 'width': 1.0, 'height': 1.0})

    current_obj = MovingObject(_base_info(object_id='obj-current'), when, _camera())
    current_obj.location = [Chronoloc(Point(1.0, 1.0, 0.0), when, bounds)]
    current_obj.chain_data = ChainData(
      regions={},
      publishedLocations=[Point(0.0, 0.0, 0.0)],
      persist={'attr': {'a': None, 'b': 'new'}}
    )

    previous_obj = MovingObject(_base_info(object_id='obj-prev'), when, _camera())
    previous_obj.location = [Chronoloc(Point(2.0, 2.0, 0.0), when, bounds)]
    previous_obj.chain_data = ChainData(
      regions={},
      publishedLocations=[Point(0.0, 0.0, 0.0)],
      persist={'attr': {'a': 'old', 'b': 'old-b'}}
    )
    previous_obj.gid = 'gid-1'
    previous_obj.first_seen = when
    previous_obj.frameCount = 3

    current_obj.setPrevious(previous_obj)

    assert current_obj.gid == 'gid-1'
    assert current_obj.frameCount == 4
    assert current_obj.first_seen == when
    assert len(current_obj.location) == 2
    assert current_obj.chain_data.persist['attr']['a'] == 'old'
    assert current_obj.chain_data.persist['attr']['b'] == 'old-b'

  def test_infer_rotation_from_velocity_applies_quaternion_above_threshold(self):
    when = datetime.datetime.now(datetime.timezone.utc)
    obj = MovingObject(_base_info(), when, _camera())
    obj.rotation_from_velocity = True
    obj.velocity = Point(1.0, 0.0, 0.0)

    with patch('controller.moving_object.rotationToTarget') as mock_rotation_to_target:
      mock_rotation_to_target.return_value = SimpleNamespace(
        as_quat=lambda: np.array([0.0, 0.0, 0.0, 1.0])
      )

      obj.inferRotationFromVelocity()

    mock_rotation_to_target.assert_called_once()
    assert obj.rotation == [0.0, 0.0, 0.0, 1.0]

  def test_infer_rotation_from_velocity_skips_when_speed_below_threshold(self):
    when = datetime.datetime.now(datetime.timezone.utc)
    obj = MovingObject(_base_info(), when, _camera())
    obj.rotation_from_velocity = True
    obj.velocity = Point(0.01, 0.0, 0.0)
    original_rotation = list(obj.rotation)

    with patch('controller.moving_object.rotationToTarget') as mock_rotation_to_target:
      obj.inferRotationFromVelocity()

    mock_rotation_to_target.assert_not_called()
    assert obj.rotation == original_rotation


class TestDecodeReIDEmbeddingVector:
  """Tests for decodeReIDEmbeddingVector validation and normalization."""

  def test_list_without_dimensions_normalizes_to_2d_array(self):
    result = decodeReIDEmbeddingVector([0.1, 0.2, 0.3])
    assert isinstance(result, np.ndarray)
    assert result.shape == (1, 3)
    assert result.dtype == np.float32

  def test_ndarray_without_dimensions_normalizes_to_2d_array(self):
    vec = np.arange(128, dtype=np.float32)
    result = decodeReIDEmbeddingVector(vec)
    assert result.shape == (1, 128)

  def test_list_with_matching_dimensions_succeeds(self):
    vec = list(range(256))
    result = decodeReIDEmbeddingVector(vec, dimensions=256)
    assert result.shape == (1, 256)

  def test_ndarray_with_matching_dimensions_succeeds(self):
    vec = np.zeros(256, dtype=np.float32)
    result = decodeReIDEmbeddingVector(vec, dimensions=256)
    assert result.shape == (1, 256)

  def test_list_with_mismatched_dimensions_raises(self):
    import pytest
    with pytest.raises(ValueError, match="128 elements, expected 256"):
      decodeReIDEmbeddingVector(list(range(128)), dimensions=256)

  def test_ndarray_with_mismatched_dimensions_raises(self):
    import pytest
    vec = np.zeros(64, dtype=np.float32)
    with pytest.raises(ValueError, match="64 elements, expected 128"):
      decodeReIDEmbeddingVector(vec, dimensions=128)

  def test_2d_ndarray_is_flattened_before_dimension_check(self):
    vec = np.ones((4, 64), dtype=np.float32)
    # 4*64 = 256 elements; should pass with dimensions=256
    result = decodeReIDEmbeddingVector(vec, dimensions=256)
    assert result.shape == (1, 256)

  def test_2d_ndarray_mismatch_after_flatten_raises(self):
    import pytest
    vec = np.ones((2, 64), dtype=np.float32)  # 128 elements
    with pytest.raises(ValueError, match="128 elements, expected 256"):
      decodeReIDEmbeddingVector(vec, dimensions=256)

  def test_invalid_base64_string_raises(self):
    import pytest, binascii
    # Characters outside the base64 alphabet (e.g. '!') are rejected when validate=True
    with pytest.raises(binascii.Error):
      decodeReIDEmbeddingVector("not!valid==base64")

  def test_invalid_base64_propagates_through_decode_reid_vector(self):
    """Verify _decodeReIDVector catches binascii.Error from invalid base64 and sets embedding_vector to None."""
    import datetime
    when = datetime.datetime.now(datetime.timezone.utc)
    from types import SimpleNamespace
    camera = SimpleNamespace(cameraID='cam-1')
    info = {
      'id': 'obj-1',
      'category': 'person',
      'confidence': 0.9,
      'bounding_box': {'x': 0.1, 'y': 0.2, 'width': 0.3, 'height': 0.4},
      'metadata': {
        'reid': {
          'embedding_vector': 'not!valid==base64',
          'model_name': 'test-model',
        }
      }
    }
    obj = MovingObject(info, when, camera)
    assert obj.reid.get('embedding_vector') is None
