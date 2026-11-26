# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""OCB1: a tiny named-array container shared by the Python and C++ tests.

Layout (little endian)::

  magic   "OCB1"
  u32     entry count
  entry*: u16 name_len, name (utf-8), u8 dtype, u8 ndim, u64 dims[ndim],
          u64 nbytes, zero padding to 8-byte file alignment, raw C-order data

Entries are sorted by name, so equal contents give equal bytes. The `meta.json` entry
holds utf-8 JSON describing the scenarios and where the data came from.
"""

import json
import struct
from pathlib import Path

import numpy as np

MAGIC = b"OCB1"
DTYPE_CODES = {
  np.dtype("<f4"): 1, np.dtype("<f8"): 2, np.dtype("u1"): 3,
  np.dtype("<u4"): 4, np.dtype("<i4"): 5, np.dtype("<i8"): 6, np.dtype("<u2"): 7,
}
CODE_DTYPES = {code: dtype for dtype, code in DTYPE_CODES.items()}
META_KEY = "meta.json"


def _pad(offset):
  return (-offset) % 8


def write_ocb(path, arrays, meta):
  """Write `arrays` (name -> ndarray) and the JSON-serializable `meta`."""
  entries = dict(arrays)
  entries[META_KEY] = np.frombuffer(
    json.dumps(meta, sort_keys=True, separators=(",", ":")).encode("utf-8"), dtype="u1")
  out = bytearray(MAGIC + struct.pack("<I", len(entries)))
  for name in sorted(entries):
    array = np.ascontiguousarray(entries[name])
    dtype = array.dtype.newbyteorder("<")
    if dtype not in DTYPE_CODES:
      raise TypeError(f"{name}: unsupported dtype {array.dtype}")
    raw = name.encode("utf-8")
    out += struct.pack("<H", len(raw)) + raw
    out += struct.pack("<BB", DTYPE_CODES[dtype], array.ndim)
    out += b"".join(struct.pack("<Q", dim) for dim in array.shape)
    out += struct.pack("<Q", array.nbytes)
    out += b"\0" * _pad(len(out))
    out += array.astype(dtype, copy=False).tobytes()
  Path(path).write_bytes(bytes(out))


def read_ocb(path):
  """Return (arrays, meta); arrays are read-only views keyed by name."""
  data = Path(path).read_bytes()
  if data[:4] != MAGIC:
    raise ValueError(f"{path}: not an OCB1 file")
  (count,) = struct.unpack_from("<I", data, 4)
  offset = 8
  arrays = {}
  for _ in range(count):
    (name_len,) = struct.unpack_from("<H", data, offset)
    offset += 2
    name = data[offset:offset + name_len].decode("utf-8")
    offset += name_len
    code, ndim = struct.unpack_from("<BB", data, offset)
    offset += 2
    shape = struct.unpack_from(f"<{ndim}Q", data, offset)
    offset += 8 * ndim
    (nbytes,) = struct.unpack_from("<Q", data, offset)
    offset += 8
    offset += _pad(offset)
    dtype = CODE_DTYPES[code]
    arrays[name] = np.frombuffer(
      data, dtype=dtype, count=nbytes // dtype.itemsize, offset=offset).reshape(shape)
    offset += nbytes
  meta = json.loads(arrays.pop(META_KEY).tobytes().decode("utf-8"))
  return arrays, meta
