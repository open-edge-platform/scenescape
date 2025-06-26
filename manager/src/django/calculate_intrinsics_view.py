# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import cv2
import numpy as np
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from scipy.spatial.transform import Rotation

from scene_common import log

def y_up_to_y_down(rotation_matrix):
  rotate_y = Rotation.from_euler('Y', np.pi).as_matrix()
  rotate_z = Rotation.from_euler('Z', np.pi).as_matrix()
  return rotation_matrix @ rotate_y @ rotate_z

def calculate_pose(rvec, tvec):
  R, _ = cv2.Rodrigues(rvec)
  T = np.array([
    [R[0, 0], R[0, 1], R[0, 2], tvec[0, 0]],
    [-R[1, 0], -R[1, 1], -R[1, 2], -tvec[1, 0]],
    [-R[2, 0], -R[2, 1], -R[2, 2], -tvec[2, 0]],
    [0, 0, 0, 1]
  ])
  T_inv = np.linalg.inv(T)

  euler = Rotation.from_matrix(y_up_to_y_down(T_inv[:3, :3])).as_euler('XYZ', degrees=False)

  position = T_inv[:3, 3]

  return euler, position

class CalculateCameraIntrinsics(APIView):
  def post(self, request):
    log.info(f"Received request to calculate intrinsics with {request.data}")
    try:
      if len(request.data['mapPoints']) != len(request.data['camPoints']) \
          or len(request.data['mapPoints']) < 4:
        return Response({"error": "Invalid number of points provided for calculation."},
                        status=status.HTTP_400_BAD_REQUEST)

      obj_points = np.array(request.data['mapPoints'], dtype=np.float32)
      img_points = np.array(request.data['camPoints'], dtype=np.float32)
      num_points = len(obj_points)

      intrinsics = np.array(request.data['intrinsics'], dtype=np.float64)
      distortion = np.array(request.data['distortion'], dtype=np.float64)
      image_size = tuple(map(int, request.data['imageSize']))

      # FIXME: Consolidate pose calculation with the one in scene_common/transform.py
      flags = cv2.CALIB_USE_INTRINSIC_GUESS | cv2.CALIB_FIX_ASPECT_RATIO
      calibrate_flags = [
        (["fx", "fy"], cv2.CALIB_FIX_FOCAL_LENGTH, 6),
        (["cx", "cy"], cv2.CALIB_FIX_PRINCIPAL_POINT, 6),
        (["k1"], cv2.CALIB_FIX_K1, 8),
        (["k2"], cv2.CALIB_FIX_K2, 8),
        (["k3"], cv2.CALIB_FIX_K3, 8),
        (["p1", "p2"], cv2.CALIB_FIX_TANGENT_DIST, 8)
      ]

      fix_intrinsics = request.data.get("fixIntrinsics", {})
      for keys, flag, min_points in calibrate_flags:
        if any(fix_intrinsics.get(key, True) for key in keys) or num_points < min_points:
          flags |= flag

      _, mtx, dist, rvecs, tvecs = cv2.calibrateCamera([obj_points], [img_points],
                                                       image_size, intrinsics,
                                                       distortion, flags=flags)

      euler, position = calculate_pose(rvecs[0], tvecs[0])
      return Response({"euler": euler, "position": position, "mtx": mtx, "dist": dist},
                      status=status.HTTP_200_OK)
    except (cv2.error, TypeError, ValueError) as e:
      log.error(f"Error calculating intrinsics: {e}")
      return Response({"error": "Invalid values provided for calculation"},
                      status=status.HTTP_400_BAD_REQUEST)
