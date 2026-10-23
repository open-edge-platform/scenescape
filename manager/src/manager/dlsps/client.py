# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""REST client used by Manager to create, inspect and stop DLSPS 2.0 pipeline instances."""

import os
import uuid
from http import HTTPStatus
from typing import Any, Dict, List, Optional, Sequence, Union

import requests

from scene_common import log

from .exceptions import (
  DLSPSBadRequestError,
  DLSPSConflictError,
  DLSPSError,
  DLSPSNotFoundError,
  DLSPSUnavailableError,
)
from .schemas import PipelineStatus, PipelineSummary, RestartConfig, StartPipelineRequest

DLSPS_URL_ENV = "DLSPS_URL"
DEFAULT_DLSPS_URL = "http://dlstreamer-pipeline-server:8080"
DEFAULT_TIMEOUT = 10
MAX_ERROR_DETAIL_LENGTH = 512

_ERRORS_BY_STATUS = {
  HTTPStatus.BAD_REQUEST: DLSPSBadRequestError,
  HTTPStatus.UNPROCESSABLE_ENTITY: DLSPSBadRequestError,
  HTTPStatus.NOT_FOUND: DLSPSNotFoundError,
  HTTPStatus.CONFLICT: DLSPSConflictError,
  HTTPStatus.SERVICE_UNAVAILABLE: DLSPSUnavailableError,
}

InstanceId = Union[str, uuid.UUID]


class DLSPSClient:
  """Thin client for the DLSPS 2.0 pipeline instance API.

  Starting a pipeline returns immediately with an instance id while DLSPS validates and
  launches it in the background, so callers should poll ``get_pipeline_status`` to detect
  failures. Non-2xx responses are raised as ``DLSPSError`` subclasses; invalid arguments
  raise ``ValueError`` before any request is sent.
  """

  def __init__(self, base_url: Optional[str] = None, timeout: float = DEFAULT_TIMEOUT,
               verify: Union[bool, str] = True, session: Optional[requests.Session] = None):
    """
    Args:
      base_url: DLSPS root URL. Defaults to ``$DLSPS_URL``, then ``DEFAULT_DLSPS_URL``.
      timeout: Per-request timeout in seconds.
      verify: TLS verification flag or CA bundle path (only relevant for https URLs).
      session: Optional pre-configured ``requests.Session`` (e.g. for tests).
    """
    url = base_url or os.getenv(DLSPS_URL_ENV) or DEFAULT_DLSPS_URL
    self.base_url = url.rstrip("/")
    self.timeout = timeout
    self.verify = verify
    self.session = session if session is not None else requests.Session()

  def __enter__(self) -> "DLSPSClient":
    return self

  def __exit__(self, *exc_info) -> None:
    self.close()

  def close(self) -> None:
    """Release pooled HTTP connections held by the underlying session."""
    self.session.close()

  def create_pipeline(self, pipeline: str, *, validate_pipeline: bool = True,
                      cpu_cores: Optional[Sequence[int]] = None, warmup_frames: int = 0,
                      restart_config: Optional[RestartConfig] = None) -> str:
    """Start a pipeline instance from a gst-launch-1.0 string (``POST /pipelines``).

    Returns:
      The instance id (UUID string) assigned by DLSPS.
    """
    request = StartPipelineRequest(
      pipeline=pipeline,
      validate_pipeline=validate_pipeline,
      cpu_cores=cpu_cores,
      warmup_frames=warmup_frames,
      restart_config=restart_config,
    )
    instance_id = _parse_instance_id_response(
      self._request("POST", "/pipelines", json=request.to_dict()))
    log.info(f"DLSPS pipeline instance {instance_id} created")
    return instance_id

  def get_pipeline(self, instance_id: InstanceId) -> PipelineSummary:
    """Return status and configuration of a pipeline instance (``GET /pipelines/{id}``)."""
    path = f"/pipelines/{_normalize_instance_id(instance_id)}"
    return PipelineSummary.from_dict(self._request("GET", path))

  def get_pipeline_status(self, instance_id: InstanceId) -> PipelineStatus:
    """Return runtime status of a pipeline instance (``GET /pipelines/{id}/status``)."""
    path = f"/pipelines/{_normalize_instance_id(instance_id)}/status"
    return PipelineStatus.from_dict(self._request("GET", path))

  def list_pipeline_statuses(self) -> List[PipelineStatus]:
    """Return status of every pipeline instance known to DLSPS (``GET /pipelines/status``)."""
    data = self._request("GET", "/pipelines/status")
    if not isinstance(data, list):
      raise DLSPSError(f"Expected a list of pipeline statuses, got {type(data).__name__}")
    return [PipelineStatus.from_dict(item) for item in data]

  def delete_pipeline(self, instance_id: InstanceId) -> str:
    """Request a graceful stop of a RUNNING or RESTARTING instance (``DELETE /pipelines/{id}``).

    Raises:
      DLSPSConflictError: The instance is not RUNNING or RESTARTING (e.g. QUEUED, COMPLETED).

    Returns:
      The id of the instance that was asked to stop.
    """
    path = f"/pipelines/{_normalize_instance_id(instance_id)}"
    stopped_id = _parse_instance_id_response(self._request("DELETE", path))
    log.info(f"DLSPS pipeline instance {stopped_id} stop requested")
    return stopped_id

  def _request(self, method: str, path: str, json: Optional[Dict[str, Any]] = None) -> Any:
    url = f"{self.base_url}{path}"
    try:
      response = self.session.request(method, url, json=json, timeout=self.timeout,
                                      verify=self.verify)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
      raise DLSPSUnavailableError(f"DLSPS {method} {path} failed: {e}") from e
    except requests.exceptions.RequestException as e:
      raise DLSPSError(f"DLSPS {method} {path} failed: {e}") from e

    if not response.ok:
      raise _error_from_response(method, path, response)
    try:
      return response.json()
    except ValueError as e:
      raise DLSPSError(f"DLSPS {method} {path} returned invalid JSON",
                       status_code=response.status_code) from e


def _normalize_instance_id(instance_id: InstanceId) -> str:
  """Return the canonical UUID string; rejecting non-UUIDs keeps ids from altering the URL path."""
  if isinstance(instance_id, uuid.UUID):
    return str(instance_id)
  if not isinstance(instance_id, str):
    raise ValueError(f"instance_id must be a UUID string, got {type(instance_id).__name__}")
  try:
    return str(uuid.UUID(instance_id))
  except ValueError as e:
    raise ValueError(f"instance_id is not a valid UUID: {instance_id!r}") from e


def _parse_instance_id_response(data: Any) -> str:
  instance_id = data.get("instance_id") if isinstance(data, dict) else None
  if not isinstance(instance_id, str) or not instance_id:
    raise DLSPSError("DLSPS response is missing 'instance_id'")
  return instance_id


def _error_from_response(method: str, path: str, response: requests.Response) -> DLSPSError:
  detail = _extract_error_detail(response)
  error_cls = _ERRORS_BY_STATUS.get(response.status_code, DLSPSError)
  return error_cls(f"DLSPS {method} {path} failed with HTTP {response.status_code}: {detail}",
                   status_code=response.status_code, detail=detail)


def _extract_error_detail(response: requests.Response) -> Any:
  try:
    body = response.json()
  except ValueError:
    return response.text[:MAX_ERROR_DETAIL_LENGTH]
  if isinstance(body, dict) and "detail" in body:
    return body["detail"]
  return body
