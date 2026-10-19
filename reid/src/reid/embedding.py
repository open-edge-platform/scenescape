# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Decode the ``metadata.reid`` payload carried on scene tracks.

Mirrors ``controller.moving_object.decodeReIDEmbeddingVector`` so reid-service
does not import the Controller (and its OpenCV/Open3D dependencies) just to
read an embedding. Keep the two in sync until the Controller path is deleted.
"""

import base64
import binascii

import numpy as np

from scene_common.reid_constants import REID_PROVENANCE_KEY

REID_FLOAT_SIZE_BYTES = np.dtype(np.float32).itemsize
REID_EMBEDDING_DIMENSIONS_KEY = "embedding_dimensions"


def _embedding_dimensions(reid):
  if not isinstance(reid, dict):
    return None
  for key in (REID_EMBEDDING_DIMENSIONS_KEY, "dimensions"):
    value = reid.get(key)
    if value is None:
      continue
    try:
      return int(value)
    except (TypeError, ValueError) as err:
      raise ValueError(f"Invalid ReID embedding dimensions: {value}") from err
  return None


def decode_embedding_vector(embedding_data, dimensions=None):
  """Return a (1, N) float32 array from a base64 string or a (nested) list."""
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


def decode_reid_payload(reid):
  """
  Decode a ``metadata.reid`` value.

  @param   reid  dict with ``embedding_vector`` (base64 or list), or a legacy
                 bare base64 string / list
  @return  (embedding, provenance)  embedding is a (1, N) ndarray or None;
                                    provenance is a dict or None
  @raises  ValueError on a malformed embedding
  """
  if reid is None:
    return None, None
  try:
    if isinstance(reid, dict):
      if "embedding_vector" not in reid:
        return None, None
      provenance = reid.get(REID_PROVENANCE_KEY)
      provenance = dict(provenance) if isinstance(provenance, dict) else None
      embedding = decode_embedding_vector(
        reid["embedding_vector"], _embedding_dimensions(reid))
      return embedding, provenance
    return decode_embedding_vector(reid), None
  except (TypeError, binascii.Error) as err:
    raise ValueError(f"Malformed ReID embedding: {err}") from err
