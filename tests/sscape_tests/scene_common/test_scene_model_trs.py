# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for SceneModel.trs_xyz_to_lla on GLB maps with a legacy (unposed) mesh."""

import shutil
from pathlib import Path

import numpy as np

from scene_common.earth_lla import convertXYZToLLA, localFootprintCornersLLA
from scene_common.scene_model import SceneModel

TEST_GLB_FILE = Path(__file__).resolve().parents[1] / "mesh_util" / "test_data" / "scene.glb"


def test_legacy_glb_without_pose_computes_no_lla_until_posed(tmp_path):
  """! A GLB map stored without mesh pose yields no LLA transform. Once a pose is set,
  the posed footprint maps onto the stored LLA corners within 1 m.
  """
  glb = tmp_path / "map.glb"
  shutil.copy(TEST_GLB_FILE, glb)
  scene = SceneModel("legacy", str(glb), None)
  scene.output_lla = True
  scene.map_corners_lla = localFootprintCornersLLA(37.0, -121.0, 35.0, 10.0, 10.0)
  scene.mesh_rotation = None
  scene.mesh_translation = None
  scene._invalidate_trs_xyz_to_lla()

  assert scene.trs_xyz_to_lla is None

  scene.mesh_rotation = [90, 0, 0]
  scene.mesh_translation = [0, 0, 0]
  scene._invalidate_trs_xyz_to_lla()
  footprint = scene.mapFootprintCorners()
  width = footprint[:, 0].max() - footprint[:, 0].min()
  height = footprint[:, 1].max() - footprint[:, 1].min()
  scene.map_corners_lla = localFootprintCornersLLA(37.0, -121.0, 35.0, width, height)

  trs_mat = scene.trs_xyz_to_lla
  assert trs_mat is not None

  for i, xyz_corner in enumerate(footprint):
    lla_corner = convertXYZToLLA(trs_mat, xyz_corner)
    expected = scene.map_corners_lla[i]
    lat_err_m = np.abs(lla_corner[0] - expected[0]) * 111000
    lng_err_m = np.abs(lla_corner[1] - expected[1]) * 111000 * np.cos(np.radians(expected[0]))
    assert max(lat_err_m, lng_err_m) <= 1.0, f"Corner {i} is off by more than 1 m"
