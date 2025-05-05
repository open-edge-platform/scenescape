# Copyright (C) 2023-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import math
from threading import Lock

import cv2
import numpy as np
import open3d as o3d
import open3d.visualization.rendering as rendering
from dt_apriltags import Detector

from scene_common.glb_top_view import materialToMaterialRecord
from scene_common.mesh_util import extractTriangleMesh
from scene_common.transform import CameraIntrinsics, CameraPose

TAG_SIZE = 0.147
TILE_SIZE = 480  # Virtual Camera resolution
DISTORTION_COEFFS = np.zeros((4, 1))
MIN_APRILTAG_COUNT = 4

# Below are design parameters obtained from calibration. DO NOT MODIFY
DEFAULT_ROTATION_MATRIX = [180, 0, 0]
DEFAULT_MESH_ROTATION = np.array([90, 0, 0])
SUNLIGHT_INTENSITY = 100000
SUNLIGHT_DIRECTION = [0.0, 0.0, -1.0]
SUNLIGHT_COLOR = [1.0, 1.0, 1.0]
DEFAULT_FOV = 70

class CameraCalibrationApriltag:
  """
  Class performs the auto-camera-calibration tasks on the map_image and camera image.
  """
  atag_detector = None
  result_data_3d = None
  apriltags_2d_data = None
  cam_calib_lock = Lock()
  scene_id = None
  dist_coefs = DISTORTION_COEFFS
  triangle_mesh = None
  scene_name = None
  intrinsic_matrix_2d = None
  extrinsic_matrix = None

  def __init__(self, map_filename, scale, scene_name, intrinsic_matrix=None, tag_size=TAG_SIZE):
    """! Initializes the class with various data necessary for preprocessing.
    @param   map_filename        Filename of map object (image/object file).
    @param   scale               Scale size in float(as in database).
    @param   scene_name          Name of the scene as in database.
    @param   intrinsic_matrix    Camera intrinsic matrix.

    @return  None
    """
    o3d.utility.set_verbosity_level(o3d.utility.VerbosityLevel.Error)
    if not map_filename or not scale:
      raise ValueError("No map available for scene")

    self.scene_name = scene_name
    self.map_info = []
    self.tag_size = tag_size
    self.fixed_step_size = 4 * self.tag_size
    self.zval = self.fixed_step_size / math.tan(math.radians(DEFAULT_FOV / 2))

    supported_types = ["png", "jpg", "jpeg"]
    if map_filename.split(".")[-1].lower() in supported_types:
      self.map_info.append(map_filename)
      self.map_info.append(scale)
    else:
      self.map_info.append(map_filename)

    # Get the detector object.
    self.atag_detector = Detector(searchpath=['apriltags'],
                                  families='tag36h11',
                                  nthreads=1,
                                  quad_decimate=1.0,
                                  quad_sigma=0.0,
                                  refine_edges=1,
                                  decode_sharpening=0.25,
                                  debug=0)
    self.intrinsic_matrix_2d = intrinsic_matrix

    return


  def renderCamView(self, mesh, tensor_mesh, intrinsic_matrix, extrinsic_matrix, res_x, res_y):
    """! Render an image on camera plane with given intrinsic and extrinsic matrices
    @param   mesh                Triangular mesh.
    @param   intrinsic_matrix    Camera intrinsic matrix.
    @param   extrinsic_matrix    Extrinsix matrix in 4x4 format.
    @param   res_x               Image resolution in x-axis.
    @param   res_y               Image resolution in y-axis

    @return  img                 Image in numpy format.
    """
    renderer = rendering.OffscreenRenderer(res_x, res_y)
    if tensor_mesh is None:
      material = o3d.visualization.rendering.MaterialRecord()
      material.shader = mesh.material.material_name
      material.albedo_img = mesh.material.texture_maps["albedo"].to_legacy()
    else:
      material = materialToMaterialRecord(tensor_mesh[0].material)
    renderer.scene.add_geometry("mesh", mesh, material)
    renderer.scene.scene.set_sun_light(SUNLIGHT_DIRECTION,
                                       SUNLIGHT_COLOR,
                                       SUNLIGHT_INTENSITY)
    renderer.scene.scene.enable_sun_light(True)
    renderer.scene.show_axes(False)
    renderer.setup_camera(intrinsic_matrix, extrinsic_matrix, res_x, res_y)
    img = renderer.render_to_image()
    return np.array(img)

  def findApriltagsInFrame(self, source_image, store=False, intrinsics=None):
    """! Detects the apriltags in the source image using the apriltag class detector.
    @param   source_image    Image in which apriltags are to be detected.
    @param   store           Store 2d-apriltag info in CameraCalibrationApriltag class.
    @param   intrinsics      Source Camera Intrinsics.

    @return  dict            Return data format {"apriltag_id":"apriltag_id_centers"}.
    """
    intrinsics_matrix = intrinsics if intrinsics is not None else self.intrinsic_matrix_2d
    grayed_image = cv2.cvtColor(source_image, cv2.COLOR_BGR2GRAY)
    tags = self.atag_detector.detect(grayed_image,
                                     estimate_tag_pose=True,
                                     camera_params=(intrinsics_matrix[0][0],
                                                    intrinsics_matrix[1][1],
                                                    intrinsics_matrix[0][2],
                                                    intrinsics_matrix[1][2]),
                                     tag_size=self.tag_size)
    apriltag_2d_centers = {str(tag.tag_id): tag.center for tag in tags}
    if store:
      self.apriltags_2d_data = apriltag_2d_centers
    return apriltag_2d_centers

  def identifyApriltagsInScene(self, res_x, res_y, rotational_matrix):
    """! Identify apriltags in a scene map, based on a bounding box approach.
    @param   res_x               Image resolution in x-axis.
    @param   res_y               Image resolution in y-axis.
    @param   rotational_matrix   Rotational matrix in 3x3 format.

    @return  None
    """
    apriltag_3d_data = {}
    new_intrinsic_matrix = CameraIntrinsics(intrinsics=DEFAULT_FOV,
                                            resolution=[TILE_SIZE, TILE_SIZE]).intrinsics
    self.triangle_mesh, self.tensor_tmesh = extractTriangleMesh(self.map_info, DEFAULT_MESH_ROTATION)
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(self.triangle_mesh)
    max_bounding_box = self.triangle_mesh.get_max_bound()
    min_bounding_box = self.triangle_mesh.get_min_bound()

    # Move virtual camera within bounding box, detect apriltags and
    # use raycasting to get 3D coordinates of apriltag center points.
    bby = min_bounding_box[1].item()
    while bby < max_bounding_box[1].item():
      bbx = min_bounding_box[0].item()
      while bbx < max_bounding_box[0].item():
        pose_dict = {
          'rotation': rotational_matrix,
          'translation': [bbx, bby, self.zval],
          'scale': [1.0, 1.0, 1.0]
        }
        camera_pose = CameraPose(pose=pose_dict,
                                 intrinsics=new_intrinsic_matrix)
        extrinsic_matrix = np.linalg.inv(camera_pose.pose_mat)
        rendered_img = self.renderCamView(self.triangle_mesh,
                                          self.tensor_tmesh,
                                          new_intrinsic_matrix,
                                          extrinsic_matrix,
                                          res_x, res_y)
        imgpts = self.findApriltagsInFrame(rendered_img, intrinsics=new_intrinsic_matrix)
        if len(imgpts) != 0:
          current_apriltags = self.getCorresponding3DPoints(imgpts,
                                                            new_intrinsic_matrix,
                                                            camera_pose.pose_mat,
                                                            scene)
          apriltag_3d_data |= current_apriltags
        bbx = bbx + self.fixed_step_size
      bby = bby + self.fixed_step_size

    self.result_data_3d = apriltag_3d_data
    return

  def createRaysForCasting(self, img_pts, pose_mat, intrinsic_matrix):
    """! Generate Rays for casting.
    @param    img_pts           Apriltag Points in 2d plane.
    @param    pose_mat          Camera Pose Matrix.
    @param    intrinsic_matrix  Intrinsic Matrix.

    @return   rays              List of rays.
    """
    homogeneous_pose_mat = np.matmul(pose_mat,
                                     np.array([0.0, 0.0, 0.0, 1]))[:3]
    rays = []
    for id in img_pts:
      undistort_points = cv2.undistortPoints(np.float64(img_pts[id]),
                                             intrinsic_matrix, None)[0][0]
      undistorted_pose_mat = np.matmul(pose_mat,
                                         np.append(undistort_points, [1., 1, ]))[0:3]
      ray = [homogeneous_pose_mat, undistorted_pose_mat]
      rays.append(ray)
    rays = [[r[0], r[1] - r[0]] for r in rays]
    rays = [np.append(r[0], r[1] / np.linalg.norm(r[1])) for r in rays]
    rays = o3d.core.Tensor(rays, dtype=o3d.core.Dtype.Float32)
    return rays

  def getImagePointsFromRayCasting(self, rays, img_pts, cast_results):
    """! Based on ray casting(Open3d), get matching 2d image points in 3d plane.
    @param    rays              Rays from ray casting.
    @param    img_pts           Image points in 2d image space.
    @param    cast_results      Ray casting results.

    @return   result_array_3d   Corresponding points in 2d and 3d plane.
    """
    result_array_3d = {}
    for i, id in enumerate(img_pts.keys()):
      # Results of succesful hit of rays from image to mesh.
      # http://www.open3d.org/docs/release/python_api/open3d.t.geometry.RaycastingScene.html
      pt = rays[i][:3] + rays[i][-3:] * cast_results['t_hit'][i]
      point = pt.numpy().tolist()
      if float('inf') not in point or float('-inf') not in point:
        result_array_3d[id] = point

    return result_array_3d

  def getCorresponding3DPoints(self, points_2d, intrinsics, pose_mat, scene):
    rays = self.createRaysForCasting(points_2d,
                                     pose_mat,
                                     intrinsics)
    cast_results = scene.cast_rays(rays)
    return self.getImagePointsFromRayCasting(rays,
                                             points_2d,
                                             cast_results)

  def calculatePointCorrespondences(self, intrinsics, pose_mat):
    """! Calculate correspondences between points in 2D and 3D using the scene mesh.
    @param   intrinsics             Camera intrinsics.
    @param   pose_mat               Camera pose.

    @return  points_3d, points_2d   Points in 3D and 2D plane.
    """
    scene = o3d.t.geometry.RaycastingScene()
    if not self.triangle_mesh:
      self.triangle_mesh, self.tensor_tmesh = extractTriangleMesh(self.map_info,
                                                                  DEFAULT_MESH_ROTATION)
    scene.add_triangles(self.triangle_mesh)
    result_array_3d = self.getCorresponding3DPoints(self.apriltags_2d_data,
                                                    intrinsics,
                                                    pose_mat,
                                                    scene)
    points_3d, points_2d = [], []
    for point in self.apriltags_2d_data:
      if point in result_array_3d:
        points_2d.append(self.apriltags_2d_data[point].tolist())
        points_3d.append(result_array_3d[point])
    return points_3d, points_2d

  def getCameraPoseInScene(self):
    """! Function calculates the pose of the camera with respect
         to the scene based on solvepnp function from Opencv.

    @return  pose_mat   Camera pose matrix i.e camera to world transform
    """
    # We need a minimum of 4 points for SolvePNP algorithm to work.
    if len(self.apriltags_2d_data) < MIN_APRILTAG_COUNT or \
       len(self.result_data_3d) < MIN_APRILTAG_COUNT:
      return None
    points_3d, points_2d = [], []
    for key in self.apriltags_2d_data:
      if key in self.result_data_3d:
        points_3d.append(self.result_data_3d[key])
        points_2d.append(self.apriltags_2d_data[key])
    if len(points_2d) < MIN_APRILTAG_COUNT:
      raise TypeError(f"{len(points_2d)} apriltags found in camera feed, "
                      f"at least {MIN_APRILTAG_COUNT} expected")
    computed_pose_data = {"camera points": np.array(points_2d, dtype="float32"),
                          "map points": np.array(points_3d, dtype="float32"),
                          "resolution": (TILE_SIZE, TILE_SIZE)}
    camera_intrinsics = CameraIntrinsics(intrinsics=self.intrinsic_matrix_2d)
    return CameraPose(pose=computed_pose_data,
                      intrinsics=camera_intrinsics).pose_mat

  def getCameraFrustum(self):
    """! Creates 5 points, when connected by a line, looks like a camera view of the scene.

    @return  points   Five points on image, when connected by a line looks like a frustum.
    """
    res_x, res_y = TILE_SIZE, TILE_SIZE
    bottom_right_corner = cv2.undistortPoints(np.float64([res_x, res_y]),
                                              self.intrinsic_matrix_2d,
                                              None)[0][0].tolist()
    top_left_corner = cv2.undistortPoints(np.float64([0, 0]),
                                          self.intrinsic_matrix_2d,
                                          None)[0][0].tolist()
    return [
      [0, 0, 0],
      [bottom_right_corner[0], bottom_right_corner[1], 1],
      [bottom_right_corner[0], top_left_corner[1], 1],
      [top_left_corner[0], top_left_corner[1], 1],
      [top_left_corner[0], bottom_right_corner[1], 1],
    ]
