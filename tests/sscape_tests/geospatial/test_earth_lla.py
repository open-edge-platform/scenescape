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
  inputs = {
    "pixels per meter": 5.765182197,
    "map resolution": [981, 1112],
    "lat, long, altitude points": [
      [33.842058, -112.136117, 539],
      [33.842175, -112.134245, 539],
      [33.843923, -112.134407, 539],
      [33.843811, -112.136257, 539]
    ]
  }
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
  ti_gt = 90 * np.random.rand(int(1e+4), 3)
  for i, ti in enumerate(ti_gt):
    calc_pt = earth_lla.convertLLAToECEF(ti)
    calc_pt = earth_lla.convertECEFToLLA(calc_pt)
    error = np.linalg.norm(calc_pt - ti_gt[i])
    assert error < 1e-3

def test_geoConversionWorkflow(lla_datafile):
  with open(lla_datafile, 'r') as f:
    inputs = json.load(f)
  lla_pts = np.array(inputs['lat, long, altitude points'])
  resx, resy = inputs['map resolution']
  map_pts = (1 / inputs['pixels per meter']) * np.array([[0, 0, 0],
                                                         [resx, 0, 0],
                                                         [resx, resy, 0],
                                                         [0, resy, 0]])
  trs_mat = earth_lla.convertLLAToCartesianTRS(map_pts, lla_pts)
  for i, pt in enumerate(map_pts):
    calc_lla_pt = earth_lla.convertXYZToLLA(trs_mat, pt)
    error = np.linalg.norm(calc_lla_pt - lla_pts[i])
    assert error < 1e-3
  pt_xyz = np.array([70.524848281194, 90.8350847616695, -3.6675197488896113e-20])
  print(pt_xyz, earth_lla.convertXYZToLLA(trs_mat, pt_xyz))
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
