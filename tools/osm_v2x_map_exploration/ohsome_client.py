# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Safety-hardened client for querying the ohsome API (HeiGIT).

Used by the "Explore V2X Map creation using OpenStreetMaps" feasibility spike
to pull road-network data (highway/footway ways) around fixed test sites
defined in test_sites.yaml.

Requires an ohsome API key: sign up at https://account.heigit.org/signup and
set it in the OHSOME_API_KEY environment variable. The key is never hardcoded
or logged.

Security controls (see .github/skills/security/SKILL.md):
- Endpoint is restricted to an HTTPS allow-list; no user-supplied URLs.
- The ohsome filter string is a fixed constant; no free-form/user-controlled
  text is ever concatenated into it (no filter-injection surface).
- Coordinates/radius are range- and type-validated before use (SSRF/garbage-
  input guard).
- API key is read only from the OHSOME_API_KEY environment variable.
- Responses are read with a hard size cap to avoid resource exhaustion.
- TLS certificate verification is never disabled.
- Requests are throttled and retried with bounded attempts/backoff.
"""

import io
import logging
import math
import os
import time

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import pandas as pd
import requests
import yaml
from shapely import wkb

logger = logging.getLogger(__name__)

_EARTH_METERS_PER_DEGREE = 111_320.0
MAX_RADIUS_M = 2000  # keeps bbox/query/response small regardless of yaml input


@dataclass(frozen=True)
class BoundingBox:
  south: float
  west: float
  north: float
  east: float

# Publicly documented ohsome API instance. Endpoint selection is restricted to
# this allow-list; arbitrary/user-supplied endpoints are always rejected.
ALLOWED_OHSOME_ENDPOINTS = (
  "https://api.heigit.org/ohsome-api/v2-rc",
)
DEFAULT_ENDPOINT = ALLOWED_OHSOME_ENDPOINTS[0]
EXTRACTION_PATH = "/extraction/features.parquet"

# Fixed, non-user-controlled ohsome filter (see docs.ohsome.org/.../filter.html).
# Selects way features tagged highway=* or footway=*.
ROAD_FILTER = "type:way and (highway=* or footway=*)"

API_KEY_ENV_VAR = "OHSOME_API_KEY"
USER_AGENT = "scenescape-osm-v2x-spike/0.1 (+https://github.com/open-edge-platform/scenescape)"

REQUEST_TIMEOUT_S = 30
MAX_RESPONSE_BYTES = 25 * 1024 * 1024  # hard cap, far above expected test-site payloads
MIN_REQUEST_INTERVAL_S = 1.0  # client-side throttle to be a good API citizen
MAX_RETRIES = 3
RETRY_BACKOFF_S = 2.0

_last_request_time = 0.0


class OhsomeError(Exception):
  """Raised when an ohsome API request cannot be safely built or completed."""


def validate_coordinates(lat: float, lng: float, radius_m: float) -> None:
  """Validate site coordinates/radius are well-formed and within safe bounds."""
  if isinstance(lat, bool) or isinstance(lng, bool) or \
     not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
    raise OhsomeError(f"lat/lng must be numeric, got lat={lat!r} lng={lng!r}")
  if not (-90.0 <= lat <= 90.0):
    raise OhsomeError(f"lat out of range [-90, 90]: {lat}")
  if not (-180.0 <= lng <= 180.0):
    raise OhsomeError(f"lng out of range [-180, 180]: {lng}")
  if isinstance(radius_m, bool) or not isinstance(radius_m, (int, float)) or radius_m <= 0:
    raise OhsomeError(f"radius_m must be a positive number: {radius_m!r}")
  if radius_m > MAX_RADIUS_M:
    raise OhsomeError(f"radius_m {radius_m} exceeds max allowed {MAX_RADIUS_M}")
  return


def bbox_from_center(lat: float, lng: float, radius_m: float) -> BoundingBox:
  """Derive a lat/lng bounding box from a center point and radius in meters."""
  validate_coordinates(lat, lng, radius_m)
  lat_delta = radius_m / _EARTH_METERS_PER_DEGREE
  lng_delta = radius_m / (_EARTH_METERS_PER_DEGREE * max(math.cos(math.radians(lat)), 1e-6))
  return BoundingBox(
    south=lat - lat_delta,
    west=lng - lng_delta,
    north=lat + lat_delta,
    east=lng + lng_delta,
  )


def load_test_sites(path: Path) -> List[Dict[str, Any]]:
  """Load candidate site definitions from test_sites.yaml."""
  with open(path) as f:
    data = yaml.safe_load(f)
  sites = data.get("sites") if isinstance(data, dict) else None
  if not isinstance(sites, list):
    raise OhsomeError(f"No 'sites' list found in {path}")
  return sites


def find_site(sites: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
  """Look up a site by its 'name' key."""
  for site in sites:
    if site.get("name") == name:
      return site
  raise OhsomeError(f"Unknown site '{name}', known sites: {[s.get('name') for s in sites]}")


def validate_endpoint(endpoint: str) -> str:
  """Ensure the ohsome endpoint is on the trusted, HTTPS-only allow-list."""
  if endpoint not in ALLOWED_OHSOME_ENDPOINTS:
    raise OhsomeError(f"ohsome endpoint not in allow-list: {endpoint}")
  if urlparse(endpoint).scheme != "https":
    raise OhsomeError(f"ohsome endpoint must use HTTPS: {endpoint}")
  return endpoint


def get_api_key() -> str:
  """Read the ohsome API key from the environment; never hardcode or log it."""
  api_key = os.environ.get(API_KEY_ENV_VAR)
  if not api_key:
    raise OhsomeError(f"Missing ohsome API key: set the {API_KEY_ENV_VAR} environment variable")
  return api_key


def bbox_to_aoi(bbox: BoundingBox) -> List[float]:
  """Convert a validated BoundingBox into ohsome's [xmin, ymin, xmax, ymax] AOI array."""
  return [bbox.west, bbox.south, bbox.east, bbox.north]


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
    raise OhsomeError(f"Response too large ({content_length} bytes)")

  chunks = []
  total = 0
  for chunk in response.iter_content(chunk_size=65536):
    total += len(chunk)
    if total > MAX_RESPONSE_BYTES:
      raise OhsomeError(f"Response exceeded max size of {MAX_RESPONSE_BYTES} bytes")
    chunks.append(chunk)
  return b"".join(chunks)


def query_ohsome(
  aoi: List[float],
  endpoint: str = DEFAULT_ENDPOINT,
  osm_filter: str = ROAD_FILTER,
  timeout_s: int = REQUEST_TIMEOUT_S,
  max_retries: int = MAX_RETRIES,
) -> pd.DataFrame:
  """Send a feature-extraction request to the ohsome API with safety checks.

  Args:
    aoi: [xmin, ymin, xmax, ymax] bbox, built via bbox_to_aoi().
    endpoint: Must be one of ALLOWED_OHSOME_ENDPOINTS.
    osm_filter: Fixed ohsome filter string (never user/free-form text).
    timeout_s: Per-request network timeout, in seconds.
    max_retries: Bounded retry attempts on transient failures.

  Returns:
    Parsed features as a pandas DataFrame (osm_type, osm_id, tags, geom_type, ...).

  Raises:
    OhsomeError: On invalid endpoint, missing API key, oversized response, or
      exhausted retries.
  """
  endpoint = validate_endpoint(endpoint)
  api_key = get_api_key()
  body = {"aoi": aoi, "filter": osm_filter, "time": "latest", "clip": True}

  last_error: Optional[Exception] = None
  for attempt in range(1, max_retries + 1):
    _throttle()
    try:
      response = requests.post(
        endpoint + EXTRACTION_PATH,
        json=body,
        headers={"Authorization": api_key, "User-Agent": USER_AGENT},
        timeout=timeout_s,
        stream=True,
        # verify defaults to True (system CA bundle); TLS verification is never disabled.
      )
      response.raise_for_status()
      content = _read_bounded(response)
      return pd.read_parquet(io.BytesIO(content), to_pandas_kwargs={"maps_as_pydicts": "strict"})
    except (requests.RequestException, OhsomeError, OSError) as exc:
      last_error = exc
      logger.warning(f"ohsome request attempt {attempt}/{max_retries} failed: {exc}")
      if attempt < max_retries:
        time.sleep(RETRY_BACKOFF_S * attempt)

  raise OhsomeError(f"ohsome query failed after {max_retries} attempts: {last_error}")


def fetch_site_data(site: Dict[str, Any], endpoint: str = DEFAULT_ENDPOINT) -> pd.DataFrame:
  """Fetch ohsome data for a single site definition from test_sites.yaml."""
  center = site["center"]
  bbox = bbox_from_center(center["lat"], center["lng"], site["radius_m"])
  aoi = bbox_to_aoi(bbox)
  logger.info(f"Querying ohsome for site '{site.get('name')}' aoi={aoi}")
  return query_ohsome(aoi, endpoint=endpoint)


def _main() -> None:
  import argparse

  logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

  parser = argparse.ArgumentParser(description="Query the ohsome API for a configured test site")
  parser.add_argument("site", help="Site name from test_sites.yaml (e.g. gdynia-city-center-pl)")
  parser.add_argument(
    "--test-sites", type=Path, default=Path(__file__).parent / "test_sites.yaml",
    help="Path to test_sites.yaml",
  )
  parser.add_argument(
    "--endpoint", default=DEFAULT_ENDPOINT, choices=ALLOWED_OHSOME_ENDPOINTS,
    help="ohsome API endpoint (must be allow-listed)",
  )
  args = parser.parse_args()

  sites = load_test_sites(args.test_sites)
  site = find_site(sites, args.site)
  features = fetch_site_data(site, endpoint=args.endpoint)

  ways = features[features["osm_type"] == "way"]
  print(f"Site: {site['name']}")
  print(f"Total features: {len(features)} (ways: {len(ways)})")
  for _, way in ways.head(5).iterrows():
    tags = way["tags"] or {}
    geom = wkb.loads(way["geom"])
    first_point = list(geom.coords)[0] if geom.coords else None
    print(
      f"  way {way['osm_id']}: highway={tags.get('highway')} footway={tags.get('footway')} "
      f"geom_type={way['geom_type']} points={len(geom.coords)} first_point={first_point}"
    )
  return


if __name__ == "__main__":
  _main()
