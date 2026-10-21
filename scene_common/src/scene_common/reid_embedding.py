# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared ReID embedding wire-format decoding without Controller dependencies."""

import base64

import numpy as np

REID_FLOAT_SIZE_BYTES = np.dtype(np.float32).itemsize
REID_EMBEDDING_DIMENSIONS_KEY = "embedding_dimensions"
REID_EMBEDDING_DIMENSION_KEYS = (REID_EMBEDDING_DIMENSIONS_KEY, "dimensions")


def get_embedding_dimensions(reid):
  """Read the preferred dimension key, falling back to the legacy key."""
  if not isinstance(reid, dict):
    return None
  for key in REID_EMBEDDING_DIMENSION_KEYS:
    value = reid.get(key)
    if value is None:
      continue
    try:
      return int(value)
    except (TypeError, ValueError) as err:
      raise ValueError(f"Invalid ReID embedding dimensions: {value}") from err
  return None


def decode_embedding_vector(embedding_data, dimensions=None):
  """Return a (1, N) float32 array from a base64 string, list, or NumPy array."""
  if isinstance(embedding_data, str):
    vector = base64.b64decode(embedding_data, validate=True)
    if len(vector) % REID_FLOAT_SIZE_BYTES != 0:
      raise ValueError(
        f"Packed ReID vector size {len(vector)} is not divisible by "
        f"{REID_FLOAT_SIZE_BYTES}")
    inferred = len(vector) // REID_FLOAT_SIZE_BYTES
    if dimensions is None:
      dimensions = inferred
    elif int(dimensions) != inferred:
      raise ValueError(
        f"Packed ReID vector contains {inferred} floats, expected {dimensions}")
    return np.frombuffer(vector, dtype=np.float32).copy().reshape(1, dimensions)

  if isinstance(embedding_data, (np.ndarray, list)):
    arr = np.asarray(embedding_data, dtype=np.float32).reshape(-1)
    if dimensions is not None and int(dimensions) != arr.shape[0]:
      raise ValueError(
        f"ReID embedding vector has {arr.shape[0]} elements, "
        f"expected {int(dimensions)}")
    return arr.reshape(1, arr.shape[0])

  return None
