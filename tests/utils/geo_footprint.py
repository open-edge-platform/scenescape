# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Synthetic geospatial footprints for tests; production takes corners from the scene."""

import math

import numpy as np

from scene_common.earth_lla import _localTangentRadii, _wrapDegrees180


def localFootprintCornersLLA(center_lat, center_lng, heading_deg, width_m, height_m, alt=0.0):
  """! Compute LLA corners of a rectangular footprint from centre, heading, and dimensions.
  Local footprint corners are at SW (-W/2,-H/2), SE (+W/2,-H/2), NE (+W/2,+H/2), NW (-W/2,+H/2).
  Heading is in degrees, where 0° means local +Y points true north. Clockwise rotation.
  Uses WGS-84 local-tangent approximation.

  @param      center_lat      Centre latitude in degrees
  @param      center_lng      Centre longitude in degrees
  @param      heading_deg     Heading in degrees (0 = north, 90 = east)
  @param      width_m         Footprint width in metres (W, east-west extent)
  @param      height_m        Footprint height in metres (H, north-south extent)
  @param      alt             Altitude in metres (default 0.0)
  @returns    numpy.ndarray   Corners as (4,3) array: [lat,lng,alt] for SW, SE, NE, NW
  """
  # Input validation
  if not np.isfinite([center_lat, center_lng, heading_deg, width_m, height_m, alt]).all():
    raise ValueError("All numeric inputs must be finite (not NaN or inf)")
  if abs(center_lat) > 90.0:
    raise ValueError(f"Latitude must be in [-90, 90], got {center_lat}")
  if abs(center_lng) > 180.0:
    raise ValueError(f"Longitude must be in [-180, 180], got {center_lng}")
  if width_m <= 0.0:
    raise ValueError(f"Width must be positive, got {width_m}")
  if height_m <= 0.0:
    raise ValueError(f"Height must be positive, got {height_m}")

  # Convert heading to radians and compute rotation
  psi_rad = np.deg2rad(heading_deg)
  cos_psi = math.cos(psi_rad)
  sin_psi = math.sin(psi_rad)

  # Local offsets for each corner: (x, y) in footprint-local coords
  corners_local = [
    (-width_m / 2.0, -height_m / 2.0),  # SW
    (width_m / 2.0, -height_m / 2.0),   # SE
    (width_m / 2.0, height_m / 2.0),    # NE
    (-width_m / 2.0, height_m / 2.0)    # NW
  ]

  # Convert centre to radians
  lat_rad = np.deg2rad(center_lat)
  lng_rad = np.deg2rad(center_lng)
  M, N, cos_lat = _localTangentRadii(lat_rad)

  corners_lla = []
  for x_local, y_local in corners_local:
    # Rotate local (x, y) by heading to get (east, north) in metres
    east = x_local * cos_psi + y_local * sin_psi
    north = -x_local * sin_psi + y_local * cos_psi

    # Convert metres to radians using local tangent plane
    dlat_rad = north / M
    dlng_rad = east / (N * cos_lat)

    # Add to centre
    lat_corner = lat_rad + dlat_rad
    lng_corner = lng_rad + dlng_rad

    # Convert back to degrees; normalise longitude to [-180, 180)
    lat_deg = np.rad2deg(lat_corner)
    lng_deg = _wrapDegrees180(np.rad2deg(lng_corner))

    corners_lla.append([lat_deg, lng_deg, alt])

  return np.array(corners_lla)
