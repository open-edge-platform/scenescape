# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Exceptions raised by the ViPPET client library."""

from typing import Any, Optional


class ViPPETError(Exception):
  """Base error for failed ViPPET requests or unexpected ViPPET responses.

  Attributes:
    status_code: HTTP status returned by ViPPET, or None when no response was received.
    detail: The ``message``/``detail`` field of the ViPPET error body (or raw text), if available.
  """

  def __init__(self, message: str, status_code: Optional[int] = None, detail: Any = None):
    super().__init__(message)
    self.status_code = status_code
    self.detail = detail


class ViPPETBadRequestError(ViPPETError):
  """ViPPET rejected the request (HTTP 400 or 422), e.g. a graph it cannot convert."""


class ViPPETNotFoundError(ViPPETError):
  """The pipeline or variant does not exist, or is not a vision pipeline."""


class ViPPETUnavailableError(ViPPETError):
  """ViPPET is unreachable, timed out, or still initializing (HTTP 503)."""
