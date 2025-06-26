# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

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
  lat_b, long_b = np.deg2rad(convertXYZToLLA(trs_mat, map_pt + velocity)[:2])
  long_diff = long_b - long_a

  x = math.cos(lat_b) * math.sin(long_diff)
  y = math.cos(lat_a) * math.sin(lat_b) - math.sin(lat_a) * math.cos(lat_b) * math.cos(long_diff)
  bearing = math.atan2(x, y)
  return np.rad2deg(bearing) % 360

def calculateTRSLocal2LLAFromSurfacePoints(map_xyz_pts, lla_pts, z_shift: float = DEFAULT_Z_SHIFT_METERS) -> np.ndarray:
  """! Calculates a transformation matrix from local Cartesian coordinates
  to Latitude, Longitude, Altitude (LLA) coordinates based on the map surface points
  and their respective geographic coordinates.

  This function provides a good aproximation for a horizontal and relatively flat
  scene map. Assuming the slope is neglible, the resulting approximation is
  accurate enough for most applications (~1m for scene dimensions below 500m).

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

def calculateTRSLocal2LLAFromImageMap(resx: int, resy: int, pixels_per_meter: float, lla_pts, z_shift: float = DEFAULT_Z_SHIFT_METERS) -> np.ndarray:
  """! Calculates a transformation matrix from local Cartesian coordinates
  to Latitude, Longitude, Altitude (LLA) coordinates based on the map resolution
  and the geographic coordinates of the map corners.

  This function provides a good aproximation for a horizontal and relatively flat
  scene map. Assuming the slope is neglible, the resulting approximation is
  accurate enough for most applications (~1m for scene dimensions below 500m,
  and up to 2 meters above the surface).

  @param      resx             Map resolution in x direction expressed in pixels (width)
  @param      resy             Map resolution in y direction expressed in pixels (height)
  @param      pixels_per_meter Pixels per meter, used to scale the map points
  @param      lla_pts          Geographic coordinates in Latitude (degrees), Longitude (degrees), Altitude format
                               of four corners of the map image.
  @note                        The map points are assumed to be in the order: (0,0), (resx,0), (resx,resy), (0,resy)
  @param      z_shift          The shift along the z-axis (altitude) to create synthetic points (default: 2.0 meters)
  @returns    numpy.ndarray    Transformation matrix in TRS format
  """
  map_pts = (1 / pixels_per_meter) * np.array([[0, 0, 0],
                                    [resx, 0, 0],
                                    [resx, resy, 0],
                                    [0, resy, 0]])
  return calculateTRSLocal2LLAFromSurfacePoints(map_pts, np.array(lla_pts), z_shift=z_shift)
