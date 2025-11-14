# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from enum import IntEnum

class PipelineGenerationNotImplementedError(NotImplementedError):
  pass

class PipelineGenerationValueError(ValueError):
  pass

class InferenceRegion(IntEnum):
  FULL_FRAME = 0
  ROI_LIST = 1
