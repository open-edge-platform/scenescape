# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Pipeline generation module for SceneScape."""

from .common_types import PipelineGenerationNotImplementedError, PipelineGenerationValueError

# Lazy imports for classes that might have heavy dependencies
def __getattr__(name):
  if name == "PipelineConfigGenerator":
    from .config_generator import PipelineConfigGenerator
    return PipelineConfigGenerator
  elif name == "PipelineGenerator":
    from .pipeline_generator import PipelineGenerator
    return PipelineGenerator
  elif name == "generate_pipeline_string_from_dict":
    from .config_generator import generate_pipeline_string_from_dict
    return generate_pipeline_string_from_dict
  else:
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = [
  # Exceptions - lightweight, safe to import directly
  'PipelineGenerationNotImplementedError',
  'PipelineGenerationValueError',

  # Heavy dependency classes - imported lazily
  'PipelineConfigGenerator',
  'PipelineGenerator',
  'generate_pipeline_string_from_dict',
]
