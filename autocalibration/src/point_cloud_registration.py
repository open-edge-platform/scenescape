# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import tempfile

import numpy as np
import open3d as o3d

from scene_common import log
from scene_common.mesh_util import extractTriangleMesh

# Rotation (degrees) applied to GLB scene meshes so that Z is up, matching the
# orientation used across the calibration pipeline.
GLB_ZUP_ROTATION = [90.0, 0.0, 0.0]

# Supported point cloud serialization formats. PCD is the default / first-class
# format; PLY is accepted for interoperability.
PCD_FORMAT = "pcd"
PLY_FORMAT = "ply"
SUPPORTED_FORMATS = (PCD_FORMAT, PLY_FORMAT)


class PointCloudRegistrationError(Exception):
  """Raised when point cloud decoding or registration fails."""


class PointCloudRegistration:
  """Sensor-agnostic point cloud registration.

  Converts a scene mesh (GLB or PLY) into a point cloud and registers an
  incoming sensor point cloud against it using Open3D Generalized ICP with a
  point-to-plane ICP refinement pass. All computation runs on the CPU in
  float64; PCD is used only as the on-disk serialization format.
  """

  DEFAULT_VOXEL_SIZE = 0.05          # meters (fine registration scale)
  COARSE_VOXEL_MULTIPLIER = 4.0      # coarse scale used for the GICP init pass
  CORRESPONDENCE_MULTIPLIER = 1.5    # max correspondence distance vs. voxel size
  NORMAL_NN = 30                     # neighbours used for normal estimation
  MAX_ITERATIONS = 50
  DEFAULT_SCENE_SAMPLE_POINTS = 200000

  def __init__(self, voxel_size=DEFAULT_VOXEL_SIZE,
               scene_sample_points=DEFAULT_SCENE_SAMPLE_POINTS,
               max_iterations=MAX_ITERATIONS):
    self.voxel_size = voxel_size
    self.coarse_voxel_size = voxel_size * self.COARSE_VOXEL_MULTIPLIER
    self.scene_sample_points = scene_sample_points
    self.max_iterations = max_iterations
    return

  @staticmethod
  def detect_format(raw_bytes):
    """Detect the point cloud serialization format from magic bytes.

    @param   raw_bytes   Raw (decoded) point cloud file bytes.

    @return  "pcd" or "ply".
    """
    if raw_bytes[:3] == b'ply':
      return PLY_FORMAT
    head = raw_bytes[:64].upper()
    if b'.PCD' in head or head.startswith(b'VERSION') or raw_bytes[:1] == b'#':
      return PCD_FORMAT
    raise PointCloudRegistrationError(
        "Point cloud data does not appear to be a valid PCD or PLY file")

  @classmethod
  def decode_point_cloud(cls, raw_bytes, fmt=None):
    """Decode raw PCD/PLY bytes into an Open3D point cloud.

    @param   raw_bytes   Raw point cloud file bytes.
    @param   fmt         Optional explicit format ("pcd" or "ply").

    @return  o3d.geometry.PointCloud
    """
    detected = cls.detect_format(raw_bytes)
    if fmt is not None and fmt.lower() != detected:
      raise PointCloudRegistrationError(
          f"Declared format '{fmt}' does not match detected format '{detected}'")

    with tempfile.NamedTemporaryFile(suffix=f".{detected}", delete=False) as tmp:
      tmp.write(raw_bytes)
      tmp_path = tmp.name
    try:
      pcd = o3d.io.read_point_cloud(tmp_path)
    finally:
      os.remove(tmp_path)

    if pcd.is_empty():
      raise PointCloudRegistrationError("Decoded point cloud contains no points")
    return pcd

  def scene_mesh_to_point_cloud(self, map_path, number_of_points=None):
    """Sample a point cloud from a scene mesh (GLB or PLY).

    @param   map_path           Path to the scene 3D model.
    @param   number_of_points   Optional override for the sample count.

    @return  o3d.geometry.PointCloud sampled from the mesh surface.
    """
    if not map_path:
      raise PointCloudRegistrationError("Scene has no map to sample")

    count = number_of_points or self.scene_sample_points
    rotation = None
    if os.path.splitext(map_path)[1].lower() == ".glb":
      rotation = GLB_ZUP_ROTATION

    tensor_mesh, _ = extractTriangleMesh([map_path], rotation)
    mesh = tensor_mesh.to_legacy()
    mesh.compute_vertex_normals()
    pcd = mesh.sample_points_uniformly(number_of_points=count)
    if pcd.is_empty():
      raise PointCloudRegistrationError(
          f"Sampling produced an empty point cloud for {map_path}")
    log.info(f"Sampled {len(pcd.points)} points from scene mesh {map_path}")
    return pcd

  def serialize_point_cloud(self, pcd, path):
    """Persist a point cloud as compressed binary PCD (float32, meters).

    @param   pcd    o3d.geometry.PointCloud to store.
    @param   path   Destination file path (".pcd").
    """
    ok = o3d.io.write_point_cloud(path, pcd, write_ascii=False, compressed=True)
    if not ok:
      raise PointCloudRegistrationError(f"Failed to write point cloud to {path}")
    return

  def _downsample(self, pcd, voxel_size):
    """Voxel-downsample a cloud and estimate normals for registration."""
    down = pcd.voxel_down_sample(voxel_size)
    down.estimate_normals(
        o3d.geometry.KDTreeSearchParamHybrid(radius=voxel_size * 2.0,
                                             max_nn=self.NORMAL_NN))
    return down

  def _initial_alignment(self, source, target):
    """Coarse initial transform aligning cloud centroids."""
    transform = np.eye(4)
    transform[:3, 3] = target.get_center() - source.get_center()
    return transform

  def register(self, source, target, initial_transform=None):
    """Register a source cloud onto a target cloud.

    Runs a coarse Generalized ICP pass followed by a fine point-to-plane ICP
    refinement. Intended for the complete-overlap case.

    @param   source              Sensor point cloud (o3d.geometry.PointCloud).
    @param   target              Scene point cloud (o3d.geometry.PointCloud).
    @param   initial_transform   Optional 4x4 initial guess (list or ndarray).

    @return  dict with keys "transform" (4x4 list), "fitness", "inlier_rmse".
    """
    if source.is_empty() or target.is_empty():
      raise PointCloudRegistrationError("Cannot register an empty point cloud")

    source_coarse = self._downsample(source, self.coarse_voxel_size)
    target_coarse = self._downsample(target, self.coarse_voxel_size)

    if initial_transform is None:
      init = self._initial_alignment(source_coarse, target_coarse)
    else:
      init = np.asarray(initial_transform, dtype=np.float64)
      if init.shape != (4, 4):
        raise PointCloudRegistrationError("initial_transform must be a 4x4 matrix")

    coarse_distance = self.coarse_voxel_size * self.CORRESPONDENCE_MULTIPLIER
    gicp = o3d.pipelines.registration.registration_generalized_icp(
        source_coarse, target_coarse, coarse_distance, init,
        o3d.pipelines.registration.TransformationEstimationForGeneralizedICP(),
        o3d.pipelines.registration.ICPConvergenceCriteria(
            max_iteration=self.max_iterations))

    source_fine = self._downsample(source, self.voxel_size)
    target_fine = self._downsample(target, self.voxel_size)
    fine_distance = self.voxel_size * self.CORRESPONDENCE_MULTIPLIER
    refined = o3d.pipelines.registration.registration_icp(
        source_fine, target_fine, fine_distance, gicp.transformation,
        o3d.pipelines.registration.TransformationEstimationPointToPlane(),
        o3d.pipelines.registration.ICPConvergenceCriteria(
            max_iteration=self.max_iterations))

    log.info(f"Registration complete: fitness={refined.fitness:.4f} "
             f"inlier_rmse={refined.inlier_rmse:.4f}")
    return {
        "transform": np.asarray(refined.transformation).tolist(),
        "fitness": refined.fitness,
        "inlier_rmse": refined.inlier_rmse,
    }
