# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Typed representations of DL Streamer Pipeline Server 2.0 REST payloads.

Response parsers ignore unknown keys so that additive changes in the alpha API
do not break Manager, but they fail visibly on missing or mistyped core fields.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from .exceptions import DLSPSError


class PipelineState(str, Enum):
  """Lifecycle state of a DLSPS pipeline instance."""

  QUEUED = "QUEUED"
  RUNNING = "RUNNING"
  RESTARTING = "RESTARTING"
  COMPLETED = "COMPLETED"
  ERROR = "ERROR"
  ABORTED = "ABORTED"


def _require_int(value: Any, name: str, minimum: int) -> int:
  if isinstance(value, bool) or not isinstance(value, int):
    raise ValueError(f"{name} must be an integer, got {type(value).__name__}")
  if value < minimum:
    raise ValueError(f"{name} must be >= {minimum}, got {value}")
  return value


@dataclass(frozen=True)
class RestartConfig:
  """Automatic restart policy applied by DLSPS on pipeline error or EOS."""

  enabled: bool
  max_attempts: int = 5
  backoff_seconds: int = 30

  def __post_init__(self):
    if not isinstance(self.enabled, bool):
      raise ValueError("enabled must be a boolean")
    _require_int(self.max_attempts, "max_attempts", 1)
    _require_int(self.backoff_seconds, "backoff_seconds", 0)

  def to_dict(self) -> Dict[str, Any]:
    """Return the JSON-serializable ``restart_config`` object."""
    return {
      "enabled": self.enabled,
      "max_attempts": self.max_attempts,
      "backoff_seconds": self.backoff_seconds,
    }


@dataclass(frozen=True)
class StartPipelineRequest:
  """Body of ``POST /pipelines``; ``pipeline`` is a gst-launch-1.0 string run as-is."""

  pipeline: str
  validate_pipeline: bool = True
  cpu_cores: Optional[Tuple[int, ...]] = None
  warmup_frames: int = 0
  restart_config: Optional[RestartConfig] = None

  def __post_init__(self):
    if not isinstance(self.pipeline, str) or not self.pipeline.strip():
      raise ValueError("pipeline must be a non-empty GStreamer launch string")
    if not isinstance(self.validate_pipeline, bool):
      raise ValueError("validate_pipeline must be a boolean")
    _require_int(self.warmup_frames, "warmup_frames", 0)
    if self.restart_config is not None and not isinstance(self.restart_config, RestartConfig):
      raise ValueError("restart_config must be a RestartConfig instance")
    if self.cpu_cores is not None:
      object.__setattr__(self, "cpu_cores", _parse_cpu_cores(self.cpu_cores))

  def to_dict(self) -> Dict[str, Any]:
    """Return the JSON request body, omitting unset optional fields."""
    body = {
      "pipeline": self.pipeline,
      "validate_pipeline": self.validate_pipeline,
      "warmup_frames": self.warmup_frames,
    }
    if self.cpu_cores is not None:
      body["cpu_cores"] = list(self.cpu_cores)
    if self.restart_config is not None:
      body["restart_config"] = self.restart_config.to_dict()
    return body


def _parse_cpu_cores(cpu_cores: Any) -> Tuple[int, ...]:
  if isinstance(cpu_cores, (str, bytes)) or not isinstance(cpu_cores, Iterable):
    raise ValueError("cpu_cores must be a sequence of CPU core indices")
  return tuple(_require_int(core, "cpu_cores item", 0) for core in cpu_cores)


@dataclass(frozen=True)
class PipelineStatus:  # pylint: disable=too-many-instance-attributes
  """Runtime status of a pipeline instance (``GET /pipelines/{id}/status``)."""

  id: str
  state: PipelineState
  avg_fps: float
  frame_fps: float
  frame_interval: float
  start_time: Optional[float]
  first_frame_time: Optional[float]
  elapsed_time: Optional[float]
  message: str

  @classmethod
  def from_dict(cls, data: Mapping) -> "PipelineStatus":
    """Build from a DLSPS JSON object; raises DLSPSError on malformed payloads."""
    return cls(**_parse_status_fields(data))


@dataclass(frozen=True)
class PipelineSummary(PipelineStatus):
  """Status plus configuration of a pipeline instance (``GET /pipelines/{id}``).

  ``name``, ``version`` and ``request`` are None for instances started via ``POST /pipelines``.
  """

  type: Optional[str] = None
  launch_command: Optional[str] = None
  name: Optional[str] = None
  version: Optional[str] = None
  request: Optional[Dict[str, Any]] = field(default=None, hash=False)

  @classmethod
  def from_dict(cls, data: Mapping) -> "PipelineSummary":
    status_fields = _parse_status_fields(data)
    request = data.get("request")
    if request is not None and not isinstance(request, Mapping):
      raise DLSPSError("Field 'request' must be an object")
    return cls(
      **status_fields,
      type=_parse_optional_str(data, "type"),
      launch_command=_parse_optional_str(data, "launch_command"),
      name=_parse_optional_str(data, "name"),
      version=_parse_optional_str(data, "version"),
      request=dict(request) if request is not None else None,
    )


def _parse_status_fields(data: Any) -> Dict[str, Any]:
  if not isinstance(data, Mapping):
    raise DLSPSError(f"Expected pipeline status object, got {type(data).__name__}")
  instance_id = data.get("id")
  if not isinstance(instance_id, str) or not instance_id:
    raise DLSPSError("Pipeline status is missing a valid 'id'")
  return {
    "id": instance_id,
    "state": _parse_state(data.get("state")),
    "avg_fps": _parse_number(data, "avg_fps", 0.0),
    "frame_fps": _parse_number(data, "frame_fps", 0.0),
    "frame_interval": _parse_number(data, "frame_interval", 0.0),
    "start_time": _parse_number(data, "start_time", None),
    "first_frame_time": _parse_number(data, "first_frame_time", None),
    "elapsed_time": _parse_number(data, "elapsed_time", None),
    "message": _parse_optional_str(data, "message") or "",
  }


def _parse_state(value: Any) -> PipelineState:
  try:
    return PipelineState(value)
  except ValueError as e:
    raise DLSPSError(f"Unknown pipeline state: {value!r}") from e


def _parse_number(data: Mapping, key: str, default: Optional[float]) -> Optional[float]:
  value = data.get(key)
  if value is None:
    return default
  if isinstance(value, bool) or not isinstance(value, (int, float)):
    raise DLSPSError(f"Field '{key}' must be a number, got {type(value).__name__}")
  return float(value)


def _parse_optional_str(data: Mapping, key: str) -> Optional[str]:
  value = data.get(key)
  if value is not None and not isinstance(value, str):
    raise DLSPSError(f"Field '{key}' must be a string, got {type(value).__name__}")
  return value
