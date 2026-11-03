# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# This file contains functions for conversion between various geospatial data formats
# Relevant acronyms:
#   ECEF - Earth-centered, Earth-fixed
#     Format:    [X,      Y,      Z     ]
#     Data type: [meters, meters, meters]
#   LLA  - Latitude, Longitude, Altitude
#     Format:    [Latitude, Longitude, Altitude]
#     Data type: [degrees,  degrees,   meters  ]
#   TRS  - Translation, Rotation, Scale

import numpy as np
import cv2
import math

from scene_common.geometry import Point

EQUATORIAL_RADIUS = 6378137.0
POLAR_RADIUS = 6356752.314245
SPHERICAL_RADIUS = 6378000.0
DEFAULT_Z_SHIFT_METERS = 2.0

def convertLLAToECEF(lla_pt):
  """! This function converts geospatial data from Latitude, Longitude, Altitude data (LLA)
  to a Earth-centered, Earth-fixed Coordiante System (ECEF). The input data can be a tuple,
  list, or numpy array.
  @param      lla_pt           Coordinates in LLA format [latitude, longitude, altitude]
  @returns    numpy.ndarray    Data in ECEF format [X, Y, Z]
  """
  # Conversion derived from https://en.wikipedia.org/wiki/Geographic_coordinate_conversion
  lat, long, altitude = lla_pt
  lat = np.deg2rad(lat)
  long = np.deg2rad(long)
  e_squared = 1 - POLAR_RADIUS**2/EQUATORIAL_RADIUS**2
  N = EQUATORIAL_RADIUS/math.sqrt(1 - e_squared*math.pow(math.sin(lat), 2))

  geo_cart_pt = np.array([
                (N + altitude)*math.cos(lat)*math.cos(long),
                (N + altitude)*math.cos(lat)*math.sin(long),
                ((1-e_squared)*N + altitude)*math.sin(lat)
                ])

  return geo_cart_pt

def convertECEFToLLA(ecef_pt):
  """! This function converts geospatial data from a Earth-centered, Earth-fixed Coordiante
  System (ECEF) to Latitude, Longitude, Altitude data (LLA). The input data can be a Point,
  tuple, list, or numpy array.
  @param      ecef_pt          Data in ECEF format [X, Y, Z]
  @returns    numpy.ndarray    Coordinates in LLA format [latitude, longitude, altitude]
  """
  # Note, some or all of these methods break down at the poles
  if isinstance(ecef_pt, Point):
    X, Y, Z = ecef_pt.asNumpyCartesian
  else:
    X, Y, Z = ecef_pt

  try:
    # Heikkinen's technique
    # -better approximation
    # https://en.wikipedia.org/wiki/Geographic_coordinate_conversion
    Z_sq = Z**2
    a_sq = EQUATORIAL_RADIUS**2
    b_sq = POLAR_RADIUS**2
    e_sq = 1 - b_sq/a_sq
    e_p_sq = a_sq/b_sq - 1
    p = math.sqrt(ecef_pt[0]**2 + Y**2)
    p_sq = p**2
    F = 54*(b_sq)*Z_sq
    G = p_sq + (1-e_sq)*Z_sq - e_sq*(a_sq-b_sq)
    c = (e_sq**2)*F*p_sq/(G**3)
    s = (1 + c + math.sqrt(c**2 + 2*c))**(1/3)
    k = s + 1 + 1/s
    P = F/(3*(k**2)*(G**2))
    Q = math.sqrt(1 + 2*(e_sq**2)*P)
    r0 = -P*e_sq*p/(1+Q) + math.sqrt(0.5*a_sq*(1+1/Q)-P*(1-e_sq)*Z_sq/(Q+Q**2)-0.5*P*p_sq)
    U = math.sqrt((p-e_sq*r0)**2+Z_sq)
    V = math.sqrt((p-e_sq*r0)**2+(1-e_sq)*Z_sq)
    z0 = b_sq*Z/(EQUATORIAL_RADIUS*V)
    altitude = U * (1 - b_sq/(EQUATORIAL_RADIUS*V))
    lat = math.atan((Z+e_p_sq*z0)/p)
    long = math.atan2(Y, X)
  except (TypeError, ValueError):
    # simplest approximation, earth as sphere
    #  Default to using when the above technique fails
    #  Occurs with small values of [X, Y, Z] i.e. inside the earth
    R = math.sqrt(X**2+Y**2+Z**2)
    lat = math.asin(Z/R)
    long = math.atan2(Y, X)
    altitude = R - SPHERICAL_RADIUS

  return np.array([np.rad2deg(lat), np.rad2deg(long), altitude])

def convertToCartesianTRS(from_pts, to_pts):
  # Needs 3 point pairs, reliable with 4+
  (tr_mat, scale) = cv2.estimateAffine3D(from_pts, to_pts, force_rotation=False)
  tr_mat = np.vstack([tr_mat, np.array([0, 0, 0, 1])])
  s_mat = scale * np.identity(4)
  s_mat[3, 3] = 1
  trs_mat = np.matmul(tr_mat, s_mat)

  return trs_mat

def convertLLAToCartesianTRS(map_pts, lla_pts):
  ecef_pts = np.array([convertLLAToECEF(pt) for pt in lla_pts])
  trs_mat = convertToCartesianTRS(map_pts, ecef_pts)
  return trs_mat

def convertXYZToLLA(trs_mat, map_pt):
  ecef_pt = np.matmul(trs_mat, np.hstack([map_pt, 1]).T)[:3]
  return convertECEFToLLA(ecef_pt)

def calculateHeading(trs_mat, map_pt, velocity):
  # Implemented Simple Version, assumes spherical:
  # --https://towardsdatascience.com/calculating-the-bearing-between-two-geospatial-coordinates-66203f57e4b4
  # If more accuracy needed, this iterative, ellipsoid based solution may be implemented:
  # --https://en.wikipedia.org/wiki/Vincenty%27s_formulae
  lat_a, long_a = np.deg2rad(convertXYZToLLA(trs_mat, map_pt)[:2])
  lat_b, long_b = np.deg2rad(convertXYZToLLA(trs_mat, np.add(map_pt, velocity))[:2])
  long_diff = long_b - long_a

  x = math.cos(lat_b) * math.sin(long_diff)
  y = math.cos(lat_a) * math.sin(lat_b) - math.sin(lat_a) * math.cos(lat_b) * math.cos(long_diff)
  bearing = math.atan2(x, y)
  return np.rad2deg(bearing) % 360

def _signedArea(xs, ys):
  """! Shoelace signed area of the polygon with vertices (xs[i], ys[i]).
  @returns    float    Positive when the vertices run counterclockwise, negative when clockwise
  """
  return 0.5 * np.sum(xs * np.roll(ys, -1) - np.roll(xs, -1) * ys)

def alignCornerWinding(map_xyz_pts, lla_pts):
  """! Orders four geographic map corners so they run in the same rotational direction as the
  local map corners they are paired with.

  The documented convention lists the corners counterclockwise from the map origin, but the
  geospatial map generation in the UI lists them clockwise (SW, NW, NE, SE). A map cannot be
  mirrored on the globe, so the local XY polygon and the longitude/latitude polygon must wind the
  same way. If they do not, the second to fourth geographic corners are reversed and the first
  corner stays in place. Anything other than four points, or a degenerate (zero area) polygon,
  is returned unchanged.

  @param      map_xyz_pts      Four local corners on the map surface, in traversal order
  @param      lla_pts          The respective geographic corners in Latitude, Longitude, Altitude format
  @returns    numpy.ndarray    Geographic corners paired index-by-index with map_xyz_pts
  """
  map_xyz_pts = np.asarray(map_xyz_pts)
  lla_pts = np.asarray(lla_pts)
  if map_xyz_pts.shape[0] != 4 or lla_pts.shape[0] != 4:
    return lla_pts
  local_area = _signedArea(map_xyz_pts[:, 0], map_xyz_pts[:, 1])
  # Wrap longitude differences to [-180, 180) so a map crossing the antimeridian keeps its winding
  lon_diff = (lla_pts[:, 1] - lla_pts[0, 1] + 180.0) % 360.0 - 180.0
  geo_area = _signedArea(lon_diff, lla_pts[:, 0])
  if np.sign(local_area) * np.sign(geo_area) < 0:
    return lla_pts[[0, 3, 2, 1]]
  return lla_pts

def calculateTRSLocal2LLAFromSurfacePoints(map_xyz_pts, lla_pts, z_shift: float = DEFAULT_Z_SHIFT_METERS) -> np.ndarray:
  """! Calculates a transformation matrix from local Cartesian coordinates
  to Latitude, Longitude, Altitude (LLA) coordinates based on the map surface points
  and their respective geographic coordinates.

  This function provides a good aproximation for a horizontal and relatively flat
  scene map. Assuming the slope is neglible, the resulting approximation is
  accurate enough for most applications (~1m for scene dimensions below 500m).

  When four corner points are given, the geographic corners may be listed in either direction
  around the map (see alignCornerWinding).

  @param      map_xyz_pts      Points on the map surface (z=0) in local Cartesian coordinates
  @param      lla_pts          The Respective geographic coordinates in Latitude (degrees), Longitude (degrees), Altitude format
  @param      z_shift          The shift along the z-axis (altitude) to create synthetic points (default: 2.0 meters)
  @returns    numpy.ndarray    Transformation matrix in TRS format
  """
  map_xyz_pts = np.array(map_xyz_pts)
  lla_pts = np.array(lla_pts)
  if map_xyz_pts.shape[0] != lla_pts.shape[0]:
    raise ValueError("Number of map points must match number of geographic points")
  if map_xyz_pts.shape[0] < 3:
    raise ValueError("Needs at least 3 points to calculate transformation matrix")
  if any(map_xyz_pts[:, 2] != 0.0):
    raise ValueError("All map points must be on the surface (z=0)")
  lla_pts = alignCornerWinding(map_xyz_pts, lla_pts)
  # Extend point arrays with the same points but shifted along z-axis (altitude). This way we
  # provide additional synthetic points to augment the data and provide points that are not
  # coplanar to the map surface. This is necessary for the transformation matrix to be well-defined
  # in all three dimensions.
  map_xyz_pts = np.vstack([map_xyz_pts, np.column_stack([map_xyz_pts[:, 0],
                                                         map_xyz_pts[:, 1],
                                                         np.full(map_xyz_pts.shape[0], z_shift)])])
  lla_pts = np.vstack([lla_pts, np.column_stack([lla_pts[:, 0],
                                                 lla_pts[:, 1],
                                                 lla_pts[:, 2] + z_shift])])
  trs_mat = convertLLAToCartesianTRS(map_xyz_pts, lla_pts)
  return trs_mat

def _wrapDegrees180(deg):
  """! Wrap an angle in degrees into [-180, 180)."""
  return ((deg + 180.0) % 360.0) - 180.0

def _localTangentRadii(lat_rad):
  """! WGS-84 meridional radius (M), prime-vertical radius (N), and cos(lat) at a latitude.

  @param      lat_rad         Latitude in radians
  @returns    tuple           (M, N, cos_lat) in metres and unitless
  """
  e_sq = 1.0 - POLAR_RADIUS**2 / EQUATORIAL_RADIUS**2
  denom = math.sqrt(1.0 - e_sq * math.sin(lat_rad)**2)
  M = EQUATORIAL_RADIUS * (1.0 - e_sq) / (denom**3)
  N = EQUATORIAL_RADIUS / denom
  return M, N, math.cos(lat_rad)

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

def footprintAnchorFromCornersLLA(corners_lla):
  """! Recover footprint centre, heading, and dimensions from LLA corners.
  Inverse of localFootprintCornersLLA for SW, SE, NE, NW corner ordering, using the same
  local-tangent approximation.

  @param      corners_lla     Corners as (4,3) array: [lat,lng,alt] for SW, SE, NE, NW
  @returns    tuple           (lat, lng, heading_deg, width_m, height_m)
  """
  corners_lla = np.asarray(corners_lla)

  # Validate input
  if corners_lla.ndim != 2:
    raise ValueError(f"Corners must be a 2-D array, got shape {corners_lla.shape}")
  if corners_lla.shape[0] != 4:
    raise ValueError(f"Expected exactly 4 corners, got {corners_lla.shape[0]}")
  if corners_lla.shape[1] < 2:
    raise ValueError(f"Each corner must have at least lat,lng, got shape {corners_lla.shape}")
  if not np.isfinite(corners_lla).all():
    raise ValueError("All corner coordinates must be finite (not NaN or inf)")

  # Extract corners: SW, SE, NE, NW
  sw = corners_lla[0, :2]  # [lat, lng]
  se = corners_lla[1, :2]
  ne = corners_lla[2, :2]
  nw = corners_lla[3, :2]

  # Centre is the mean of the four corners. Longitudes are unwrapped relative to SW before
  # averaging so a footprint crossing the antimeridian is not centred near 0°.
  center_lat = np.mean([sw[0], se[0], ne[0], nw[0]])
  lngs_unwrapped = [sw[1]] + [sw[1] + _wrapDegrees180(p[1] - sw[1]) for p in (se, ne, nw)]
  center_lng = _wrapDegrees180(np.mean(lngs_unwrapped))

  lat_rad = np.deg2rad(center_lat)
  M, N, cos_lat = _localTangentRadii(lat_rad)

  # Helper: convert LLA difference to local (east, north) metres at centre
  def lla_to_local(pt_lla):
    pt_lat_rad = np.deg2rad(pt_lla[0])
    dlat_rad = pt_lat_rad - lat_rad
    dlng_rad = np.deg2rad(_wrapDegrees180(pt_lla[1] - center_lng))
    north = dlat_rad * M
    east = dlng_rad * N * cos_lat
    return east, north

  # Convert corners to local (east, north)
  se_east, se_north = lla_to_local(se)
  sw_east, sw_north = lla_to_local(sw)
  nw_east, nw_north = lla_to_local(nw)

  # Width = |SE - SW| (along local y=0 line), Height = |NW - SW| (along x=0 line)
  se_minus_sw_east = se_east - sw_east
  se_minus_sw_north = se_north - sw_north
  width_m = math.sqrt(se_minus_sw_east**2 + se_minus_sw_north**2)

  nw_minus_sw_east = nw_east - sw_east
  nw_minus_sw_north = nw_north - sw_north
  height_m = math.sqrt(nw_minus_sw_east**2 + nw_minus_sw_north**2)

  # Heading: local +X axis (SW->SE) direction has (east, north) = (cos psi, -sin psi)
  # So psi = atan2(-north_of_SE_minus_SW, east_of_SE_minus_SW)
  heading_rad = math.atan2(-se_minus_sw_north, se_minus_sw_east)
  heading_deg = np.rad2deg(heading_rad)
  heading_deg = heading_deg % 360.0  # Normalise to [0, 360)

  return (center_lat, center_lng, heading_deg, width_m, height_m)
