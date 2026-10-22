# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Typed representations of the ViPPET REST payloads consumed by Manager.

Manager only needs pipeline metadata, variant identity and, on demand, the GStreamer
launch string of a variant. Graphs, thumbnails and timestamps are deliberately dropped.
Parsers ignore unknown keys so that additive ViPPET API changes do not break Manager,
but they fail visibly on missing or mistyped core fields.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Tuple

from .exceptions import ViPPETError, ViPPETNotFoundError


class PipelineType(str, Enum):
  """Kind of ViPPET pipeline; only vision pipelines are GStreamer pipelines usable by DLSPS."""

  VISION = "vision"
  TIME_SERIES = "time_series"


@dataclass(frozen=True)
class PipelineVariant:
  """Hardware-specific variant of a ViPPET pipeline (e.g. CPU, GPU, NPU)."""

  id: str
  name: str

  @classmethod
  def from_dict(cls, data: Any) -> "PipelineVariant":
    """Build from a ViPPET variant object; raises ViPPETError on malformed payloads."""
    _require_mapping(data, "pipeline variant")
    return cls(id=_require_str(data, "id"), name=_require_str(data, "name"))


@dataclass(frozen=True)
class PipelineSummary:
  """ViPPET pipeline metadata without graphs.

  Resolve the GStreamer launch string of a variant with
  ``ViPPETClient.get_pipeline_string(summary.id, variant.id)``.
  """

  id: str
  name: str
  description: str
  tags: Tuple[str, ...]
  variants: Tuple[PipelineVariant, ...]

  @classmethod
  def from_dict(cls, data: Any) -> "PipelineSummary":
    """Build from a ViPPET pipeline object; raises ViPPETError on malformed payloads."""
    _require_mapping(data, "pipeline")
    return cls(
      id=_require_str(data, "id"),
      name=_require_str(data, "name"),
      description=_optional_str(data, "description"),
      tags=_parse_tags(data.get("tags")),
      variants=tuple(PipelineVariant.from_dict(item) for item in _require_list(data, "variants")),
    )


def is_vision_pipeline(data: Any) -> bool:
  """Return True when a ViPPET pipeline object is a vision (GStreamer) pipeline.

  A missing ``type`` means vision, matching ViPPET's schema default. Unknown types are
  treated as non-vision so that new ViPPET pipeline kinds are hidden rather than misused.
  """
  _require_mapping(data, "pipeline")
  pipeline_type = data.get("type")
  if pipeline_type is None:
    return True
  if not isinstance(pipeline_type, str):
    raise ViPPETError(f"Field 'type' must be a string, got {type(pipeline_type).__name__}")
  return pipeline_type == PipelineType.VISION.value


def parse_variant_graph(pipeline: Any, variant_id: str) -> Dict[str, Any]:
  """Return the advanced ``pipeline_graph`` of ``variant_id`` from a ViPPET pipeline object.

  The graph is passed through unchanged to ViPPET's converter; only its envelope is checked.

  Raises:
    ViPPETNotFoundError: The pipeline has no variant with this id.
    ViPPETError: The pipeline or graph payload is malformed.
  """
  _require_mapping(pipeline, "pipeline")
  for variant in _require_list(pipeline, "variants"):
    _require_mapping(variant, "pipeline variant")
    if variant.get("id") != variant_id:
      continue
    graph = variant.get("pipeline_graph")
    if not isinstance(graph, Mapping):
      raise ViPPETError(f"Variant {variant_id!r} is missing a valid 'pipeline_graph'")
    _require_list(graph, "nodes")
    _require_list(graph, "edges")
    return dict(graph)
  raise ViPPETNotFoundError(f"ViPPET pipeline has no variant {variant_id!r}")


def parse_pipeline_description(data: Any) -> str:
  """Return the GStreamer launch string from a ViPPET ``PipelineDescription`` response."""
  _require_mapping(data, "pipeline description")
  description = data.get("pipeline_description")
  if not isinstance(description, str) or not description.strip():
    raise ViPPETError("ViPPET response is missing a non-empty 'pipeline_description'")
  return description


def _require_mapping(data: Any, what: str) -> None:
  if not isinstance(data, Mapping):
    raise ViPPETError(f"Expected {what} object, got {type(data).__name__}")


def _require_str(data: Mapping, key: str) -> str:
  value = data.get(key)
  if not isinstance(value, str) or not value:
    raise ViPPETError(f"Field '{key}' must be a non-empty string")
  return value


def _optional_str(data: Mapping, key: str) -> str:
  value = data.get(key)
  if value is None:
    return ""
  if not isinstance(value, str):
    raise ViPPETError(f"Field '{key}' must be a string, got {type(value).__name__}")
  return value


def _require_list(data: Mapping, key: str) -> list:
  value = data.get(key)
  if not isinstance(value, list):
    raise ViPPETError(f"Field '{key}' must be a list")
  return value


def _parse_tags(tags: Any) -> Tuple[str, ...]:
  if tags is None:
    return ()
  if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
    raise ViPPETError("Field 'tags' must be a list of strings")
  return tuple(tags)
