# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Exceptions raised by the DL Streamer Pipeline Server 2.0 client."""

from typing import Any, Optional


class DLSPSError(Exception):
  """Base error for failed DLSPS requests or unexpected DLSPS responses.

  Attributes:
    status_code: HTTP status returned by DLSPS, or None when no response was received.
    detail: The ``detail`` field of the DLSPS error body (or raw text), if available.
  """

  def __init__(self, message: str, status_code: Optional[int] = None, detail: Any = None):
    super().__init__(message)
    self.status_code = status_code
    self.detail = detail


class DLSPSBadRequestError(DLSPSError):
  """DLSPS rejected the request body (HTTP 400 or 422)."""


class DLSPSNotFoundError(DLSPSError):
  """The pipeline instance does not exist (HTTP 404)."""


class DLSPSConflictError(DLSPSError):
  """The pipeline instance is not in a state that allows the operation (HTTP 409)."""


class DLSPSUnavailableError(DLSPSError):
  """DLSPS is unreachable, timed out, or not initialized (HTTP 503)."""
