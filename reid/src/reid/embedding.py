# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Decode scene-track ReID payloads using shared embedding wire-format helpers."""

import binascii

from scene_common.reid_embedding import (
  REID_EMBEDDING_DIMENSIONS_KEY as REID_EMBEDDING_DIMENSIONS_KEY,
  REID_EMBEDDING_DIMENSION_KEYS as REID_EMBEDDING_DIMENSION_KEYS,
  REID_FLOAT_SIZE_BYTES as REID_FLOAT_SIZE_BYTES,
  decode_embedding_vector,
  get_embedding_dimensions as _embedding_dimensions,
)
from scene_common.reid_constants import REID_PROVENANCE_KEY


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
