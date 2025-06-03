from typing import Union
from pathlib import Path
import functools
import numpy as np
import pycolmap
import open3d as o3d
import torch
from torch.utils.dlpack import from_dlpack as torch_from_dlpack
from hloc.utils.read_write_model import Camera
from hloc import logger

Image = o3d.t.geometry.Image
Tensor = o3d.core.Tensor


def Tinv(Tr):
    """Inverse transform for homogenous matrix"""
    return np.vstack(
        (np.hstack((Tr[:3, :3].T, -Tr[:3, :3].T @ Tr[:3, 3:])), [[0, 0, 0, 1]])
    )


def to_homogeneous(p):
    return np.pad(p, ((0, 0),) * (p.ndim - 1) + ((0, 1),), constant_values=1)


def vector_to_cross_product_matrix(v):
    return np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])


def compute_epipolar_errors(qvec_r2t, tvec_r2t, p2d_r, p2d_t):
    T_r2t = pose_matrix_from_qvec_tvec(qvec_r2t, tvec_r2t)
    # Compute errors in normalized plane to avoid distortion.
    E = vector_to_cross_product_matrix(T_r2t[:3, -1]) @ T_r2t[:3, :3]
    l2d_r2t = (E @ to_homogeneous(p2d_r).T).T
    l2d_t2r = (E.T @ to_homogeneous(p2d_t).T).T
    errors_r = np.abs(np.sum(to_homogeneous(p2d_r) * l2d_t2r, axis=1)) / np.linalg.norm(
        l2d_t2r[:, :2], axis=1
    )
    errors_t = np.abs(np.sum(to_homogeneous(p2d_t) * l2d_r2t, axis=1)) / np.linalg.norm(
        l2d_r2t[:, :2], axis=1
    )
    return E, errors_r, errors_t


def pose_matrix_from_qvec_tvec(qvec, tvec):
    pose = np.eye(4)
    pose[:3, :3] = pycolmap.qvec_to_rotmat(qvec)
    pose[:3, -1] = tvec
    return pose


def qvec_tvec_from_pose_matrix(pose):
    qvec = pycolmap.rotmat_to_qvec(pose[:3, :3])
    tvec = pose[:3, -1]
    return qvec, tvec


def get_intrinsic_mat(camera: Camera):
    distortion = np.array([0.0])
    if camera.model.upper() in ("SIMPLE_PINHOLE", "SIMPLE_RADIAL"):
        fx, cx, cy, *distortion = camera.params
        fy = fx
    elif camera.model.upper() in ("PINHOLE", "RADIAL", "OPENCV"):
        fx, fy, cx, cy, *distortion = camera.params
    else:
        raise ValueError(
            f"Unsupported camera model {camera.model}. "
            "Only SIMPLE_PINHOLE, PINHOLE, SIMPLE_RADIAL, RADIAL and OPENCV are supported."
        )
    if not np.allclose(distortion, 0):
        logger.warning("Ignoring distortion in camera.")

    intrinsic_mat = Tensor([[fx, 0, cx], [0, fy, cy], [0, 0, 1]])  #
    return intrinsic_mat


# @torch.no_grad
def interpolate_scan(depth: Image, camera: Camera, kp: np.ndarray):

    if (depth.rows, depth.columns) != (camera.height, camera.width):
        raise ValueError(
            f"Depth camera intrinsic shape ({camera.height},{camera.width})"
            f"does not match depth image shape {depth.shape[:2]}."
        )
    intrinsic_mat = get_intrinsic_mat(camera)
    scan = depth.create_vertex_map(
        intrinsics=intrinsic_mat, invalid_fill=np.nan
    ).as_tensor()

    h, w, c = scan.shape
    kp = kp / np.array([[w - 1, h - 1]], dtype=kp.dtype) * 2 - 1
    assert np.all(kp > -1) and np.all(kp < 1)
    scan = torch_from_dlpack(scan.to_dlpack()).permute(2, 0, 1)[None]
    kp = torch.from_numpy(kp)[None, None]
    grid_sample = torch.nn.functional.grid_sample

    # To maximize the number of points that have depth:
    # do bilinear interpolation first and then nearest for the remaining points
    interp_lin = grid_sample(scan, kp, align_corners=True, mode="bilinear")[0, :, 0]
    interp_nn = torch.nn.functional.grid_sample(
        scan, kp, align_corners=True, mode="nearest"
    )[0, :, 0]
    interp = torch.where(torch.isnan(interp_lin), interp_nn, interp_lin)
    valid = ~torch.any(torch.isnan(interp), 0)

    kp3d = interp.T.numpy()
    valid = valid.numpy()
    return kp3d, valid


def interpolate_mesh(
    mesh_path: Union[Path, str],
    pose: np.ndarray,  # extrinsics: world_to_camera
    camera: Camera,  # intrinsics
    kp: np.ndarray,  # (N, 2)
):
    """Create ray casting data structure for mesh interpolation and provide 3D
    points for input 2D points and camera calibration (intrinsics + extrinics).

    Args:

        mesh_path (str or Path): path to mesh file.
        pose (np.ndarray):  extrinsics- world_to_camera.
        camera (Camera):  camera intrinsics.
        kp (np.ndarray): 2D keypoints with shape (N, 2).

    Returns:
        tuple of 3D keypoints (shape (N,3)) and valid mask (shape (N,))
    """

    @functools.lru_cache(maxsize=8)
    def get_raycasting_scene(mesh_path: str):
        mesh = o3d.t.io.read_triangle_mesh(mesh_path)
        rc_scene = o3d.t.geometry.RaycastingScene()
        rc_scene.add_triangles(mesh)
        return rc_scene

    K = get_intrinsic_mat(camera).numpy()
    K_inv = np.linalg.inv(K)
    camera_center = (-pose[:3, :3].T @ pose[:3, 3:]).astype(np.float32)
    ray_dirn = (
        pose[:3, :3].T @ K_inv @ np.vstack((kp.T, np.ones((1, kp.shape[0]))))
    ).astype(np.float32)
    rays = Tensor.from_numpy(
        np.hstack((np.repeat(camera_center.T, kp.shape[0], axis=0), ray_dirn.T))
    )
    rc_scene = get_raycasting_scene(str(mesh_path))
    result = rc_scene.cast_rays(rays)
    valid = result["t_hit"].isfinite().numpy()
    kp3d = camera_center + ray_dirn * result["t_hit"].reshape((1, -1)).numpy()
    return kp3d.T, valid
