# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Registry mapping REID_DATABASE names to ReIDDatabase adapters.

Adapter modules are imported lazily so a deployment only pays for the client
library of the backend it selects.
"""

from importlib import import_module

from controller.reid_env import get_reid_database

# Backend name -> (module path, adapter class name). Register new backends here;
# no other production module needs to know the set of available adapters.
_BACKENDS = {
  "VDMS": ("controller.vdms_adapter", "VDMSDatabase"),
  "QDRANT": ("controller.qdrant_adapter", "QdrantDatabase"),
}


def supported_backends():
  """Return the sorted list of registered backend names."""
  return sorted(_BACKENDS)


def normalize_backend_name(name=None):
  """Return the canonical backend name, falling back to REID_DATABASE."""
  if name is None:
    name = get_reid_database()
  normalized = str(name).strip().upper()
  if normalized not in _BACKENDS:
    raise ValueError(
      f"Unsupported REID database '{normalized}'. "
      f"Supported values: {supported_backends()}")
  return normalized


def get_reid_database_class(name=None):
  """Return the adapter class for a backend, importing its module on demand."""
  normalized = normalize_backend_name(name)
  module_path, class_name = _BACKENDS[normalized]
  try:
    module = import_module(module_path)
  except ImportError as error:
    raise ImportError(
      f"ReID backend '{normalized}' needs '{module_path}', which failed to "
      f"import ({error}). Install the client library for this backend or set "
      f"REID_DATABASE to one of: {supported_backends()}") from error
  return getattr(module, class_name)


def create_reid_database(name=None, **kwargs):
  """Instantiate the adapter for a backend with the given constructor kwargs."""
  return get_reid_database_class(name)(**kwargs)
