#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Generate reference test data for C++ CoordinateTransformer unit tests.

This script replicates the Python controller's transformation logic using
pure numpy/scipy/cv2 to generate expected transformation results.
This avoids dependency on scene_common which requires building C++ extensions.

The algorithms match:
- scene_common/src/scene_common/transform.py: CameraPose class
- scene_common/src/scene_common/object.py: camLoc property (FOOT point)

Usage:
  python generate_reference_data.py

Output:
  transformation_reference.json - Reference values for C++ tests
"""

import json
import math
import os

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

# Constants matching transform.py
FALLBACK_HORIZON_DISTANCE = 100.0  # meters
EARTH_RADIUS = 6371000  # meters
MIN_HEIGHT_FOR_HORIZON = 0.1  # meters
RAY_EPSILON = 1e-6

# Path: tracker/test/tools/generate_reference_data.py
# Go up 4 levels: tools -> test -> tracker -> repo root (scenescape)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))


def load_scenes_config():
  """Load camera configurations from tracker/config/scenes.json."""
  scenes_path = os.path.join(REPO_ROOT, 'tracker', 'config', 'scenes.json')
  with open(scenes_path, 'r') as f:
    return json.load(f)


def build_intrinsics_matrix(intrinsics_cfg):
  """Build 3x3 camera intrinsics matrix K."""
  return np.array([
    [intrinsics_cfg['fx'], 0.0, intrinsics_cfg['cx']],
    [0.0, intrinsics_cfg['fy'], intrinsics_cfg['cy']],
    [0.0, 0.0, 1.0]
  ], dtype=np.float64)


def build_distortion_coeffs(intrinsics_cfg):
  """Build distortion coefficients [k1, k2, p1, p2]."""
  dist = intrinsics_cfg.get('distortion', {'k1': 0, 'k2': 0, 'p1': 0, 'p2': 0})
  return np.array([dist['k1'], dist['k2'], dist['p1'], dist['p2']], dtype=np.float64)


def build_pose_matrix(extrinsics_cfg):
  """Build 4x4 pose matrix from extrinsics.

  Matches transform.py _poseToPoseMat() lines 493-500:
    rmat = Rotation.from_euler('XYZ', rotation, degrees=True).as_matrix()
    tvecs = np.array(translation).reshape(3, -1)
    pose_mat = np.vstack((np.hstack((rmat, tvecs)), [0, 0, 0, 1]))
    diag_scale = np.diag(np.hstack([scale, [1]]))
    pose_mat = np.matmul(pose_mat, diag_scale)
  """
  rotation = extrinsics_cfg['rotation']
  translation = extrinsics_cfg['translation']
  scale = extrinsics_cfg['scale']

  # XYZ intrinsic Euler angles in degrees -> rotation matrix
  rmat = Rotation.from_euler('XYZ', rotation, degrees=True).as_matrix()

  # Build [R | t; 0 0 0 1]
  tvecs = np.array(translation).reshape(3, 1)
  pose_mat = np.vstack((np.hstack((rmat, tvecs)), [0, 0, 0, 1]))

  # Apply scale
  diag_scale = np.diag(np.hstack([scale, [1]]))
  pose_mat = np.matmul(pose_mat, diag_scale)

  return pose_mat


def get_horizon_distance(camera_z):
  """Calculate horizon distance based on camera height.

  Matches transform.py _getHorizonDistance() lines 447-456:
    camera_height = abs(self.translation.z)
    if camera_height > 0.1:
      earth_radius = 6371000
      horizon_distance = math.sqrt(2 * earth_radius * camera_height)
    else:
      horizon_distance = FALLBACK_HORIZON_DISTANCE
  """
  camera_height = abs(camera_z)
  if camera_height > MIN_HEIGHT_FOR_HORIZON:
    return math.sqrt(2 * EARTH_RADIUS * camera_height)
  return FALLBACK_HORIZON_DISTANCE


def map_pixel_to_normalized(pixel_x, pixel_y, intrinsics_mat, distortion):
  """Undistort pixel to normalized image plane.

  Matches transform.py mapPixelToNormalizedImagePlane() lines 173-195:
    undistorted_pt = cv2.undistortPoints(coords.as2Dxy.asNumpyCartesian.reshape(-1, 1, 2),
                                         self.intrinsics, self.distortion)
  """
  pixel = np.array([[[pixel_x, pixel_y]]], dtype=np.float64)
  undistorted = cv2.undistortPoints(pixel, intrinsics_mat, distortion)
  return undistorted[0, 0, 0], undistorted[0, 0, 1]


def camera_point_to_world(normalized_x, normalized_y, pose_mat, camera_origin):
  """Transform normalized camera point to world coordinates.

  Matches transform.py cameraPointToWorldPoint() lines 300-331:
    npt = np.reshape(np.array([point.asNumpyCartesian, (1, 1)]), -1)
    start = Point(np.matmul(self.pose_mat, np.array([0, 0, 0, 1]))[:3])
    end = Point(np.matmul(self.pose_mat, npt)[:3])
    pt = end - start
    if pt.z < -1e-6:
      scale = (0 - start.z) / pt.z
      pt = Point(pt.x * scale, pt.y * scale, pt.z * scale)
      pt = pt + start
  """
  # Point on unit plane (z=1) in camera coordinates
  npt = np.array([normalized_x, normalized_y, 1.0, 1.0])

  # Transform to world
  start = camera_origin  # camera position
  end = np.matmul(pose_mat, npt)[:3]

  # Ray direction
  ray = end - start

  if ray[2] < -RAY_EPSILON:
    # Ray points downward - intersect with ground plane (z=0)
    t = -start[2] / ray[2]
    result = start + t * ray
    return {'x': result[0], 'y': result[1], 'z': result[2]}

  # Ray points upward or parallel - use horizon culling
  horizon_dist = get_horizon_distance(start[2])
  xy_length = math.sqrt(ray[0]**2 + ray[1]**2)

  if xy_length > RAY_EPSILON:
    result_x = start[0] + (ray[0] / xy_length) * horizon_dist
    result_y = start[1] + (ray[1] / xy_length) * horizon_dist
    return {'x': result_x, 'y': result_y, 'z': 0.0}

  # Ray is vertical - project to point below camera
  return {'x': start[0], 'y': start[1], 'z': 0.0}


def compute_foot_point(bbox):
  """Compute FOOT (bottom-center) point of bounding box.

  This matches object.py camLoc property line 194:
    pt = Point(bounds.x + bounds.width / 2, bounds.y2)
  """
  return bbox['x'] + bbox['width'] / 2, bbox['y'] + bbox['height']


def generate_euler_to_rotation_tests():
  """Generate test cases for Euler angle to rotation matrix conversion.

  Tests the XYZ intrinsic rotation order with degrees.
  Matches: Rotation.from_euler('XYZ', rotation, degrees=True).as_matrix()
  """
  test_cases = []

  # Test cases with various Euler angles
  euler_angles = [
    [0.0, 0.0, 0.0],        # Identity
    [90.0, 0.0, 0.0],       # 90° about X
    [0.0, 90.0, 0.0],       # 90° about Y
    [0.0, 0.0, 90.0],       # 90° about Z
    [45.0, 45.0, 45.0],     # Mixed rotation
    [-135.0, 12.0, 19.0],   # Typical camera angle (from atag-qcam1)
    [-150.6, 42.35, 52.3],  # Another camera angle (from atag-qcam2)
    [-137.86, -19.44, -15.38],  # Negative angles (from camera1)
  ]

  for euler in euler_angles:
    # Compute rotation matrix using scipy (ground truth)
    rmat = Rotation.from_euler('XYZ', euler, degrees=True).as_matrix()

    test_cases.append({
      'euler_degrees': euler,
      'expected_rotation_matrix': rmat.tolist()
    })

  return test_cases


def generate_yaw_to_quaternion_tests():
  """Generate test cases for yaw-to-quaternion conversion.

  RobotVision's TrackedObject.yaw is a Z-axis rotation in radians.
  The quaternion for a pure Z rotation is:
    q = [0, 0, sin(yaw/2), cos(yaw/2)]  (x, y, z, w)

  Uses scipy as ground truth:
    Rotation.from_euler('z', yaw, degrees=False).as_quat()  # returns [x,y,z,w]
  """
  test_cases = []

  yaw_angles = [
    0.0,                        # Identity
    math.pi / 2,                # 90 degrees
    math.pi,                    # 180 degrees
    -math.pi / 2,               # -90 degrees
    math.pi / 4,                # 45 degrees
    -math.pi / 4,               # -45 degrees
    math.pi / 6,                # 30 degrees
    2.0 * math.pi / 3,          # 120 degrees
    -math.pi,                   # -180 degrees
    0.1,                        # Small angle
    -0.1,                       # Small negative angle
  ]

  for yaw in yaw_angles:
    # scipy returns [x, y, z, w] which matches our convention
    q = Rotation.from_euler('z', yaw, degrees=False).as_quat()

    test_cases.append({
      'yaw_radians': yaw,
      'expected_quaternion': q.tolist()  # [x, y, z, w]
    })

  return test_cases


def generate_pixel_to_world_tests(intrinsics_mat, distortion, pose_mat, camera_origin, camera_config):
  """Generate test cases for pixel-to-world transformation."""
  test_cases = []

  # Get image resolution (estimate from principal point if not available)
  cx = camera_config['intrinsics']['cx']
  cy = camera_config['intrinsics']['cy']
  width = int(cx * 2)
  height = int(cy * 2)

  # Test pixels: center, corners, and some intermediate points
  test_pixels = [
    {'x': cx, 'y': cy, 'name': 'image_center'},
    {'x': 0.0, 'y': 0.0, 'name': 'top_left'},
    {'x': width - 1, 'y': 0.0, 'name': 'top_right'},
    {'x': 0.0, 'y': height - 1, 'name': 'bottom_left'},
    {'x': width - 1, 'y': height - 1, 'name': 'bottom_right'},
    {'x': cx, 'y': height - 1, 'name': 'bottom_center'},
    {'x': cx / 2, 'y': cy / 2, 'name': 'quarter_point'},
  ]

  for pixel in test_pixels:
    # Step 1: Undistort to normalized image plane
    norm_x, norm_y = map_pixel_to_normalized(
        pixel['x'], pixel['y'], intrinsics_mat, distortion)

    # Step 2: Transform to world coordinates
    world = camera_point_to_world(norm_x, norm_y, pose_mat, camera_origin)

    test_cases.append({
      'name': pixel['name'],
      'pixel': {'x': pixel['x'], 'y': pixel['y']},
      'normalized': {'x': float(norm_x), 'y': float(norm_y)},
      'world': world
    })

  return test_cases


def generate_bbox_foot_tests(intrinsics_mat, distortion, pose_mat, camera_origin, camera_config):
  """Generate test cases for bounding box FOOT-to-world transformation."""
  test_cases = []

  # Get image resolution
  cx = camera_config['intrinsics']['cx']
  cy = camera_config['intrinsics']['cy']
  width = int(cx * 2)
  height = int(cy * 2)

  # Test bounding boxes at various positions
  test_bboxes = [
    {'x': cx - 50, 'y': cy - 100, 'width': 100, 'height': 200, 'name': 'center_person'},
    {'x': 10, 'y': 10, 'width': 80, 'height': 160, 'name': 'top_left_person'},
    {'x': width - 90, 'y': height - 170, 'width': 80, 'height': 160, 'name': 'bottom_right_person'},
    {'x': cx - 25, 'y': height - 100, 'width': 50, 'height': 100, 'name': 'bottom_center_small'},
  ]

  for bbox in test_bboxes:
    # Compute FOOT point (bottom-center)
    foot_x, foot_y = compute_foot_point(bbox)

    # Undistort and transform FOOT to world
    norm_x, norm_y = map_pixel_to_normalized(foot_x, foot_y, intrinsics_mat, distortion)
    world = camera_point_to_world(norm_x, norm_y, pose_mat, camera_origin)

    test_cases.append({
      'name': bbox['name'],
      'bbox': {'x': bbox['x'], 'y': bbox['y'], 'width': bbox['width'], 'height': bbox['height']},
      'foot_pixel': {'x': foot_x, 'y': foot_y},
      'world': world
    })

  return test_cases


def pixel_to_world_point(pixel_x, pixel_y, intrinsics_mat, distortion, pose_mat, camera_origin):
  """Helper: transform a single pixel to world coordinates."""
  norm_x, norm_y = map_pixel_to_normalized(pixel_x, pixel_y, intrinsics_mat, distortion)
  return camera_point_to_world(norm_x, norm_y, pose_mat, camera_origin)


def generate_bbox_size_tests(intrinsics_mat, distortion, pose_mat, camera_origin, camera_config):
  """Generate test cases for bounding box size-to-world transformation.

  Matches Python controller's projectBounds() from transform.py:
    bl, br, far_l, far_r = self._mapCameraViewCornersToWorld(rect)
    lw = bl.distance(br)
    ll1 = self.translation.distance(far_l)
    ll2 = bl.distance(far_l)
    al = math.atan2(self.translation.z, ll1)
    lh = math.sin(al) * ll2

  Size convention from moving_object.py line 247:
    size = [bbMeters.width, bbMeters.width, bbMeters.height]
  """
  test_cases = []

  cx = camera_config['intrinsics']['cx']
  cy = camera_config['intrinsics']['cy']
  width = int(cx * 2)
  height = int(cy * 2)

  # Same bboxes as bbox_foot_to_world tests
  test_bboxes = [
    {'x': cx - 50, 'y': cy - 100, 'width': 100, 'height': 200, 'name': 'center_person'},
    {'x': 10, 'y': 10, 'width': 80, 'height': 160, 'name': 'top_left_person'},
    {'x': width - 90, 'y': height - 170, 'width': 80, 'height': 160, 'name': 'bottom_right_person'},
    {'x': cx - 25, 'y': height - 100, 'width': 50, 'height': 100, 'name': 'bottom_center_small'},
  ]

  for bbox in test_bboxes:
    # Project 4 corners to world (matching _mapCameraViewCornersToWorld)
    bl = pixel_to_world_point(
        bbox['x'], bbox['y'] + bbox['height'],
        intrinsics_mat, distortion, pose_mat, camera_origin)
    br = pixel_to_world_point(
        bbox['x'] + bbox['width'], bbox['y'] + bbox['height'],
        intrinsics_mat, distortion, pose_mat, camera_origin)
    tl = pixel_to_world_point(
        bbox['x'], bbox['y'],
        intrinsics_mat, distortion, pose_mat, camera_origin)

    # Width: distance between bottom-left and bottom-right (matching lw = bl.distance(br))
    lw = math.sqrt((br['x'] - bl['x'])**2 + (br['y'] - bl['y'])**2)

    # Height via elevation angle geometry (matching projectBounds)
    # far_l = topLeft corner in world
    cam = camera_origin
    ll1 = math.sqrt(
        (cam[0] - tl['x'])**2 + (cam[1] - tl['y'])**2 + cam[2]**2)
    ll2 = math.sqrt(
        (tl['x'] - bl['x'])**2 + (tl['y'] - bl['y'])**2)
    al = math.atan2(abs(cam[2]), ll1)
    lh = math.sin(al) * ll2

    test_cases.append({
      'name': bbox['name'],
      'bbox': {'x': bbox['x'], 'y': bbox['y'],
               'width': bbox['width'], 'height': bbox['height']},
      'world_size': {
        'width_m': float(lw),
        'height_m': float(lh)
      }
    })

  return test_cases


def main():
  """Generate reference data and write to fixtures file."""
  scenes = load_scenes_config()

  output = {
    'description': 'Reference data for C++ CoordinateTransformer unit tests',
    'generated_by': 'generate_reference_data.py',
    'euler_to_rotation': generate_euler_to_rotation_tests(),
    'yaw_to_quaternion': generate_yaw_to_quaternion_tests(),
    'cameras': []
  }

  # Process each camera from scenes.json
  for scene in scenes:
    for camera_config in scene['cameras']:
      # Build transformation matrices
      intrinsics_mat = build_intrinsics_matrix(camera_config['intrinsics'])
      distortion = build_distortion_coeffs(camera_config['intrinsics'])
      pose_mat = build_pose_matrix(camera_config['extrinsics'])
      camera_origin = np.array(camera_config['extrinsics']['translation'])

      camera_data = {
        'uid': camera_config['uid'],
        'name': camera_config['name'],
        'scene_name': scene['name'],
        'intrinsics': camera_config['intrinsics'],
        'extrinsics': camera_config['extrinsics'],
        'pixel_to_world': generate_pixel_to_world_tests(
            intrinsics_mat, distortion, pose_mat, camera_origin, camera_config),
        'bbox_foot_to_world': generate_bbox_foot_tests(
            intrinsics_mat, distortion, pose_mat, camera_origin, camera_config),
        'bbox_size_to_world': generate_bbox_size_tests(
            intrinsics_mat, distortion, pose_mat, camera_origin, camera_config)
      }

      output['cameras'].append(camera_data)

  # Write output
  output_path = os.path.join(os.path.dirname(__file__), 'transformation_reference.json')
  with open(output_path, 'w') as f:
    json.dump(output, f, indent=2)

  print(f'Generated reference data: {output_path}')
  print(f'  - {len(output["euler_to_rotation"])} Euler-to-rotation test cases')
  print(f'  - {len(output["cameras"])} cameras with transformation tests')


if __name__ == '__main__':
  main()
