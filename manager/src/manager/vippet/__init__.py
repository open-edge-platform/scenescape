# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Manager client library for pulling pipeline definitions from ViPPET.

ViPPET (Visual Pipeline and Platform Evaluation Tool) is where pipelines are authored.
Manager consumes only vision pipelines and only their GStreamer launch strings.
"""

from .client import VIPPET_URL_ENV, ViPPETClient
from .exceptions import (
  ViPPETBadRequestError,
  ViPPETError,
  ViPPETNotFoundError,
  ViPPETUnavailableError,
)
from .schemas import PipelineSummary, PipelineType, PipelineVariant

__all__ = [
  'VIPPET_URL_ENV',
  'ViPPETClient',
  'ViPPETBadRequestError',
  'ViPPETError',
  'ViPPETNotFoundError',
  'ViPPETUnavailableError',
  'PipelineSummary',
  'PipelineType',
  'PipelineVariant',
]
