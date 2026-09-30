# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Safety-hardened server-side helper for querying the ohsome API (HeiGIT).

Fetches OSM road/footway geometries for a scene's map bounding box.
Requires an ohsome API key: sign up at https://account.heigit.org/signup
and set it in the OHSOME_API_KEY environment variable.

Security controls (see .github/skills/security/SKILL.md):
- Endpoint is restricted to an HTTPS allow-list; no user-supplied URLs.
- The ohsome filter string is a fixed constant; no free-form/user-controlled
  text is ever concatenated into it (no filter-injection surface).
- The bbox is re-validated (range + max span) here regardless of what the
  browser sent; client input is never trusted as-is.
- API key is read only from the OHSOME_API_KEY environment variable; never
  hardcoded or logged.
- Responses are read with a hard size cap to avoid resource exhaustion.
- TLS certificate verification is never disabled.
- Requests are throttled and retried with bounded attempts/backoff.
"""

import io
import logging
import os
import time

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import pandas as pd
import requests
from shapely import wkb

logger = logging.getLogger(__name__)

# Publicly documented ohsome API instance; arbitrary/user-supplied endpoints
# are always rejected.
ALLOWED_OHSOME_ENDPOINTS = (
  "https://api.heigit.org/ohsome-api/v2-rc",
)
DEFAULT_ENDPOINT = ALLOWED_OHSOME_ENDPOINTS[0]
EXTRACTION_PATH = "/extraction/features.parquet"

# Fixed, non-user-controlled ohsome filter (see docs.ohsome.org/.../filter.html).
ROAD_FILTER = "type:way and (highway=* or footway=*)"

API_KEY_ENV_VAR = "OHSOME_API_KEY"
USER_AGENT = "scenescape-manager-osm-query/0.1 (+https://github.com/open-edge-platform/scenescape)"

REQUEST_TIMEOUT_S = 30
MAX_RESPONSE_BYTES = 10 * 1024 * 1024
MIN_REQUEST_INTERVAL_S = 1.0
MAX_RETRIES = 3
RETRY_BACKOFF_S = 2.0
MAX_BBOX_SPAN_DEG = 0.05  # ~5.5km at the equator; keeps queries/responses small
MAX_SAMPLE_FEATURES = 10
MAX_ROI_FEATURES = 100  # safety cap on raw ways processed for geometry extraction

_last_request_time = 0.0


class OsmQueryError(Exception):
  """Raised when an ohsome request cannot be safely built or completed."""


@dataclass(frozen=True)
class BoundingBox:
  south: float
  west: float
  north: float
  east: float

  def as_aoi(self) -> List[float]:
    # ohsome's AOI order is [xmin, ymin, xmax, ymax] i.e. [west, south, east, north].
    return [self.west, self.south, self.east, self.north]


def validate_bbox(south: float, west: float, north: float, east: float) -> BoundingBox:
  """Re-validate a browser-supplied bbox; never trust it as-is."""
  values = (south, west, north, east)
  if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in values):
    raise OsmQueryError("bbox values must be numeric")
  if not (-90.0 <= south <= 90.0) or not (-90.0 <= north <= 90.0):
    raise OsmQueryError("latitude out of range [-90, 90]")
  if not (-180.0 <= west <= 180.0) or not (-180.0 <= east <= 180.0):
    raise OsmQueryError("longitude out of range [-180, 180]")
  if south >= north:
    raise OsmQueryError("south must be less than north")
  if west >= east:
    raise OsmQueryError("west must be less than east")
  if (north - south) > MAX_BBOX_SPAN_DEG or (east - west) > MAX_BBOX_SPAN_DEG:
    raise OsmQueryError(f"bbox span exceeds max allowed of {MAX_BBOX_SPAN_DEG} degrees")
  return BoundingBox(south=south, west=west, north=north, east=east)


def validate_endpoint(endpoint: str) -> str:
  """Ensure the ohsome endpoint is on the trusted, HTTPS-only allow-list."""
  if endpoint not in ALLOWED_OHSOME_ENDPOINTS:
    raise OsmQueryError(f"ohsome endpoint not in allow-list: {endpoint}")
  if urlparse(endpoint).scheme != "https":
    raise OsmQueryError(f"ohsome endpoint must use HTTPS: {endpoint}")
  return endpoint


def get_api_key() -> str:
  """Read the ohsome API key from the environment; never hardcode or log it."""
  api_key = os.environ.get(API_KEY_ENV_VAR)
  if not api_key:
    raise OsmQueryError(f"Missing ohsome API key: set the {API_KEY_ENV_VAR} environment variable")
  return api_key


def _throttle() -> None:
  """Enforce a minimum interval between requests to be a good API citizen."""
  global _last_request_time
  elapsed = time.monotonic() - _last_request_time
  if elapsed < MIN_REQUEST_INTERVAL_S:
    time.sleep(MIN_REQUEST_INTERVAL_S - elapsed)
  _last_request_time = time.monotonic()
  return


def _read_bounded(response: requests.Response) -> bytes:
  """Read a streamed response body, enforcing a max size to avoid resource exhaustion."""
  content_length = response.headers.get("Content-Length")
  if content_length is not None and int(content_length) > MAX_RESPONSE_BYTES:
    raise OsmQueryError(f"Response too large ({content_length} bytes)")

  chunks: List[bytes] = []
  total = 0
  for chunk in response.iter_content(chunk_size=65536):
    total += len(chunk)
    if total > MAX_RESPONSE_BYTES:
      raise OsmQueryError(f"Response exceeded max size of {MAX_RESPONSE_BYTES} bytes")
    chunks.append(chunk)
  return b"".join(chunks)


def query_osm_ways_geometry(
  south: float, west: float, north: float, east: float,
  endpoint: str = DEFAULT_ENDPOINT,
) -> List[Dict[str, Any]]:
  """Query ohsome for road/footway ways in a bbox and return geometry.

  Returns a list of dicts, each with keys:
    - "type": OSM road type (highway, footway, or fallback "way")
    - "coords": list of (lat, lng) tuples representing the line geometry    - "tags": dict of OSM tags for the way (e.g., width, lanes, footway, surface)
  If any way is a MultiLineString, it is split into one entry per sub-line,
  preserving the same tags/type for each.

  Raises OsmQueryError if the bbox is too large for geometry extraction or if
  the upstream request fails.
  """
  bbox = validate_bbox(south, west, north, east)
  endpoint = validate_endpoint(endpoint)
  api_key = get_api_key()
  aoi = bbox.as_aoi()
  body = {"aoi": aoi, "filter": ROAD_FILTER, "time": "latest", "clip": True}
  url = endpoint + EXTRACTION_PATH

  logger.info(f"Querying ohsome for geometries: url={url} aoi={aoi}")

  last_error: Optional[Exception] = None
  for attempt in range(1, MAX_RETRIES + 1):
    _throttle()
    try:
      response = requests.post(
        url,
        json=body,
        headers={"Authorization": api_key, "User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_S,
        stream=True,
      )
      response.raise_for_status()
      content = _read_bounded(response)
      features_df = pd.read_parquet(io.BytesIO(content))
      ways = features_df[features_df["osm_type"] == "way"]

      if len(ways) > MAX_ROI_FEATURES:
        raise OsmQueryError(
          f"Query returned {len(ways)} ways, exceeding limit of {MAX_ROI_FEATURES}. "
          "Please shrink the bounding box."
        )

      results = []
      for _, row in ways.iterrows():
        tags = row.get("tags") or {}
        way_type = _feature_type(tags)
        geom_bytes = row.get("geom")
        if geom_bytes is None:
          continue

        try:
          geom = wkb.loads(geom_bytes)
        except Exception as exc:
          logger.warning(f"Failed to decode WKB geometry for way {row.get('osm_id')}: {exc}")
          continue

        # Handle both LineString and MultiLineString
        if geom.geom_type == "LineString":
          coords = [(lat, lng) for lng, lat in geom.coords]
          results.append({"type": way_type, "coords": coords, "tags": tags})
        elif geom.geom_type == "MultiLineString":
          for line in geom.geoms:
            coords = [(lat, lng) for lng, lat in line.coords]
            results.append({"type": way_type, "coords": coords, "tags": tags})

      logger.info(
        f"ohsome geometry query succeeded: url={url} way_count={len(ways)} "
        f"geometry_count={len(results)}"
      )
      return results

    except (requests.RequestException, OsmQueryError, OSError, ValueError) as exc:
      last_error = exc
      logger.warning(f"ohsome request attempt {attempt}/{MAX_RETRIES} failed: url={url} error={exc}")
      if attempt < MAX_RETRIES:
        time.sleep(RETRY_BACKOFF_S * attempt)

  raise OsmQueryError(f"ohsome geometry query failed after {MAX_RETRIES} attempts: {last_error}")

