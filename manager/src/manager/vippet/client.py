# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""REST client used by Manager to pull vision pipeline definitions from ViPPET."""

import os
import re
from http import HTTPStatus
from typing import Any, Dict, List, Optional, Union
from urllib.parse import quote, urlparse

import requests

from scene_common import log

from .exceptions import (
  ViPPETBadRequestError,
  ViPPETError,
  ViPPETNotFoundError,
  ViPPETUnavailableError,
)
from .schemas import (
  PipelineSummary,
  is_vision_pipeline,
  parse_pipeline_description,
  parse_variant_graph,
)

VIPPET_URL_ENV = "VIPPET_URL"
DEFAULT_TIMEOUT = 10
MAX_ERROR_DETAIL_LENGTH = 512
MAX_ID_LENGTH = 128

_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]+")

_ERRORS_BY_STATUS = {
  HTTPStatus.BAD_REQUEST: ViPPETBadRequestError,
  HTTPStatus.UNPROCESSABLE_ENTITY: ViPPETBadRequestError,
  HTTPStatus.NOT_FOUND: ViPPETNotFoundError,
  HTTPStatus.SERVICE_UNAVAILABLE: ViPPETUnavailableError,
}


class ViPPETClient:
  """Client for pulling vision pipeline definitions from the ViPPET REST API.

  ViPPET stores each pipeline as a graph per hardware variant and renders the GStreamer
  launch string on demand, so ``get_pipelines`` is a single cheap call and
  ``get_pipeline_string`` resolves one variant at a time. Time-series pipelines are never
  exposed. Non-2xx responses raise ``ViPPETError`` subclasses; invalid arguments raise
  ``ValueError`` before any request is sent.
  """

  def __init__(self, base_url: Optional[str] = None, timeout: float = DEFAULT_TIMEOUT,
               verify: Union[bool, str] = True, session: Optional[requests.Session] = None):
    """
    Args:
      base_url: ViPPET API root including its ``/api/v1`` prefix
        (e.g. ``http://vippet:7860/api/v1``). Defaults to ``$VIPPET_URL``.
      timeout: Per-request timeout in seconds.
      verify: TLS verification flag or CA bundle path (only relevant for https URLs).
      session: Optional pre-configured ``requests.Session`` (e.g. for tests).

    Raises:
      ValueError: No base URL is configured or it is not an http(s) URL.
    """
    self.base_url = _resolve_base_url(base_url)
    self.timeout = timeout
    self.verify = verify
    self.session = session if session is not None else requests.Session()

  def __enter__(self) -> "ViPPETClient":
    return self

  def __exit__(self, *exc_info) -> None:
    self.close()

  def close(self) -> None:
    """Release pooled HTTP connections held by the underlying session."""
    self.session.close()

  def get_pipelines(self) -> List[PipelineSummary]:
    """Return all vision pipelines known to ViPPET (``GET /pipelines``), without strings."""
    data = self._request("GET", "/pipelines")
    if not isinstance(data, list):
      raise ViPPETError(f"Expected a list of pipelines, got {type(data).__name__}")
    return [PipelineSummary.from_dict(item) for item in data if is_vision_pipeline(item)]

  def get_pipeline_string(self, pipeline_id: str, variant_id: str) -> str:
    """Return the GStreamer launch string of one pipeline variant.

    Fetches the pipeline (``GET /pipelines/{id}``) and converts the variant's advanced graph
    with ``POST /convert/to-description``. The string is returned verbatim, ready to be
    stored or submitted to DLSPS ``POST /pipelines``.

    Raises:
      ValueError: ``pipeline_id`` or ``variant_id`` is not a valid ViPPET identifier.
      ViPPETNotFoundError: Unknown pipeline or variant, or the pipeline is not a vision pipeline.
      ViPPETBadRequestError: ViPPET could not convert the variant graph.
    """
    path = f"/pipelines/{quote(_validate_id(pipeline_id, 'pipeline_id'), safe='')}"
    _validate_id(variant_id, "variant_id")

    pipeline = self._request("GET", path)
    if not is_vision_pipeline(pipeline):
      raise ViPPETNotFoundError(f"ViPPET pipeline {pipeline_id!r} is not a vision pipeline")
    graph = parse_variant_graph(pipeline, variant_id)
    pipeline_string = parse_pipeline_description(
      self._request("POST", "/convert/to-description", json=graph))
    # The string itself is not logged: it may embed source URIs with credentials.
    log.info(f"Resolved GStreamer string for ViPPET pipeline {pipeline_id} variant {variant_id}")
    return pipeline_string

  def _request(self, method: str, path: str, json: Optional[Dict[str, Any]] = None) -> Any:
    url = f"{self.base_url}{path}"
    try:
      response = self.session.request(method, url, json=json, timeout=self.timeout,
                                      verify=self.verify)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
      raise ViPPETUnavailableError(f"ViPPET {method} {path} failed: {e}") from e
    except requests.exceptions.RequestException as e:
      raise ViPPETError(f"ViPPET {method} {path} failed: {e}") from e

    if not response.ok:
      raise _error_from_response(method, path, response)
    try:
      return response.json()
    except ValueError as e:
      raise ViPPETError(f"ViPPET {method} {path} returned invalid JSON",
                        status_code=response.status_code) from e


def _resolve_base_url(base_url: Optional[str]) -> str:
  url = (base_url or os.getenv(VIPPET_URL_ENV) or "").strip()
  if not url:
    raise ValueError(f"ViPPET base URL is not configured: pass base_url or set ${VIPPET_URL_ENV}")
  parsed = urlparse(url)
  # The URL itself is not echoed because it may contain credentials.
  if parsed.scheme not in ("http", "https") or not parsed.netloc:
    raise ValueError("ViPPET base URL must be an absolute http(s) URL")
  if parsed.query or parsed.fragment:
    raise ValueError("ViPPET base URL must not contain a query string or fragment")
  return url.rstrip("/")


def _validate_id(value: Any, name: str) -> str:
  """Allow only ViPPET slug-style ids so a caller-supplied id cannot alter the request path."""
  if not isinstance(value, str):
    raise ValueError(f"{name} must be a string, got {type(value).__name__}")
  valid = 0 < len(value) <= MAX_ID_LENGTH and value not in (".", "..")
  if not valid or not _ID_PATTERN.fullmatch(value):
    raise ValueError(f"{name} must be 1-{MAX_ID_LENGTH} characters of [A-Za-z0-9._-]")
  return value


def _error_from_response(method: str, path: str, response: requests.Response) -> ViPPETError:
  detail = _extract_error_detail(response)
  error_cls = _ERRORS_BY_STATUS.get(response.status_code, ViPPETError)
  return error_cls(f"ViPPET {method} {path} failed with HTTP {response.status_code}: {detail}",
                   status_code=response.status_code, detail=detail)


def _extract_error_detail(response: requests.Response) -> Any:
  """Return ViPPET's ``message`` or FastAPI's ``detail`` field, else the (truncated) body."""
  try:
    body = response.json()
  except ValueError:
    return response.text[:MAX_ERROR_DETAIL_LENGTH]
  if isinstance(body, dict):
    for key in ("message", "detail"):
      if key in body:
        return body[key]
  return body
