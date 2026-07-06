# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Backward-compatible exports for UUID manager lifecycle logic."""

from controller.reid_uuid.uuid_manager import DEFAULT_DATABASE
from controller.reid_uuid.uuid_manager import DEFAULT_FEATURE_SLICE_SIZE
from controller.reid_uuid.uuid_manager import DEFAULT_MAX_QUERY_TIME
from controller.reid_uuid.uuid_manager import DEFAULT_MAX_SIMILARITY_QUERIES_TRACKED
from controller.reid_uuid.uuid_manager import DEFAULT_MINIMUM_BBOX_AREA
from controller.reid_uuid.uuid_manager import DEFAULT_MINIMUM_FEATURE_COUNT
from controller.reid_uuid.uuid_manager import DEFAULT_SIMILARITY_METRIC
from controller.reid_uuid.uuid_manager import DEFAULT_SIMILARITY_THRESHOLD_COSINE
from controller.reid_uuid.uuid_manager import DEFAULT_SIMILARITY_THRESHOLD_L2
from controller.reid_uuid.uuid_manager import DEFAULT_STALE_FEATURE_CHECK_INTERVAL_SECS
from controller.reid_uuid.uuid_manager import DEFAULT_STALE_FEATURE_TIMEOUT_SECS
from controller.reid_uuid.uuid_manager import SUPPORTED_SIMILARITY_METRICS
from controller.reid_uuid.uuid_manager import UUIDManager
from controller.reid_uuid.vdms_adapter import COSINE_SIMILARITY_TOLERANCE
from controller.reid_uuid.vdms_adapter import VDMSDatabase


__all__ = [
  'COSINE_SIMILARITY_TOLERANCE',
  'DEFAULT_DATABASE',
  'DEFAULT_FEATURE_SLICE_SIZE',
  'DEFAULT_MAX_QUERY_TIME',
  'DEFAULT_MAX_SIMILARITY_QUERIES_TRACKED',
  'DEFAULT_MINIMUM_BBOX_AREA',
  'DEFAULT_MINIMUM_FEATURE_COUNT',
  'DEFAULT_SIMILARITY_METRIC',
  'DEFAULT_SIMILARITY_THRESHOLD_COSINE',
  'DEFAULT_SIMILARITY_THRESHOLD_L2',
  'DEFAULT_STALE_FEATURE_CHECK_INTERVAL_SECS',
  'DEFAULT_STALE_FEATURE_TIMEOUT_SECS',
  'SUPPORTED_SIMILARITY_METRICS',
  'UUIDManager',
  'VDMSDatabase',
]
