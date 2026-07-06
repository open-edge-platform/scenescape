# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Backward-compatible exports for VDMS ReID adapter."""

from controller.reid_uuid.vdms_adapter import COSINE_SIMILARITY_TOLERANCE
from controller.reid_uuid.vdms_adapter import DEFAULT_CA_CERT
from controller.reid_uuid.vdms_adapter import DEFAULT_CLIENT_CERT
from controller.reid_uuid.vdms_adapter import DEFAULT_CLIENT_KEY
from controller.reid_uuid.vdms_adapter import DEFAULT_CONFIDENCE_THRESHOLD
from controller.reid_uuid.vdms_adapter import DEFAULT_HOSTNAME
from controller.reid_uuid.vdms_adapter import DIMENSIONS
from controller.reid_uuid.vdms_adapter import K_NEIGHBORS
from controller.reid_uuid.vdms_adapter import SCHEMA_NAME
from controller.reid_uuid.vdms_adapter import SIMILARITY_METRIC
from controller.reid_uuid.vdms_adapter import VDMSDatabase
from controller.reid_uuid.vdms_adapter import vdms

__all__ = [
  'COSINE_SIMILARITY_TOLERANCE',
  'DEFAULT_CA_CERT',
  'DEFAULT_CLIENT_CERT',
  'DEFAULT_CLIENT_KEY',
  'DEFAULT_CONFIDENCE_THRESHOLD',
  'DEFAULT_HOSTNAME',
  'DIMENSIONS',
  'K_NEIGHBORS',
  'SCHEMA_NAME',
  'SIMILARITY_METRIC',
  'VDMSDatabase',
  'vdms',
]
