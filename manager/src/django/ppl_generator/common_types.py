# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from enum import IntEnum

# The custom exceptions are provided for full control over error messages
# and to avoid leakage of sensitive info to the user - we provide
# guarantee that no sensitive info will be included in these exceptions

# TODO: add a custom base class with a custom field for user message that
#       will be shown in the UI and derive other exceptions from it
class PipelineGenerationNotImplementedError(NotImplementedError):
  pass

class PipelineGenerationValueError(ValueError):
  pass

class InferenceRegion(IntEnum):
  FULL_FRAME = 0
  ROI_LIST = 1
