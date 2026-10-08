# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Convert OSM-derived line geometries into scene-local polygon ROIs.

Reuses the existing Region model and RegionSerializer to create DB objects.
Coordinates are transformed from LLA (lat/lng/alt) into the scene's local
meter coordinate system using the pre-computed trs_matrix.
"""

import logging
import math

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
import uuid

import numpy as np
from shapely.geometry import LineString, MultiPolygon, Polygon

from scene_common.earth_lla import convertLLAToECEF

from . import osm_query
from .models import Scene

logger = logging.getLogger(__name__)


class OsmRoiError(Exception):
  """Raised when OSM ROI creation cannot proceed."""


# Road width lookup table (meters) for buffering line geometries.
# Matches common OSM highway classifications.
ROAD_WIDTH_BY_TYPE_M = {
  "footway": 3.0,
  "path": 3.0,
  "cycleway": 4.0,
  "track": 4.0,
  "steps": 3.0,
  "platform": 5.0,
  "pedestrian": 5.0,
  "living_street": 5.0,
  "service": 4.0,
  "unclassified": 6.0,
  "residential": 6.0,
  "tertiary": 7.0,
  "secondary": 8.0,
  "primary": 10.0,
  "trunk": 12.0,
  "motorway": 14.0,
}
DEFAULT_ROAD_WIDTH_M = 4.0

# Human-readable labels for OSM way types
OSM_TYPE_LABELS = {
  "footway": "Walking Path",
  "path": "Pedestrian Path",
  "cycleway": "Bike Path",
  "track": "Track",
  "steps": "Steps",
  "platform": "Platform",
  "pedestrian": "Pedestrian Street",
  "living_street": "Living Street",
  "service": "Service Road",
  "unclassified": "Unclassified Road",
  "residential": "Residential Street",
  "tertiary": "Tertiary Road",
  "secondary": "Secondary Road",
  "primary": "Primary Road",
  "trunk": "Trunk Road",
  "motorway": "Motorway",
}

# Footway sub-type labels
FOOTWAY_TYPE_LABELS = {
  "sidewalk": "Sidewalk",
  "crossing": "Pedestrian Crossing",
  "alley": "Alley",
  "track": "Track",
}

# Road types where OSM 'lanes' tag reliably indicates vehicle-carriageway width;
# excludes path-like types, which aren't measured in lanes.
LANE_BASED_WIDTH_TYPES = frozenset(ROAD_WIDTH_BY_TYPE_M) - {
  "footway", "path", "cycleway", "track", "steps", "platform", "pedestrian",
}

# Safety cap on polygon point count after simplification.
MAX_POLYGON_POINTS = 200
STANDARD_LANE_WIDTH_M = 3.5  # meters per lane for road width estimation


def lla_to_local_xy(
  trs_matrix: List[List[float]],
  lat: float,
  lng: float,
  alt: float = 0.0,
) -> Tuple[float, float]:
  """Convert LLA (lat/lng/alt) to scene-local (x, y) coordinates.

  Args:
    trs_matrix: 4x4 matrix from Scene.trs_matrix (local XYZ -> ECEF direction).
    lat: latitude in degrees.
    lng: longitude in degrees.
    alt: altitude in meters (default 0.0).

  Returns:
    (x, y) tuple in scene-local meters.

  Raises:
    OsmRoiError: if trs_matrix is None/falsy or invalid.
  """
  if not trs_matrix:
    raise OsmRoiError(
      "Scene geospatial calibration (trs_matrix) is not ready; "
      "enable output_lla and wait for the controller to publish it."
    )

  try:
    # Convert LLA to ECEF
    ecef = convertLLAToECEF([lat, lng, alt])

    # Apply inverse of trs_matrix: local = inv(trs_matrix) @ [ecef, 1]
    trs_array = np.array(trs_matrix, dtype=float)
    trs_inv = np.linalg.inv(trs_array)
    ecef_homogeneous = np.array([*ecef, 1.0])
    local_homogeneous = trs_inv @ ecef_homogeneous
    local_xyz = local_homogeneous[:3]

    return float(local_xyz[0]), float(local_xyz[1])

  except (ValueError, np.linalg.LinAlgError, TypeError) as exc:
    raise OsmRoiError(f"Failed to convert LLA to local coordinates: {exc}")


def line_to_polygons(
  local_coords: List[Tuple[float, float]],
  width_m: float,
) -> List[List[Tuple[float, float]]]:
  """Convert a line into polygon(s) by buffering.

  Args:
    local_coords: list of (x, y) tuples in scene-local meters.
    width_m: buffer width in meters.

  Returns:
    list of polygons, each a list of (x, y) tuples (exterior ring only,
    closing vertex omitted).
  """
  if len(local_coords) < 2:
    return []

  try:
    line = LineString(local_coords)
    buffered = line.buffer(width_m / 2, cap_style="flat")
    simplified = buffered.simplify(0.1, preserve_topology=True)

    polygons = []

    if simplified.geom_type == "Polygon":
      geoms = [simplified]
    elif simplified.geom_type == "MultiPolygon":
      geoms = simplified.geoms
    else:
      logger.warning(f"Unexpected geometry type after buffer: {simplified.geom_type}")
      return []

    for poly in geoms:
      if not isinstance(poly, Polygon):
        continue

      # Extract exterior ring coordinates, omit closing duplicate
      exterior_coords = list(poly.exterior.coords)[:-1]

      # Safety check: truncate if too many points
      if len(exterior_coords) > MAX_POLYGON_POINTS:
        logger.warning(
          f"Polygon has {len(exterior_coords)} points, exceeding "
          f"MAX_POLYGON_POINTS={MAX_POLYGON_POINTS}; truncating"
        )
        # Keep evenly-spaced subset using ceiling division to ensure result ≤ MAX_POLYGON_POINTS
        step = max(1, math.ceil(len(exterior_coords) / MAX_POLYGON_POINTS))
        exterior_coords = exterior_coords[::step]

      polygons.append(exterior_coords)

    return polygons

  except Exception as exc:
    logger.error(f"Error buffering line to polygon: {exc}")
    return []


def bbox_from_map_corners(
  map_corners_lla: Optional[List[List[float]]],
) -> Tuple[float, float, float, float]:
  """Derive an OSM query bounding box from the scene's saved map corners.

  Args:
    map_corners_lla: list of 4 [lat, lon, alt] corners (Scene.map_corners_lla).

  Returns:
    (south, west, north, east) bounding box in degrees.

  Raises:
    OsmRoiError: if map_corners_lla is not set or malformed.
  """
  if not map_corners_lla:
    raise OsmRoiError(
      "Scene has no map_corners_lla set; generate geospatial bounds "
      "(Generate Geospatial Bounds & Snapshot) before creating OSM ROIs."
    )

  try:
    lats = [float(corner[0]) for corner in map_corners_lla]
    lons = [float(corner[1]) for corner in map_corners_lla]
  except (IndexError, TypeError, ValueError) as exc:
    raise OsmRoiError(f"Invalid map_corners_lla: {exc}")

  return min(lats), min(lons), max(lats), max(lons)


def get_width_m(tags: Dict[str, Any], way_type: str) -> float:
  """Extract road/path width from OSM tags with intelligent fallbacks.

  Priority order:
    1. Explicit 'width' tag (meters)
    2. 'lanes' count * standard lane width (for roads)
    3. Footway sub-type specific widths
    4. Road type default from ROAD_WIDTH_BY_TYPE_M
    5. DEFAULT_ROAD_WIDTH_M fallback

  Args:
    tags: OSM tags dict (e.g., {"width": "3.5", "lanes": "3"}).
    way_type: OSM highway type (e.g., "secondary", "footway").

  Returns:
    Width in meters.
  """
  if not isinstance(tags, dict):
    return ROAD_WIDTH_BY_TYPE_M.get(way_type, DEFAULT_ROAD_WIDTH_M)

  # Priority 1: explicit width tag
  if "width" in tags:
    try:
      return float(tags["width"])
    except (ValueError, TypeError):
      pass

  # Priority 2: lanes-based estimate (for vehicle roads, not footways/cycleways)
  if "lanes" in tags and way_type in LANE_BASED_WIDTH_TYPES:
    try:
      lanes = int(tags["lanes"])
      estimated_width = lanes * STANDARD_LANE_WIDTH_M
      return estimated_width
    except (ValueError, TypeError):
      pass

  # Priority 3: footway sub-type specific widths
  if way_type == "footway":
    footway_type = tags.get("footway", "").lower()
    if footway_type == "crossing":
      return 2.0  # crossings are narrow
    elif footway_type == "sidewalk":
      return 1.8  # standard sidewalk narrower than generic footway

  # Priority 4: type-based default
  width = ROAD_WIDTH_BY_TYPE_M.get(way_type, DEFAULT_ROAD_WIDTH_M)
  return width


def build_roi_name(tags: Dict[str, Any], way_type: str, ordinal: int = 1) -> str:
  """Build a descriptive ROI name from OSM tags and type.

  Includes road name (if present) and sub-type (for footways). Named roads use
  their OSM name alone; the type label is only appended when there's no name.
  Examples:
    - "Ul. Grójecka"
    - "Sidewalk"
    - "Pedestrian Crossing"
    - "Bike Path-1"

  Args:
    tags: OSM tags dict.
    way_type: OSM highway type.
    ordinal: for de-duplication (1 for first, 2 for second, etc.).

  Returns:
    Human-readable name string.
  """
  if not isinstance(tags, dict):
    label = OSM_TYPE_LABELS.get(way_type, way_type)
    return label if ordinal == 1 else f"{label}-{ordinal}"

  # Start with base label
  base_label = OSM_TYPE_LABELS.get(way_type, way_type)

  # Override with footway sub-type if applicable
  if way_type == "footway":
    footway_type = tags.get("footway", "").lower()
    if footway_type in FOOTWAY_TYPE_LABELS:
      base_label = FOOTWAY_TYPE_LABELS[footway_type]

  # Prefer the road's own name; fall back to the type label when unnamed
  road_name = tags.get("name", "").strip()
  name = road_name if road_name else base_label

  # Handle duplicates
  if ordinal > 1:
    name += f"-{ordinal}"

  return name


def assign_names(previews: List[Dict[str, Any]]) -> None:
  """Assign human-readable names to preview ROIs, using full tag information.

  Mutates each preview dict in-place, adding a "name" key.
  Groups by (type, road_name) to handle multiple segments of the same road.

  Args:
    previews: list of preview dicts with "type", "tags" and "points" keys.
  """
  # Group by (way_type, road_name) for intelligent de-duplication
  by_group = defaultdict(list)
  for preview in previews:
    way_type = preview.get("type", "way")
    tags = preview.get("tags", {})
    road_name = tags.get("name", "") if isinstance(tags, dict) else ""
    group_key = (way_type, road_name)
    by_group[group_key].append(preview)

  # Assign names within each group
  for (way_type, road_name), items in by_group.items():
    for ordinal, preview in enumerate(items, start=1):
      tags = preview.get("tags", {})
      name = build_roi_name(tags, way_type, ordinal if len(items) > 1 else 1)
      preview["name"] = name


def assign_temp_uuid(previews: List[Dict[str, Any]]) -> None:
  """Assign temporary UUIDs to preview ROIs for checkbox state tracking.

  Mutates each preview dict in-place, adding a "uuid" and "checked" key.
  The UUID is used to link checkboxes in the frontend to the ROI data.
  All ROIs default to checked=true.

  Args:
    previews: list of preview dicts (already with "name", "type", "points").
  """
  for preview in previews:
    preview["uuid"] = str(uuid.uuid4())
    preview["checked"] = True


def build_roi_previews(scene: Scene) -> List[Dict[str, Any]]:
  """Fetch OSM ways, convert to local coordinates, buffer to polygons, name them, assign UUID.

  The bounding box is derived from the scene's saved map_corners_lla, so no
  per-call bbox input is needed. Raw OSM way geometries are cached on the
  scene (osm_ways_cache + osm_ways_cache_bbox) so repeated ROI generation doesn't
  re-hit the OSM API. The cache is automatically invalidated if map_corners_lla
  changes, ensuring previews always reflect the current map location.

  Args:
    scene: Scene object with trs_matrix and map_corners_lla populated.

  Returns:
    list of preview dicts: {"uuid": str, "type": str, "points": [[x,y],...], 
                           "name": str, "checked": bool, "tags": dict, "width_m": float}.

  Raises:
    OsmRoiError: if scene.trs_matrix/map_corners_lla is not ready or if OSM query fails.
  """
  if not scene.trs_matrix:
    raise OsmRoiError(
      "Scene geospatial calibration (trs_matrix) is not ready; "
      "enable output_lla and wait for the controller to publish it."
    )

  # Cache is only usable if:
  # 1. Tags format is current (dict, not raw list-of-pairs from parquet)
  # 2. The bounding box used to fetch the cache still matches current map corners
  #    (if map_corners_lla changed, the old ways are stale)
  if not scene.map_corners_lla:
    raise OsmRoiError(
      "Scene map corners (map_corners_lla) not set; cannot derive OSM query bounding box"
    )

  south, west, north, east = bbox_from_map_corners(scene.map_corners_lla)
  current_bbox = [south, west, north, east]

  cache_is_current = (
    scene.osm_ways_cache is not None
    and all(isinstance(way.get("tags"), dict) for way in scene.osm_ways_cache)
    and scene.osm_ways_cache_bbox == current_bbox
  )

  if cache_is_current:
    ways = scene.osm_ways_cache
  else:
    ways = osm_query.query_osm_ways_geometry(south, west, north, east)
    scene.osm_ways_cache = ways
    scene.osm_ways_cache_bbox = current_bbox
    scene.save(update_fields=["osm_ways_cache", "osm_ways_cache_bbox"])

  previews = []
  for way in ways:
    way_type = way["type"]
    coords_lla = way["coords"]  # [(lat, lng), ...]
    tags = way.get("tags", {})  # OSM tags for this way

    # Convert LLA coords to local xy
    local_coords = []
    for lat, lng in coords_lla:
      try:
        x, y = lla_to_local_xy(scene.trs_matrix, lat, lng, alt=0.0)
        local_coords.append((x, y))
      except OsmRoiError as exc:
        logger.error(f"Failed to convert way coordinate: {exc}")
        break

    if not local_coords:
      continue

    # Extract width intelligently from tags (lanes, explicit width, type default)
    width_m = get_width_m(tags, way_type)
    polygons = line_to_polygons(local_coords, width_m)

    for polygon_points in polygons:
      previews.append({
        "type": way_type,
        "points": polygon_points,
        "tags": tags,
        "width_m": width_m,
      })

  # Assign names using full tag information for context
  assign_names(previews)
  
  # Assign temporary UUIDs for checkbox tracking in frontend
  assign_temp_uuid(previews)

  logger.info(f"Built {len(previews)} ROI previews from {len(ways)} OSM ways")
  return previews


