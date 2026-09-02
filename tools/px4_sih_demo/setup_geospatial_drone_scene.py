#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Create a geospatial SceneScape scene and ROI for the PX4 SIH drone demo.

Uses Mapbox (same logic as the manager geospatial UI) to fetch a satellite
snapshot, compute map_corners_lla / scale, register the scene via REST, and
add a center ROI sized for spatial-analytics verification.

Writes ``px4_sih_config.json`` beside this script for run_demo.sh / fly script.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from http import HTTPStatus
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from scene_common.rest_client import RESTClient

EARTH_CIRCUMFERENCE_M = 40075016.686
MAP_WIDTH_PX = 1280
MAP_HEIGHT_PX = 1280
DEFAULT_ZOOM = 19.0
DEFAULT_LOCATION = "Shoreline Amphitheatre, Mountain View, CA"
SCENE_NAME = "PX4 SIH Drone Demo"
ROI_NAME = "Drone Flight Corridor"
ROI_HALF_SIZE_M = 45.0


def _env(name, default=None, required=False):
  value = os.environ.get(name, default)
  if required and not value:
    raise SystemExit(f"Missing required environment variable: {name}")
  return value


def geocode_mapbox(token, query):
  url = (
    "https://api.mapbox.com/geocoding/v5/mapbox.places/"
    f"{quote(query)}.json?limit=1&access_token={token}")
  with urlopen(Request(url), timeout=30) as resp:
    data = json.loads(resp.read().decode("utf-8"))
  features = data.get("features") or []
  if not features:
    raise SystemExit(f"Mapbox geocoding found no results for: {query!r}")
  lng, lat = features[0]["center"]
  place_name = features[0].get("place_name", query)
  return lat, lng, place_name


def calculate_scale(lat, zoom):
  """Match manager/static/js/geospatial/map-interface.js calculateScale()."""
  pixels_per_degree = (256 * (2 ** zoom)) / 360.0
  meters_per_degree_lng = (EARTH_CIRCUMFERENCE_M / 360.0) * math.cos(math.radians(lat))
  return pixels_per_degree / meters_per_degree_lng


def _lat_lng_to_pixel(lat, lng, zoom):
  world_size = 512 * (2 ** zoom)
  x = (lng + 180.0) / 360.0 * world_size
  lat_rad = math.radians(lat)
  y = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * world_size
  return x, y


def _pixel_to_lat_lng(x, y, zoom):
  world_size = 512 * (2 ** zoom)
  lng = x / world_size * 360.0 - 180.0
  lat_rad = math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / world_size)))
  return math.degrees(lat_rad), lng


def map_view_corners(lat, lng, zoom, width_px, height_px, alt_m):
  """Return map_corners_lla: SW, NW, NE, SE (counterclockwise from bottom-left)."""
  cx, cy = _lat_lng_to_pixel(lat, lng, zoom)
  sw = _pixel_to_lat_lng(cx - width_px / 2.0, cy + height_px / 2.0, zoom)
  nw = _pixel_to_lat_lng(cx - width_px / 2.0, cy - height_px / 2.0, zoom)
  ne = _pixel_to_lat_lng(cx + width_px / 2.0, cy - height_px / 2.0, zoom)
  se = _pixel_to_lat_lng(cx + width_px / 2.0, cy + height_px / 2.0, zoom)
  return [
    [sw[0], sw[1], alt_m],
    [nw[0], nw[1], alt_m],
    [ne[0], ne[1], alt_m],
    [se[0], se[1], alt_m],
  ]


def fetch_mapbox_snapshot(token, lat, lng, zoom, out_path):
  url = (
    "https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/"
    f"{lng},{lat},{zoom},0,0/{MAP_WIDTH_PX}x{MAP_HEIGHT_PX}"
    f"?access_token={token}")
  req = Request(url)
  with urlopen(req, timeout=120) as resp:
    data = resp.read()
    content_type = resp.headers.get("Content-Type", "")
  if "jpeg" in content_type or data[:3] == b"\xff\xd8\xff":
    out_path = out_path.with_suffix(".jpg")
  out_path.write_bytes(data)
  return len(data), out_path


def roi_points_from_map_size(width_m, height_m, half_size_m):
  """Centered axis-aligned ROI in scene-local metres (image map convention)."""
  cx = width_m / 2.0
  cy = height_m / 2.0
  hs = half_size_m
  return [
    (cx - hs, cy - hs),
    (cx - hs, cy + hs),
    (cx + hs, cy + hs),
    (cx + hs, cy - hs),
  ]


def parse_args(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
    "--location", default=_env("PX4_DEMO_LOCATION", DEFAULT_LOCATION),
    help="Address or lat,lon for Mapbox geocoding")
  parser.add_argument(
    "--zoom", type=float, default=float(_env("PX4_DEMO_MAP_ZOOM", str(DEFAULT_ZOOM))),
    help="Mapbox zoom level (19 ≈ 150 m extent at 1280 px)")
  parser.add_argument(
    "--alt-m", type=float, default=float(_env("PX4_DEMO_GROUND_ALT_M", "15")),
    help="Ground altitude (m MSL) stored in map_corners_lla and PX4_HOME_ALT")
  parser.add_argument(
    "--rest-url", default=_env("SCENESCAPE_REST_URL", "https://web.scenescape.intel.com/api/v1"))
  parser.add_argument(
    "--root-cert", default=_env("SCENESCAPE_ROOT_CERT", "manager/secrets/certs/scenescape-ca.pem"))
  parser.add_argument(
    "--insecure", action="store_true",
    default=_env("SCENESCAPE_REST_INSECURE", "").lower() in ("1", "true", "yes"),
    help="Skip TLS verification (use with https://localhost)")
  parser.add_argument(
    "--user", default=_env("SCENESCAPE_REST_USER", "admin"))
  parser.add_argument(
    "--password", default=_env("SUPASS"))
  parser.add_argument(
    "--output-config",
    default=str(Path(__file__).resolve().parent / "px4_sih_config.json"))
  return parser.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  token = _env("MAPBOX_API_KEY", required=True)
  if not args.password:
    raise SystemExit("Set SUPASS (Scenescape admin password) in the environment")

  lat, lng, place_name = geocode_mapbox(token, args.location)
  scale = calculate_scale(lat, args.zoom)
  width_m = MAP_WIDTH_PX / scale
  height_m = MAP_HEIGHT_PX / scale
  corners = map_view_corners(lat, lng, args.zoom, MAP_WIDTH_PX, MAP_HEIGHT_PX, args.alt_m)

  with tempfile.TemporaryDirectory(prefix="px4-sih-map-") as tmpdir:
    map_path = Path(tmpdir) / "geospatial_map.png"
    nbytes, map_path = fetch_mapbox_snapshot(token, lat, lng, args.zoom, map_path)
    print(f"Map snapshot: {nbytes} bytes ({MAP_WIDTH_PX}x{MAP_HEIGHT_PX} px, "
          f"scale={scale:.2f} px/m, extent≈{width_m:.0f}x{height_m:.0f} m)")

    rest = RESTClient(
      args.rest_url,
      rootcert=None if args.insecure else args.root_cert,
      verify_ssl=False if args.insecure else args.root_cert)
    assert rest.authenticate(args.user, args.password), "REST authentication failed"

    scene_data = {
      "name": SCENE_NAME,
      "map_type": "geospatial_map",
      "map": (str(map_path), map_path.read_bytes()),
      "scale": round(scale, 2),
      "output_lla": True,
      "map_corners_lla": json.dumps(corners),
      "geospatial_provider": "mapbox",
      "map_center_lat": lat,
      "map_center_lng": lng,
      "map_zoom": args.zoom,
      "map_bearing": 0,
      # Must stay True: TimeChunkedIntelLabsTracking does not support use_tracker=False.
      "use_tracker": True,
    }
    res = rest.createScene(scene_data)
    if res.statusCode != HTTPStatus.CREATED:
      raise SystemExit(f"createScene failed: {res.statusCode} {res.errors}")
    scene_uid = res["uid"]
    print(f"Created scene {SCENE_NAME!r} uid={scene_uid}")

    roi_points = roi_points_from_map_size(width_m, height_m, ROI_HALF_SIZE_M)
    region_res = rest.createRegion({
      "scene": scene_uid,
      "name": ROI_NAME,
      "points": roi_points,
      "visible": True,
    })
    if region_res.statusCode != HTTPStatus.CREATED:
      raise SystemExit(f"createRegion failed: {region_res.statusCode} {region_res.errors}")
    roi_uid = region_res["uid"]
    print(f"Created ROI {ROI_NAME!r} uid={roi_uid}")

  takeoff_alt_m = args.alt_m + 25.0
  config = {
    "scene_uid": scene_uid,
    "scene_name": SCENE_NAME,
    "roi_uid": roi_uid,
    "roi_name": ROI_NAME,
    "location_label": place_name,
    "map_corners_lla": corners,
    "map_center_lat": lat,
    "map_center_lng": lng,
    "map_zoom": args.zoom,
    "scale_px_per_m": round(scale, 4),
    "map_extent_m": [round(width_m, 2), round(height_m, 2)],
    "px4_home_lat": lat,
    "px4_home_lon": lng,
    "px4_home_alt_m": args.alt_m,
    "px4_takeoff_alt_m": takeoff_alt_m,
    "source_id": "px4-sih-drone-1",
    "thing_type": "vehicle",
    "roi_half_size_m": ROI_HALF_SIZE_M,
  }
  out_path = Path(args.output_config)
  out_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
  print(f"Wrote {out_path}")
  print(json.dumps(config, indent=2))
  return 0


if __name__ == "__main__":
  sys.exit(main())
