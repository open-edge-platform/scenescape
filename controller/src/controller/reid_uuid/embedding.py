# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import base64
import binascii

import numpy as np

from scene_common import log

REID_FLOAT_SIZE_BYTES = np.dtype(np.float32).itemsize
REID_EMBEDDING_DIMENSIONS_KEY = 'embedding_dimensions'


def get_reid_embedding_dimensions(reid):
  """Extract embedding dimensions from ReID payload metadata."""
  if not isinstance(reid, dict):
    return None

  for key in (REID_EMBEDDING_DIMENSIONS_KEY, 'dimensions'):
    value = reid.get(key)
    if value is None:
      continue
    try:
      return int(value)
    except (TypeError, ValueError) as err:
      raise ValueError(f"Invalid ReID embedding dimensions: {value}") from err

  return None


def decode_reid_embedding_vector(embedding_data, dimensions=None):
  """Decode ReID embedding payload into a (1, N) float32 ndarray."""
  if isinstance(embedding_data, str):
    vector = base64.b64decode(embedding_data, validate=True)
    if len(vector) % REID_FLOAT_SIZE_BYTES != 0:
      raise ValueError(
        f"Packed ReID vector size {len(vector)} is not divisible by {REID_FLOAT_SIZE_BYTES}")

    inferred_dimensions = len(vector) // REID_FLOAT_SIZE_BYTES
    if dimensions is None:
      dimensions = inferred_dimensions
    elif int(dimensions) != inferred_dimensions:
      raise ValueError(
        f"Packed ReID vector contains {inferred_dimensions} floats, expected {dimensions}")

    return np.frombuffer(vector, dtype=np.float32).copy().reshape(1, dimensions)

  if isinstance(embedding_data, (np.ndarray, list)):
    arr = np.asarray(embedding_data, dtype=np.float32).reshape(-1)
    actual_length = arr.shape[0]
    if dimensions is not None and int(dimensions) != actual_length:
      raise ValueError(
        f"ReID embedding vector has {actual_length} elements, expected {int(dimensions)}")
    return arr.reshape(1, actual_length)

  return None


def serialize_reid_payload(reid):
  """Serialize ReID payload with base64 embedding and explicit dimensions."""
  if reid is None:
    return None

  if isinstance(reid, dict):
    serialized = dict(reid)
    embedding_data = serialized.get('embedding_vector', None)
    if embedding_data is None:
      return serialized

    if isinstance(embedding_data, str):
      try:
        if REID_EMBEDDING_DIMENSIONS_KEY not in serialized and 'dimensions' not in serialized:
          vector = base64.b64decode(embedding_data)
          if len(vector) % REID_FLOAT_SIZE_BYTES != 0:
            raise ValueError(
              f"Packed ReID vector size {len(vector)} is not divisible by {REID_FLOAT_SIZE_BYTES}")
          serialized[REID_EMBEDDING_DIMENSIONS_KEY] = len(vector) // REID_FLOAT_SIZE_BYTES
      except (binascii.Error, TypeError, ValueError) as err:
        log.warning(f"Failed to decode ReID embedding vector: {err}. Setting embedding_vector to None.")
        serialized['embedding_vector'] = None
      return serialized

    flat_vector = np.asarray(embedding_data, dtype=np.float32).reshape(-1)
    serialized['embedding_vector'] = base64.b64encode(flat_vector.tobytes()).decode('utf-8')
    serialized[REID_EMBEDDING_DIMENSIONS_KEY] = int(flat_vector.size)
    return serialized

  if isinstance(reid, (np.ndarray, list)):
    flat_vector = np.asarray(reid, dtype=np.float32).reshape(-1)
    return {
      'embedding_vector': base64.b64encode(flat_vector.tobytes()).decode('utf-8'),
      REID_EMBEDDING_DIMENSIONS_KEY: int(flat_vector.size),
    }

  return reid
