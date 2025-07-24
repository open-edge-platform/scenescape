# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import json
import os

import numpy as np
import pytest
import scipy.spatial.transform as sstr

from scene_common import earth_lla

@pytest.fixture
def lla_datafile(tmp_path):
  z_shift = 2.0
  inputs = [
    {
      "pixels per meter": 5.765182197,
      "map resolution": [981, 1112],
      "lat, long, altitude points": [
        [33.842058, -112.136117, 539],
        [33.842175, -112.134245, 539],
        [33.843923, -112.134407, 539],
        [33.843811, -112.136257, 539],
        [33.842058, -112.136117, 539 + z_shift],
        [33.842175, -112.134245, 539 + z_shift],
        [33.843923, -112.134407, 539 + z_shift],
        [33.843811, -112.136257, 539 + z_shift],
      ],
      "map points": [
        [0, 0, 0],
        [981.0 / 5.765182197, 0, 0],
        [981.0 / 5.765182197, 1112.0 / 5.765182197, 0],
        [0, 1112.0 / 5.765182197, 0],
        [0, 0, z_shift],
        [981.0 / 5.765182197, 0, z_shift],
        [981.0 / 5.765182197, 1112.0 / 5.765182197, z_shift],
        [0, 1112.0 / 5.765182197, z_shift],
      ]
    }
  ]

  # Generate rectangular maps centered around the equator with varying parameters
  # and with edges aligned with the latitude and longitude lines, as depicted below:
  #
  #      Longitude ↑ (North)
  #           |
  #           |
  #  (x,y)----|----(x,0) ...     +---------+     ...     +---------+    ← Rectangular maps
  #      |    |    |             |         |             |         |
  #   ---|----+----|-------------|----+----|-------------|----+----|-→  Equator (Latitude = 0°)
  #      |    |    |             |         |             |         |    (East)
  #  (0,y)----|----(0,0) ...     +---------+     ...     +---------+
  #           |                       |                       |
  #
  #  Each rectangle represents a map area generated using parameters from equator_points_data.
  #  The maps are centered on the equator, so each is half above and half below the equator line.
  #  The map dimensions are x=map_dim_x and y=map_dim_y, where the x-axis is aligned with meridians
  #  and the y-axis is aligned with parallels.

  equator_points_data = {
    "pixels per meter":    [ 10.0,      7.5, 11.5,   5.2,    15.0 ],
    "scale":               [ 1.0,       2.0, 1.15,  0.95,    0.75 ],
    "map_dim_x":           [ 445,     378.5, 95.0,  33.1,   189.4 ],
    "map_dim_y":           [ 390,     253.5, 55.0,  42.1,   139.4 ],
    "center longitude":    [ -150.0, -120.0, 52.0,  87.0,   138.0 ],
    "altitude":            [ 10.0,    -20.0,  0.0, 110.0,    35.0 ]
  }
  for i in range(len(equator_points_data['pixels per meter'])):
    # the latitude / longitude angle from the center to the edge of the map
    angle_lat_deg = 0.5 * np.rad2deg(equator_points_data['map_dim_x'][i] / earth_lla.EQUATORIAL_RADIUS)
    angle_long_deg = 0.5 * np.rad2deg(equator_points_data['map_dim_y'][i] / earth_lla.EQUATORIAL_RADIUS)
    altitude = equator_points_data['altitude'][i]
    map_center_long = equator_points_data['center longitude'][i]
    pixels_per_meter = equator_points_data['pixels per meter'][i]
    map_resolution = [
      int(equator_points_data['map_dim_x'][i] * equator_points_data['pixels per meter'][i] * equator_points_data['scale'][i]),
      int(equator_points_data['map_dim_y'][i] * equator_points_data['pixels per meter'][i] * equator_points_data['scale'][i])
    ]
    inputs.append({
      "pixels per meter": pixels_per_meter,
      "map resolution": map_resolution,
      "lat, long, altitude points": [
        [- angle_lat_deg, map_center_long + angle_long_deg, altitude],
        [  angle_lat_deg, map_center_long + angle_long_deg, altitude],
        [  angle_lat_deg, map_center_long - angle_long_deg, altitude],
        [- angle_lat_deg, map_center_long - angle_long_deg, altitude],
        [- angle_lat_deg, map_center_long + angle_long_deg, altitude + z_shift],
        [  angle_lat_deg, map_center_long + angle_long_deg, altitude + z_shift],
        [  angle_lat_deg, map_center_long - angle_long_deg, altitude + z_shift],
        [- angle_lat_deg, map_center_long - angle_long_deg, altitude + z_shift],
        # center point elevated
        [0, map_center_long, altitude + z_shift],
      ],
      "map points": [
        [0, 0, 0],
        [map_resolution[0] / pixels_per_meter, 0, 0],
        [map_resolution[0] / pixels_per_meter, map_resolution[1] / pixels_per_meter, 0],
        [0, map_resolution[1] / pixels_per_meter, 0],
        [0, 0, z_shift],
        [map_resolution[0] / pixels_per_meter, 0, z_shift],
        [map_resolution[0] / pixels_per_meter, map_resolution[1] / pixels_per_meter, z_shift],
        [0, map_resolution[1] / pixels_per_meter, z_shift],
        # center point elevated
        [0.5 * map_resolution[0] / pixels_per_meter, 0.5 * map_resolution[1] / pixels_per_meter, z_shift],
      ]
    })
  tmp_file = os.path.join(tmp_path, 'inputs.json')
  with open(tmp_file, 'w') as outfile:
    outfile.write(json.dumps(inputs, indent=2))

  return tmp_file

def test_convertLLAToECEF():
  a = earth_lla.EQUATORIAL_RADIUS
  b = earth_lla.POLAR_RADIUS
  test_inputs = [
    [0, 0, 100],
    [0, 90, 0],
    [90, 0, 0]
  ]
  expected_outputs = np.array([
    [a + 100, 0, 0],
    [0, a, 0],
    [0, 0, b]
  ])
  for i, ti in enumerate(test_inputs):
    calc_pt = earth_lla.convertLLAToECEF(ti)
    error = np.linalg.norm(calc_pt - expected_outputs[i])
    assert error < 1e-6  # 1 micron
  return

def test_convertECEFToLLA():
  a = earth_lla.EQUATORIAL_RADIUS
  b = earth_lla.POLAR_RADIUS
  test_inputs = np.array([
    [a + 100, 0, 0],
    [0, a, 0],
    [0.1, 0, b]
  ])
  expected_outputs = np.array([
    [0, 0, 100],
    [0, 90, 0],
    [90, 0, 0]
  ])
  for i, ti in enumerate(test_inputs):
    calc_pt = earth_lla.convertECEFToLLA(ti)
    error = np.linalg.norm(calc_pt - expected_outputs[i])
    assert error < 1e-3  # 1 mm
  return

def test_convertToCartesianTRS():
  point_pairs = 4
  scale = 100 * np.random.rand()
  translation = 200 * np.random.rand(3) - 100
  rotMat = sstr.Rotation.from_euler('XYZ',
                                    list(180 * np.random.rand(3)),
                                    degrees=True).as_matrix()

  pts1 = 10 * np.random.rand(point_pairs, 3)
  pts2 = scale * pts1
  pts2 = np.array([np.matmul(rotMat, pts2[i, :]) for i in range(pts2.shape[0])])
  pts2 = pts2 + translation
  trs_mat = earth_lla.convertToCartesianTRS(pts1, pts2)

  calc_pt = np.matmul(np.linalg.inv(trs_mat), np.hstack([pts2[0, :], 1]).T)[0:3]
  error = np.linalg.norm(pts1[0, :] - calc_pt)

  assert error < 1e-10
  return

def test_getConversionBothWays():
  """ Test conversion from LLA to ECEF and back, and vice versa.
  Ensure that the error is below a threshold of 1e-8 for
  the points near the earth surface.
  """
  rand_vec = np.random.rand(int(1e+4), 3)
  for i, pt in enumerate(rand_vec):
    # scale from [0,1) to lat, long, altitude
    pt_lla = pt * np.array([180.0, 180.0, 100.0]) - np.array([90.0, 90.0, 50.0])
    # test error of conversion LLA to ECEF and back
    calc_pt_ecef = earth_lla.convertLLAToECEF(pt_lla)
    calc_pt_lla = earth_lla.convertECEFToLLA(calc_pt_ecef)
    ecef_to_lla_error = np.linalg.norm(calc_pt_lla - pt_lla)
    assert ecef_to_lla_error < 1e-8
    # test error of conversion ECEF to LLA and back
    calc_pt_ecef_back = earth_lla.convertLLAToECEF(calc_pt_lla)
    error = np.linalg.norm(calc_pt_ecef_back - calc_pt_ecef)
    assert error < 1e-8

def calcLLAError(lla_pt_1, lla_pt_2):
  """ Calculate the error between two LLA points using the error metric
   that is expressed in meters and is equally sensitive across all three
   dimensions. Uses the ECEF conversion mapping points to 3D Cartesian
   space in meters, allowing to use Euclidean distance directly.
   The implicit error of the conversion is proven to be below 1e-8.
  """
  return np.linalg.norm(earth_lla.convertLLAToECEF(lla_pt_1) - earth_lla.convertLLAToECEF(lla_pt_2))

def test_calcLLAError():
  pt_lla1 = np.array([54.38289073, 18.48151347, 151.0])
  pt_lla2 = np.array([54.38297375, 18.48170560, 151.0])
  assert calcLLAError(pt_lla1, pt_lla1) == pytest.approx(0.0, abs=1e-6)
  assert calcLLAError(pt_lla1, pt_lla2) == pytest.approx(15.531878, abs=1e-6)

def test_calculateTRSLocal2LLAFromSurfacePoints(lla_datafile):
  with open(lla_datafile, 'r') as f:
    inputs = json.load(f)
  # positive scenarios - verify the accuracy
  for input in inputs:
    lla_pts = input['lat, long, altitude points']
    map_pts = input['map points']
    # test with 4 points and default z_shift
    trs_mat = earth_lla.calculateTRSLocal2LLAFromSurfacePoints(map_pts[:4], lla_pts[:4])
    for i, pt in enumerate(map_pts):
      calc_lla_pt = earth_lla.convertXYZToLLA(trs_mat, pt)
      error = calcLLAError(calc_lla_pt, lla_pts[i])
      assert error < 1.0  # this error is expressed in meters
    # test with 4 points and z_shift 1.0 meter
    trs_mat = earth_lla.calculateTRSLocal2LLAFromSurfacePoints(map_pts[:4], lla_pts[:4], z_shift=1.0)
    for i, pt in enumerate(map_pts):
      calc_lla_pt = earth_lla.convertXYZToLLA(trs_mat, pt)
      error = calcLLAError(calc_lla_pt, lla_pts[i])
      assert error < 1.1  # this error is expressed in meters
  # negative scenarios
  lla_pts = inputs[0]['lat, long, altitude points']
  map_pts = inputs[0]['map points']
  # Test with mismatched number of points (should raise an exception)
  with pytest.raises(ValueError) as excinfo:
    # 3 map points and 4 lla points
    earth_lla.calculateTRSLocal2LLAFromSurfacePoints(map_pts[:3], lla_pts[:4])
  assert "number of map points must match number of geographic points" in str(excinfo.value).lower()
  # Test with too low number of points (should raise an exception)
  with pytest.raises(ValueError) as excinfo:
    # 2 map points and 2 lla points
    earth_lla.calculateTRSLocal2LLAFromSurfacePoints(map_pts[:2], lla_pts[:2])
  assert "needs at least 3 points" in str(excinfo.value).lower()
  # Test with maps points not on the surface (should raise an exception)
  with pytest.raises(ValueError) as excinfo:
    # map points with z != 0
    earth_lla.calculateTRSLocal2LLAFromSurfacePoints(map_pts[:4] + np.ones([4, 3]), lla_pts[:4])
  assert "map points must be on the surface" in str(excinfo.value).lower()
  return

def test_getHeading():
  a = earth_lla.SPHERICAL_RADIUS
  trs_mat = np.identity(4)
  test_inputs = np.array([
    [[a, 0, 0], [0, 0, 1]],
    [[a, 0, 0], [0, 1, 0]],
    [[a, 0, 0], [0, 1, 1]]
  ])
  expected_outputs = np.array([
    0,
    90,
    44.808
  ])
  for i, ti in enumerate(test_inputs):
    calc_pt = earth_lla.calculateHeading(trs_mat, ti[0], ti[1])
    error = np.linalg.norm(calc_pt - expected_outputs[i])
    assert error < 1  # degrees
  return
