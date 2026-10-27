# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os

import numpy as np
import pytest
import scipy.spatial.transform as sstr

from scene_common import earth_lla
from scene_common.earth_lla import (
  localFootprintCornersLLA,
  footprintAnchorFromCornersLLA,
  calculateTRSLocal2LLAFromSurfacePoints,
  convertXYZToLLA
)

def _ecefDistanceM(lla_a, lla_b):
  """Straight-line distance in metres between two [lat, lng, alt] points, via ECEF."""
  return float(np.linalg.norm(earth_lla.convertLLAToECEF(lla_a) - earth_lla.convertLLAToECEF(lla_b)))

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

def _getMapCorners(lla_datafile):
  """ Returns the (map points, geographic points) pair of the first four points of every input,
  i.e. the map corners listed counterclockwise from the origin corner, as documented.
  """
  with open(lla_datafile, 'r') as f:
    inputs = json.load(f)
  return [(np.array(i['map points'][:4]), np.array(i['lat, long, altitude points'][:4])) for i in inputs]

def test_alignCornerWinding_keeps_matching_windings(lla_datafile):
  for map_pts, lla_pts in _getMapCorners(lla_datafile):
    # both counterclockwise (documented order)
    np.testing.assert_array_equal(earth_lla.alignCornerWinding(map_pts, lla_pts), lla_pts)
    # both clockwise
    np.testing.assert_array_equal(
      earth_lla.alignCornerWinding(map_pts[[0, 3, 2, 1]], lla_pts[[0, 3, 2, 1]]), lla_pts[[0, 3, 2, 1]])

def test_alignCornerWinding_reverses_mismatching_windings(lla_datafile):
  for map_pts, lla_pts in _getMapCorners(lla_datafile):
    # geographic corners clockwise (SW, NW, NE, SE, as written by the UI), local corners counterclockwise
    np.testing.assert_array_equal(earth_lla.alignCornerWinding(map_pts, lla_pts[[0, 3, 2, 1]]), lla_pts)
    # local corners clockwise, geographic corners counterclockwise
    np.testing.assert_array_equal(earth_lla.alignCornerWinding(map_pts[[0, 3, 2, 1]], lla_pts), lla_pts[[0, 3, 2, 1]])

def test_alignCornerWinding_across_antimeridian():
  # The map is 9 x 6 m and its longitudes wrap from 179.99995 to -179.99995
  map_pts = np.array([[0, 0, 0], [9, 0, 0], [9, 6, 0], [0, 6, 0]])
  lla_pts = np.array([
    [10.0, 179.99995, 0.0],
    [10.0, -179.99995, 0.0],
    [10.00005, -179.99995, 0.0],
    [10.00005, 179.99995, 0.0],
  ])
  np.testing.assert_array_equal(earth_lla.alignCornerWinding(map_pts, lla_pts), lla_pts)
  np.testing.assert_array_equal(earth_lla.alignCornerWinding(map_pts, lla_pts[[0, 3, 2, 1]]), lla_pts)

def test_alignCornerWinding_leaves_other_inputs_unchanged(lla_datafile):
  map_pts, lla_pts = _getMapCorners(lla_datafile)[0]
  # not four corners, so there is no winding to compare
  np.testing.assert_array_equal(earth_lla.alignCornerWinding(map_pts[:3], lla_pts[:3][[0, 2, 1]]), lla_pts[:3][[0, 2, 1]])
  with open(lla_datafile, 'r') as f:
    all_pts = json.load(f)[0]
  eight_lla_pts = np.array(all_pts['lat, long, altitude points'][:8])
  np.testing.assert_array_equal(earth_lla.alignCornerWinding(np.array(all_pts['map points'][:8]), eight_lla_pts), eight_lla_pts)
  # degenerate geographic corners (zero area) have no direction
  same_point = np.tile(lla_pts[0], (4, 1))
  np.testing.assert_array_equal(earth_lla.alignCornerWinding(map_pts, same_point), same_point)

def test_calculateTRSLocal2LLAFromSurfacePoints_accepts_both_corner_directions(lla_datafile):
  for map_pts, lla_pts in _getMapCorners(lla_datafile):
    counterclockwise_trs = earth_lla.calculateTRSLocal2LLAFromSurfacePoints(map_pts, lla_pts)
    clockwise_trs = earth_lla.calculateTRSLocal2LLAFromSurfacePoints(map_pts, lla_pts[[0, 3, 2, 1]])
    np.testing.assert_allclose(clockwise_trs, counterclockwise_trs)
    # every local corner lands on its own geographic corner, not on a transposed one
    for map_pt, lla_pt in zip(map_pts, lla_pts):
      assert calcLLAError(earth_lla.convertXYZToLLA(clockwise_trs, map_pt), lla_pt) < 1.0
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


class TestLocalFootprintCornersLLA:
  """Test localFootprintCornersLLA function."""

  def test_positive_zero_heading_axis_aligned(self):
    """Test 0° heading gives axis-aligned quad centred on anchor."""
    center_lat, center_lng = 45.0, -120.0
    heading_deg = 0.0
    width_m, height_m = 100.0, 50.0
    alt = 0.0

    corners = localFootprintCornersLLA(
      center_lat, center_lng, heading_deg, width_m, height_m, alt
    )

    # Corners should be: SW, SE, NE, NW
    sw, se, ne, nw = corners

    # SW and NW should have same longitude (western edge)
    assert abs(sw[1] - nw[1]) < 1e-6
    # SW and SE should have same latitude (southern edge)
    assert abs(sw[0] - se[0]) < 1e-6

    # Centre should be mean of corners
    centre_lat = np.mean([sw[0], se[0], ne[0], nw[0]])
    centre_lng = np.mean([sw[1], se[1], ne[1], nw[1]])
    assert abs(centre_lat - center_lat) < 1e-6
    assert abs(centre_lng - center_lng) < 1e-6

  def test_positive_90_heading_east(self):
    """Test ψ=90: SW->NW vector points east (local +Y east)."""
    center_lat, center_lng = 45.0, -120.0
    heading_deg = 90.0
    width_m, height_m = 100.0, 50.0
    alt = 0.0

    corners = localFootprintCornersLLA(
      center_lat, center_lng, heading_deg, width_m, height_m, alt
    )

    sw, _, _, nw = corners

    # With ψ=90°, local +Y (north in local footprint) points east in global frame
    # So: NW-SW should have positive east component
    # NW is further "north" locally, so should be further east globally
    nw_lng = nw[1]
    sw_lng = sw[1]

    # Handle antimeridian wrapping for longitude difference
    lng_diff = ((nw_lng - sw_lng + 180.0) % 360.0) - 180.0
    # NW should be east of SW when heading is 90°
    assert lng_diff > 0.0, f"NW-SW lng diff should be positive (east), got {lng_diff}"

  @pytest.mark.parametrize("heading", [0, 33, 90, 180, 271])
  def test_positive_altitude_preserved_across_headings(self, heading):
    """Test every corner keeps the requested altitude for various headings."""
    center_lat, center_lng = 45.0, -120.0
    width_m, height_m = 200.0, 150.0
    alt = 100.0

    corners = localFootprintCornersLLA(
      center_lat, center_lng, heading, width_m, height_m, alt
    )

    # All altitudes should match
    for corner in corners:
      assert abs(corner[2] - alt) < 1e-6

  def test_positive_non_square_dims(self):
    """Test non-square width and height."""
    center_lat, center_lng = 30.0, 0.0
    heading_deg = 45.0
    width_m, height_m = 500.0, 200.0
    alt = 50.0

    corners = localFootprintCornersLLA(
      center_lat, center_lng, heading_deg, width_m, height_m, alt
    )

    assert corners.shape == (4, 3)
    for corner in corners:
      assert abs(corner[2] - alt) < 1e-6

  def test_positive_60_degree_latitude(self):
    """Test at high latitude (60°)."""
    center_lat, center_lng = 60.0, 10.0
    heading_deg = 0.0
    width_m, height_m = 100.0, 100.0
    alt = 0.0

    corners = localFootprintCornersLLA(
      center_lat, center_lng, heading_deg, width_m, height_m, alt
    )

    assert corners.shape == (4, 3)
    assert all(abs(c[2]) < 1e-6 for c in corners)
    # One degree of longitude covers cos(lat) as many metres, so the same width spans about
    # 1/cos(60°) = 2x the longitude degrees it spans at the equator
    equator = localFootprintCornersLLA(0.0, center_lng, heading_deg, width_m, height_m, alt)
    assert np.ptp(corners[:, 1]) / np.ptp(equator[:, 1]) == pytest.approx(2.0, rel=1e-2)

  def test_negative_nan_inputs(self):
    """Test ValueError for NaN inputs."""
    with pytest.raises(ValueError, match="must be finite"):
      localFootprintCornersLLA(
        float('nan'), 0.0, 0.0, 100.0, 100.0
      )
    with pytest.raises(ValueError, match="must be finite"):
      localFootprintCornersLLA(
        45.0, float('nan'), 0.0, 100.0, 100.0
      )
    with pytest.raises(ValueError, match="must be finite"):
      localFootprintCornersLLA(
        45.0, 0.0, float('nan'), 100.0, 100.0
      )
    with pytest.raises(ValueError, match="must be finite"):
      localFootprintCornersLLA(
        45.0, 0.0, 0.0, float('nan'), 100.0
      )
    with pytest.raises(ValueError, match="must be finite"):
      localFootprintCornersLLA(
        45.0, 0.0, 0.0, 100.0, float('nan')
      )

  def test_negative_inf_inputs(self):
    """Test ValueError for inf inputs."""
    with pytest.raises(ValueError, match="must be finite"):
      localFootprintCornersLLA(
        float('inf'), 0.0, 0.0, 100.0, 100.0
      )
    with pytest.raises(ValueError, match="must be finite"):
      localFootprintCornersLLA(
        45.0, 0.0, 0.0, 100.0, float('inf')
      )

  def test_negative_latitude_out_of_bounds(self):
    """Test ValueError for |lat| > 90."""
    with pytest.raises(ValueError, match="Latitude must be in"):
      localFootprintCornersLLA(91.0, 0.0, 0.0, 100.0, 100.0)
    with pytest.raises(ValueError, match="Latitude must be in"):
      localFootprintCornersLLA(-91.0, 0.0, 0.0, 100.0, 100.0)

  def test_negative_longitude_out_of_bounds(self):
    """Test ValueError for |lng| > 180."""
    with pytest.raises(ValueError, match="Longitude must be in"):
      localFootprintCornersLLA(45.0, 181.0, 0.0, 100.0, 100.0)
    with pytest.raises(ValueError, match="Longitude must be in"):
      localFootprintCornersLLA(45.0, -181.0, 0.0, 100.0, 100.0)

  def test_negative_width_zero(self):
    """Test ValueError for width <= 0."""
    with pytest.raises(ValueError, match="Width must be positive"):
      localFootprintCornersLLA(45.0, 0.0, 0.0, 0.0, 100.0)
    with pytest.raises(ValueError, match="Width must be positive"):
      localFootprintCornersLLA(45.0, 0.0, 0.0, -50.0, 100.0)

  def test_negative_height_zero(self):
    """Test ValueError for height <= 0."""
    with pytest.raises(ValueError, match="Height must be positive"):
      localFootprintCornersLLA(45.0, 0.0, 0.0, 100.0, 0.0)
    with pytest.raises(ValueError, match="Height must be positive"):
      localFootprintCornersLLA(45.0, 0.0, 0.0, 100.0, -50.0)


class TestFootprintAnchorFromCornersLLA:
  """Test footprintAnchorFromCornersLLA function."""

  @pytest.mark.parametrize("heading", [0, 33, 90, 180, 271, 359.9])
  def test_positive_inverse_round_trip(self, heading):
    """Test inverse recovers (lat, lng, heading, W, H) for various headings."""
    center_lat, center_lng = 45.0, -120.0
    width_m, height_m = 300.0, 200.0
    alt = 50.0

    # Forward
    corners = localFootprintCornersLLA(
      center_lat, center_lng, heading, width_m, height_m, alt
    )

    # Inverse
    recovered_lat, recovered_lng, recovered_heading, recovered_w, recovered_h = (
      footprintAnchorFromCornersLLA(corners)
    )

    # Check recovery (within 1e-6 deg, about 0.1 m, and 1e-6 relative)
    assert abs(recovered_lat - center_lat) < 1e-6
    assert abs(recovered_lng - center_lng) < 1e-6
    assert abs(recovered_w - width_m) / width_m < 1e-6
    assert abs(recovered_h - height_m) / height_m < 1e-6

    # Heading comparison (handle 360° wrap)
    heading_diff = abs(recovered_heading - heading)
    if heading_diff > 180:
      heading_diff = 360 - heading_diff
    assert heading_diff < 1e-6

  @pytest.mark.parametrize("center_lng", [179.9999, -179.9999])
  @pytest.mark.parametrize("heading", [0, 90, 180, 270])
  def test_positive_inverse_round_trip_across_antimeridian(self, center_lng, heading):
    """Footprints straddling ±180° recover the centre longitude, not a mean near 0°."""
    center_lat = 45.0
    width_m, height_m = 200.0, 50.0

    corners = localFootprintCornersLLA(center_lat, center_lng, heading, width_m, height_m)
    recovered_lat, recovered_lng, recovered_heading, recovered_w, recovered_h = (
      footprintAnchorFromCornersLLA(corners)
    )

    lng_error = (recovered_lng - center_lng + 180.0) % 360.0 - 180.0
    assert abs(recovered_lat - center_lat) < 1e-6
    assert abs(lng_error) < 1e-6
    assert -180.0 <= recovered_lng < 180.0
    assert abs(recovered_w - width_m) / width_m < 1e-6
    assert abs(recovered_h - height_m) / height_m < 1e-6
    heading_diff = abs(recovered_heading - heading) % 360.0
    assert min(heading_diff, 360.0 - heading_diff) < 1e-6


  def test_positive_side_lengths_within_tolerance(self):
    """Test side lengths (SW-SE, SW-NW) equal W and H within 1%."""
    center_lat, center_lng = 40.0, -75.0
    heading_deg = 45.0
    width_m, height_m = 400.0, 250.0
    alt = 0.0

    corners = localFootprintCornersLLA(
      center_lat, center_lng, heading_deg, width_m, height_m, alt
    )

    sw, se, _, nw = corners

    # Side lengths as straight-line ECEF distance between adjacent corners
    width_computed = _ecefDistanceM(sw, se)
    height_computed = _ecefDistanceM(sw, nw)

    # Within 1%
    assert abs(width_computed - width_m) / width_m < 0.01
    assert abs(height_computed - height_m) / height_m < 0.01
    assert abs(width_computed - width_m) / width_m < 0.01
    assert abs(height_computed - height_m) / height_m < 0.01

  def test_negative_wrong_corner_count(self):
    """Test ValueError for wrong corner count."""
    with pytest.raises(ValueError, match="Expected exactly 4 corners"):
      footprintAnchorFromCornersLLA(np.array([[45, -120]]))
    with pytest.raises(ValueError, match="Expected exactly 4 corners"):
      footprintAnchorFromCornersLLA(np.array([[45, -120], [45.1, -120.1]]))

  def test_negative_insufficient_data_per_corner(self):
    """Test ValueError for < 2 data per corner."""
    with pytest.raises(ValueError, match="Each corner must have at least"):
      footprintAnchorFromCornersLLA(np.array([[45], [45], [45], [45]]))

  def test_negative_not_2d_corners(self):
    """Test ValueError for a flat array instead of (4, N) corners."""
    with pytest.raises(ValueError, match="must be a 2-D array"):
      footprintAnchorFromCornersLLA(np.array([45.0, -120.0, 0.0, 0.0]))

  def test_negative_nan_corners(self):
    """Test ValueError for NaN in corners."""
    corners = np.array([
      [float('nan'), -120.0, 0.0],
      [45.1, -119.9, 0.0],
      [45.2, -120.1, 0.0],
      [45.1, -120.2, 0.0]
    ])
    with pytest.raises(ValueError, match="must be finite"):
      footprintAnchorFromCornersLLA(corners)

  def test_negative_inf_corners(self):
    """Test ValueError for inf in corners."""
    corners = np.array([
      [45.0, float('inf'), 0.0],
      [45.1, -119.9, 0.0],
      [45.2, -120.1, 0.0],
      [45.1, -120.2, 0.0]
    ])
    with pytest.raises(ValueError, match="must be finite"):
      footprintAnchorFromCornersLLA(corners)


class TestRoundTripLocalFootprint:
  """Test round-trip conversion via TRS matrix."""

  @pytest.mark.parametrize("heading", [0, 33, 90, 180, 271])
  @pytest.mark.parametrize("width_m,height_m", [(100, 50), (200, 100), (150, 150)])
  def test_positive_round_trip_via_trs(self, heading, width_m, height_m):
    """Feed corners into calculateTRSLocal2LLAFromSurfacePoints and apply via
    convertXYZToLLA; round-trip each corner to <1m."""
    center_lat, center_lng = 45.0, -120.0
    alt = 0.0

    # Generate corners
    corners_lla = localFootprintCornersLLA(
      center_lat, center_lng, heading, width_m, height_m, alt
    )

    # Local footprint corners
    corners_local = np.array([
      [-width_m / 2.0, -height_m / 2.0, 0.0],  # SW
      [width_m / 2.0, -height_m / 2.0, 0.0],   # SE
      [width_m / 2.0, height_m / 2.0, 0.0],    # NE
      [-width_m / 2.0, height_m / 2.0, 0.0]    # NW
    ])

    # Compute TRS
    trs = calculateTRSLocal2LLAFromSurfacePoints(corners_local, corners_lla)

    # Convert each local corner back to LLA
    for i, local_pt in enumerate(corners_local):
      recovered_lla = convertXYZToLLA(trs, local_pt)

      distance_m = _ecefDistanceM(recovered_lla, corners_lla[i])
      assert distance_m < 1.0, f"Corner {i} round-trip error: {distance_m:.4f}m"

  def test_positive_60_degree_latitude_round_trip(self):
    """Test round-trip at 60° latitude."""
    center_lat, center_lng = 60.0, 10.0
    heading_deg = 45.0
    width_m, height_m = 100.0, 100.0
    alt = 0.0

    corners_lla = localFootprintCornersLLA(
      center_lat, center_lng, heading_deg, width_m, height_m, alt
    )

    corners_local = np.array([
      [-width_m / 2.0, -height_m / 2.0, 0.0],
      [width_m / 2.0, -height_m / 2.0, 0.0],
      [width_m / 2.0, height_m / 2.0, 0.0],
      [-width_m / 2.0, height_m / 2.0, 0.0]
    ])

    trs = calculateTRSLocal2LLAFromSurfacePoints(corners_local, corners_lla)

    for i, local_pt in enumerate(corners_local):
      recovered_lla = convertXYZToLLA(trs, local_pt)

      assert _ecefDistanceM(recovered_lla, corners_lla[i]) < 1.0
