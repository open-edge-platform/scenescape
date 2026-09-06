# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from scene_common.rest_client import RESTClient


@dataclass
class SceneScapeClients:
  """Composed REST clients for core and optional service endpoints."""

  core: RESTClient
  autocalibration: Optional[RESTClient] = None
  mapping: Optional[RESTClient] = None


def _add_source_paths(service_src_dirs):
  if not service_src_dirs:
    return

  for src_dir in service_src_dirs:
    p = Path(src_dir)
    if p.exists() and str(p) not in sys.path:
      sys.path.insert(0, str(p))


def _load_client_class(module_name, class_name):
  module = importlib.import_module(module_name)
  return getattr(module, class_name)


def create_scenescape_clients(
    base_url,
    token=None,
    auth=None,
    verify_ssl=False,
    timeout=10,
    include_autocalibration=True,
    include_mapping=True,
    service_src_dirs=None,
    strict_imports=False):
  """Create a composed set of Scenescape clients.

  This composes service-specific clients, but endpoint methods remain defined
  only in each service folder's client module.
  """
  _add_source_paths(service_src_dirs)

  clients = SceneScapeClients(
      core=RESTClient(
          url=f"{base_url}/api/v1",
          token=token,
          auth=auth,
          verify_ssl=verify_ssl,
          timeout=timeout,
      ),
  )

  if include_autocalibration:
    try:
      auto_cls = _load_client_class(
          "autocalibration_client", "AutoCalibrationClient")
      clients.autocalibration = auto_cls(
          url=f"{base_url}/api/v1/autocalibration",
          token=token,
          auth=auth,
          verify_ssl=verify_ssl,
          timeout=timeout,
      )
    except Exception:
      if strict_imports:
        raise

  if include_mapping:
    try:
      mapping_cls = _load_client_class("mapping_client", "MappingClient")
      clients.mapping = mapping_cls(
          url=f"{base_url}/api/v1/mapping/",
          token=token,
          auth=auth,
          verify_ssl=verify_ssl,
          timeout=timeout,
      )
    except Exception:
      if strict_imports:
        raise

  return clients
