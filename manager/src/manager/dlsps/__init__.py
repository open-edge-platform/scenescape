# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Manager adapter for the DL Streamer Pipeline Server 2.0 (DLSPS) REST API."""

from .client import DLSPS_URL_ENV, DLSPSClient
from .exceptions import (
  DLSPSBadRequestError,
  DLSPSConflictError,
  DLSPSError,
  DLSPSNotFoundError,
  DLSPSUnavailableError,
)
from .schemas import (
  PipelineState,
  PipelineStatus,
  PipelineSummary,
  RestartConfig,
  StartPipelineRequest,
)

__all__ = [
  'DLSPS_URL_ENV',
  'DLSPSClient',
  'DLSPSBadRequestError',
  'DLSPSConflictError',
  'DLSPSError',
  'DLSPSNotFoundError',
  'DLSPSUnavailableError',
  'PipelineState',
  'PipelineStatus',
  'PipelineSummary',
  'RestartConfig',
  'StartPipelineRequest',
]
