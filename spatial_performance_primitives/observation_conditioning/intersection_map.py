# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Vendored from scenescape-v2-architecture/algorithms/amodalreasoner.
# See NOTICE in this package for provenance requirements.

"""Dense per-pixel depth/normal map built by ray-casting the static scene mesh.

Implements the depth-map idea from docs/ALGORITHM_V2.md: at load time cast one ray
per pixel into the (static, world-frame) scene mesh and cache the hit distance and
surface normal in dense H x W matrices so later lookups are O(1).
"""
import open3d as o3d
import numpy as np





class DepthMap: 
  def __init__(self, camera_intrinsics: np.ndarray, camera_extrinsics: np.ndarray, mesh: o3d.t.geometry.TriangleMesh, width: int, height: int, num_layers: int = 1):
    """
    camera_intrinsics: 3x3 (or 3x4) pinhole matrix K = [[fx,0,cx],[0,fy,cy],[0,0,1]].
    camera_extrinsics: 4x4 camera-to-world pose [R|t]; the mesh lives in the world frame.
    mesh:              tensor TriangleMesh expressed in the world frame.
    width, height:     image size in pixels.
    num_layers:        depth-peeling layers stored per pixel (1 = first hit only).
    """
    self.camera_intrinsics = camera_intrinsics
    self.camera_extrinsics = np.asarray(camera_extrinsics, dtype=np.float64)
    self.width = int(width)
    self.height = int(height)
    self.num_layers = int(num_layers)
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(mesh)
    # TODO: Check if needed, adjust scene origin to be at 0,0,0 of the world origin
    # to do this you need to do the following:  mesh.translate(-mesh.get_center())
    # I am unsure if this is valid or if this removes some pre-existing information the mesh already encodes about the origin.
    # For example if the center of the scene is different that the origin and the origin is in the bottom left corner of the scene.
    # Or does get_center simply return where the origin of the scene is placed?
    self.scene = scene
    self.dummy_pixel_map = self._create_pseudo_3d_pixel_grid(height, width)
    self.normal_map = None
    self.t_hit_map = None

  def _create_pseudo_3d_pixel_grid(self, height: int, width: int) -> np.ndarray:
    # (H, W, 3) homogeneous pixel coords [x, y, 1]; indexed [row=y, col=x].
    ys, xs = np.indices((height, width))
    ones = np.ones((height, width))
    return np.stack((xs, ys, ones), axis=-1)

  def _convert_pixel_to_camera_space(self) -> np.ndarray:
    """ 
      Here we convert a set of pixel coordinates to there coordinates in image space given the camera intrinsics 
      x = (n - c_x) / a
      y = (m - c_y) / b
      z = 1
      Or in matrix form: K^-1 [n m 1]^T, where K is the camera intrinsics. 

      Returns: camera_space_points in the shape of (H, W, 3).
    """
    intrinsics = self.camera_intrinsics
    if intrinsics.shape != (3, 3):
      intrinsics = intrinsics[:3, :3]
    camera_space_points = self.dummy_pixel_map @ np.linalg.inv(intrinsics).T
    return camera_space_points

  def _convert_camera_coords_to_world_space(self, camera_space_points: np.ndarray) -> np.ndarray:
    """
    Assuming that our camera extrinsics matrix is a camera-to-world translation/rotation
    we convert the image coordinates for each original pixel (and now coordinate in image space)        
    to be defined in the world coordinate system.
    
    *Note: If the expected camera extrinsic matrix is defined as world-to-camera we can still use this method, 
               but will need to invert the camera-extrinsic matrix first. 
    
    """
    homogenous_camera_extrinsics = self.camera_extrinsics
    if self.camera_extrinsics.shape != (4,4):
      homogenizing_arr = np.array([0,0,0,1]).reshape(1, -1)
      homogenous_camera_extrinsics = np.vstack((homogenous_camera_extrinsics, homogenizing_arr))
    ones_grid = np.ones((*camera_space_points.shape[:-1], 1))
    homogenous_cam_coords = np.concatenate((camera_space_points, ones_grid), axis=-1)
    # Rigid extrinsics keep w = 1, so no perspective divide is needed.
    homog_world_coordinate_points = homogenous_cam_coords @ homogenous_camera_extrinsics.T
    world_coords = homog_world_coordinate_points[..., :3]
    return world_coords


  def _get_dir_vecs(self, world_coords: np.ndarray) -> np.ndarray:
    world_coord_cam_center = self.camera_extrinsics[:3, 3]
    dir_vecs = world_coords - world_coord_cam_center
    normalized_dir_vecs = dir_vecs / np.linalg.norm(dir_vecs, axis=-1, keepdims=True)
    return normalized_dir_vecs

  def get_scene(self):
    return self.scene
  
  def cast_np(self, dir_vecs: np.ndarray, origin: np.ndarray | None = None):
    """Cast rays (origin, unit dirs) and return (primitive_normals, t_hit) as numpy."""
    dir_vecs = dir_vecs.astype(np.float32)
    if origin is None:
      origin = self.camera_extrinsics[:3, 3].astype(np.float32)
    origin_grid = origin
    if origin.shape != dir_vecs.shape:
      origin_grid = np.broadcast_to(origin, dir_vecs.shape)
    rays6 = np.concatenate((origin_grid, dir_vecs), axis=-1).astype(np.float32)
    res = self.scene.cast_rays(o3d.core.Tensor(rays6, dtype=o3d.core.Dtype.Float32))
    return res["primitive_normals"].numpy(), res["t_hit"].numpy()


  def _peel_rays(self, origins: np.ndarray, dirs: np.ndarray,
                  num_layers: int | None = None, eps: float = 1e-4):
    """Cast rays and peel through up to num_layers successive hits along each ray.

    origins, dirs: (..., 3) arrays; dirs assumed unit length.
    Returns (t_hit, normals): t_hit (..., num_layers) cumulative distance from the original
    origin, normals (..., num_layers, 3). Misses are inf / NaN and terminate a ray's
    remaining layers (you cannot peel past a miss).
    """
    num_layers = self.num_layers if num_layers is None else num_layers
    origins = np.asarray(origins, dtype=np.float32)
    dirs = np.asarray(dirs, dtype=np.float32)
    batch = origins.shape[:-1]
    t_layers = np.full(batch + (num_layers,), np.inf, dtype=np.float32)
    n_layers = np.full(batch + (num_layers, 3), np.nan, dtype=np.float32)

    cumulative = np.zeros(batch, dtype=np.float32)  # distance along dir from origin to cur_origin
    cur_origin = origins
    alive = np.ones(batch, dtype=bool)              # rays still producing hits

    for layer in range(num_layers):
      rays6 = np.concatenate((cur_origin, dirs), axis=-1).astype(np.float32)
      res = self.scene.cast_rays(o3d.core.Tensor(rays6, dtype=o3d.core.Dtype.Float32))
      t = res["t_hit"].numpy()                # distance from cur_origin
      nrm = res["primitive_normals"].numpy()  # (..., 3)
      hit = np.isfinite(t) & alive
      t_total = cumulative + t                # distance from the original origin
      t_layers[..., layer] = np.where(hit, t_total, np.inf)
      n_layers[..., layer, :] = np.where(hit[..., None], nrm, np.nan)
      # Nudge the next origin just past this hit so it is not re-detected.
      cumulative = np.where(hit, t_total + eps, cumulative)
      cur_origin = origins + cumulative[..., None] * dirs
      alive = hit
      if not alive.any():
        break
    return t_layers, n_layers

  def populate(self):
    camera_space_points = self._convert_pixel_to_camera_space()
    world_space_points = self._convert_camera_coords_to_world_space(camera_space_points)
    dir_vecs = self._get_dir_vecs(world_space_points)
    origins = np.broadcast_to(self.camera_extrinsics[:3, 3], dir_vecs.shape)
    t_layers, n_layers = self._peel_rays(origins, dir_vecs)
    if self.num_layers == 1:
      # Preserve first-hit shapes: (H, W) and (H, W, 3).
      self.t_hit_map = t_layers[..., 0]
      self.normal_map = n_layers[..., 0, :]
    else:
      self.t_hit_map = t_layers      # (H, W, num_layers)
      self.normal_map = n_layers     # (H, W, num_layers, 3)

  def query(self, world_points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    This is the backwards conversion from ray to pixel now.
    
    To do this we simply multiply the camera intrinsics by each ray which gives us provides us back a pixelthat we can use to look up the values in our depth map
    
    World-Points is an array that will be in the shape: [n, 3], which we will need to append 1 onto to make the coversion work

    Returns (t_hit, normals). Single layer: t_hit (n,), normals (n, 3). Peeled
    (num_layers > 1): t_hit (n, num_layers), normals (n, num_layers, 3).
    Misses/out-of-frame are inf / NaN.
    """
    world_points = np.asarray(world_points, dtype=np.float64)
    n = world_points.shape[0]
    ones = np.ones((n, 1))
    homog_world = np.hstack((world_points, ones))                          # (n, 4)
    cam_points = homog_world @ np.linalg.inv(self.camera_extrinsics).T      # (n, 4)
    camera_intrinsics = self.camera_intrinsics
    if camera_intrinsics.shape == (3, 3):
      camera_intrinsics = np.hstack((camera_intrinsics, np.zeros((3, 1))))
    homog_px = cam_points @ camera_intrinsics.T                            # (n, 3): [u, v, w]
    depth = homog_px[:, 2]                                                  # camera-frame Z
    pixel_coords = homog_px[:, :2] / homog_px[:, 2:3]                       # (n, 2): [x, y]

    if self.num_layers == 1:
      t_hit = np.full(n, np.inf)
      normals = np.full((n, 3), np.nan)
    else:
      t_hit = np.full((n, self.num_layers), np.inf)
      normals = np.full((n, self.num_layers, 3), np.nan)
    if self.t_hit_map is None or self.normal_map is None:
      return t_hit, normals

    xs = np.round(pixel_coords[:, 0]).astype(int)
    ys = np.round(pixel_coords[:, 1]).astype(int)
    # Keep points in front of the camera (Z > 0) and inside the image frame.
    valid = (depth > 0) & (xs >= 0) & (xs < self.width) & (ys >= 0) & (ys < self.height)
    t_hit[valid] = self.t_hit_map[ys[valid], xs[valid]]
    normals[valid] = self.normal_map[ys[valid], xs[valid]]
    return t_hit, normals
  

