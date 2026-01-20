# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Sequence, Union
import pickle
import numpy as np
from scipy.spatial.transform import Rotation as R
import h5py
import pycolmap
import open3d as o3d
from hloc import logger
from hloc.utils.evaluate import evaluate, find_nearest_pose
from hloc.utils.parsers import parse_retrieval, names_to_pair
from hloc.utils.read_write_model import Camera, qvec2rotmat
from hloc.utils.geometry import (
    get_intrinsic_mat,
    interpolate_mesh,
    interpolate_scan,
    pose_matrix_from_qvec_tvec,
)

Tensor = o3d.core.Tensor
Image = o3d.t.geometry.Image
RGBDImage = o3d.t.geometry.RGBDImage
PointCloud = o3d.t.geometry.PointCloud


def qxyzw_to_qwxyz(qxyzw: np.ndarray):
  qwxyz = np.empty_like(qxyzw)
  qwxyz[..., 1:] = qxyzw[..., :3]
  qwxyz[..., 0] = qxyzw[..., 3]
  return qwxyz


def qwxyz_to_qxyzw(qwxyz: np.ndarray):
  qxyzw = np.empty_like(qwxyz)
  qxyzw[..., :3] = qwxyz[..., 1:]
  qxyzw[..., 3] = qwxyz[..., 0]
  return qxyzw


def qxyzwtinv(qxyzw: np.ndarray, tvec: np.ndarray):
  qinv = qxyzw.copy()
  qinv[:3] = -qinv[:3]
  tinv = -R.from_quat(qinv).apply(tvec)
  return qinv, tinv


def pose_from_cluster(
    dataset_dir: Path,
    db_feature_files: Sequence[h5py.File],
    q: str,
    retrieved: Sequence[str],
    feature_files: Sequence[h5py.File],
    match_files: Sequence[h5py.File],
    retrieval_calibration: Dict[str, SimpleNamespace],
    query_intrinsics: Dict,
    skip=0,
    match_dense: Union[bool, Sequence[bool]] = False,
    depth_scale=1.0,
    depth_max=9.9,
):
  """Estimate camera pose from a cluster of retrieved calibrated images and
  matching keypoints.

  Args:
      dataset_dir: Path to dataset.
      db_feature_files: List of files with 2D keypoints in database.
      q: Query image filename.
      retrieved: List of retrieved database images files.
      feature_files: Sequence[h5py.File].
      match_files: Sequence[h5py.File].
      retrieval_calibration: Dict[str, SimpleNamespace].
      query_intrinsics: Dict.
      skip: Skip matching an image if n_keypoints < skip.
      match_dense: Semi dense matching with a single model for both feature
          detection and matching.
      depth_scale: Depth scale, if depth is read from png images.
      depth_max: Max cutoff depth, if depth is read from png images.
  """

  logger.info(f"DEBUG pose_from_cluster: Starting with q={q}, retrieved={retrieved}")
  logger.info(f"DEBUG pose_from_cluster: query_intrinsics type={type(query_intrinsics)}")
  
  all_mkpq = []
  all_mkpr = []
  all_mkp3d = []
  all_indices = []
  if isinstance(match_dense, bool):
    match_dense = (match_dense,) * len(feature_files)
  
  logger.info(f"DEBUG pose_from_cluster: Reading keypoints from feature files")
  try:
    kpqs = tuple(
        ff[q]["keypoints"].__array__().astype(np.float32) for ff in feature_files
    )  # read all keypoint types
    logger.info(f"DEBUG pose_from_cluster: Successfully read {len(kpqs)} keypoint arrays")
  except Exception as e:
    logger.error(f"DEBUG pose_from_cluster: Error reading keypoints: {e}")
    raise
  
  num_matches = 0

  for i, r in enumerate(retrieved):
    logger.info(f"DEBUG pose_from_cluster: Processing retrieved image {i}: {r}")
    pair = names_to_pair(q, r)
    mkpq, mkpr = [], []
    for md, ff, mf, kpq in zip(match_dense, db_feature_files, match_files, kpqs):
      logger.info(f"DEBUG pose_from_cluster: Processing match - md={md}, pair={pair}")
      try:
        if md:
          logger.info(f"DEBUG pose_from_cluster: Dense matching mode")
          mkpq.append(mf[pair]["keypoints0"].__array__().astype(np.float32))
          mkpr.append(mf[pair]["keypoints1"].__array__().astype(np.float32))
        else:
          logger.info(f"DEBUG pose_from_cluster: Sparse matching mode")
          kpr = ff[r]["keypoints"].__array__().astype(np.float32)
          m = mf[pair]["matches0"].__array__()
          v = m > -1
          # Check if valid matches exist to index into keypoints array
          if len(kpq) != len(v):
            logger.info(f"DEBUG pose_from_cluster: Length mismatch - kpq:{len(kpq)}, v:{len(v)}, continuing")
            continue
          mkpq.append(kpq[v])
          mkpr.append(kpr[m[v]])
        logger.info(f"DEBUG pose_from_cluster: Added matches - mkpq len:{len(mkpq[-1])}, mkpr len:{len(mkpr[-1])}")
      except Exception as e:
        logger.error(f"DEBUG pose_from_cluster: Error in match processing: {e}")
        import traceback
        logger.error(f"DEBUG pose_from_cluster: Traceback:\n{traceback.format_exc()}")
        continue
        
    # Avoid stacking of an empty array
    if len(mkpq) == 0:
      logger.info(f"DEBUG pose_from_cluster: Empty mkpq array for {r}, continuing")
      continue
      
    logger.info(f"DEBUG pose_from_cluster: Stacking mkpq and mkpr arrays")
    try:
      mkpq = np.vstack(mkpq)  # TODO: non-maxima suppression
      mkpr = np.vstack(mkpr)
      logger.info(f"DEBUG pose_from_cluster: Stacked shapes - mkpq:{mkpq.shape}, mkpr:{mkpr.shape}")
    except Exception as e:
      logger.error(f"DEBUG pose_from_cluster: Error stacking arrays: {e}")
      import traceback
      logger.error(f"DEBUG pose_from_cluster: Traceback:\n{traceback.format_exc()}")
      continue
      
    if mkpr.shape[0] < skip:
      logger.info(f"DEBUG pose_from_cluster: Too few matches ({mkpr.shape[0]} < {skip}), skipping {r}")
      continue

    num_matches += len(mkpq)
    logger.info(f"DEBUG pose_from_cluster: Total num_matches now: {num_matches}")

    logger.info(f"DEBUG pose_from_cluster: Getting depth_type from {retrieval_calibration[r].depth_name}")
    depth_type = retrieval_calibration[r].depth_name.split(".")[1]
    logger.info(f"DEBUG pose_from_cluster: depth_type={depth_type}")
    valid = None
    mkp3d = None

    if depth_type in ("ply", "stl", "obj", "fbx", "gltf", "glb"):
      logger.info(f"DEBUG pose_from_cluster: Processing mesh depth type")
      try:
        Tcw = pose_matrix_from_qvec_tvec(
            retrieval_calibration[r].qvec, retrieval_calibration[r].tvec
        )
        logger.info(f"DEBUG pose_from_cluster: Calling interpolate_mesh")
        mkp3d, valid = interpolate_mesh(
            Path(dataset_dir, retrieval_calibration[r].depth_name),
            Tcw,
            retrieval_calibration[r].intrinsics,
            mkpr,
        )
        logger.info(f"DEBUG pose_from_cluster: interpolate_mesh returned mkp3d:{mkp3d.shape if mkp3d is not None else 'None'}, valid:{valid.shape if valid is not None else 'None'}")
      except Exception as e:
        logger.error(f"DEBUG pose_from_cluster: Error in mesh interpolation: {e}")
        import traceback
        logger.error(f"DEBUG pose_from_cluster: Traceback:\n{traceback.format_exc()}")
        continue

    elif depth_type in ("hdf5", "h5"):
      logger.info(f"DEBUG pose_from_cluster: Processing hdf5/h5 depth type")
      try:
        depth_file = h5py.File(
            Path(dataset_dir, retrieval_calibration[r].depth_name), "r"
        )
        depth_r = Image(
            Tensor.from_numpy(next(iter(depth_file.values()))[...])
        )  # first dataset as depth
        logger.info(f"DEBUG pose_from_cluster: Loaded depth from hdf5")
      except Exception as e:
        logger.error(f"DEBUG pose_from_cluster: Error loading hdf5 depth: {e}")
        import traceback
        logger.error(f"DEBUG pose_from_cluster: Traceback:\n{traceback.format_exc()}")
        continue
        
    elif depth_type == "png":
      logger.info(f"DEBUG pose_from_cluster: Processing png depth type")
      try:
        depth_r = o3d.t.io.read_image(
            str(Path(dataset_dir, retrieval_calibration[r].depth_name))
        )
        depth_r = depth_r.clip_transform(
            scale=depth_scale, min_value=0.1, max_value=depth_max, clip_fill=np.nan
        )
        logger.info(f"DEBUG pose_from_cluster: Loaded and transformed png depth")
      except Exception as e:
        logger.error(f"DEBUG pose_from_cluster: Error loading png depth: {e}")
        import traceback
        logger.error(f"DEBUG pose_from_cluster: Traceback:\n{traceback.format_exc()}")
        continue

    if depth_type in ("hdf5", "h5", "png"):
      logger.info(f"DEBUG pose_from_cluster: Calling interpolate_scan for depth type {depth_type}")
      try:
        mkp3d, valid = interpolate_scan(
            depth_r, retrieval_calibration[r].intrinsics, mkpr
        )
        logger.info(f"DEBUG pose_from_cluster: interpolate_scan returned mkp3d:{mkp3d.shape if mkp3d is not None else 'None'}, valid:{valid.shape if valid is not None else 'None'}")
        # Rw_c, tw_c:  camera -> world
        Rw_c = qvec2rotmat(retrieval_calibration[r].qvec).T
        tw_c = -Rw_c @ np.array(retrieval_calibration[r].tvec).reshape((3, 1))
        mkp3d = (Rw_c @ mkp3d.T + tw_c).T
        logger.info(f"DEBUG pose_from_cluster: Transformed mkp3d to world coords")
      except Exception as e:
        logger.error(f"DEBUG pose_from_cluster: Error in scan interpolation: {e}")
        import traceback
        logger.error(f"DEBUG pose_from_cluster: Traceback:\n{traceback.format_exc()}")
        continue

    logger.info(f"DEBUG pose_from_cluster: Appending to all_* arrays")
    try:
      logger.info(f"DEBUG pose_from_cluster: Before append - valid type:{type(valid)}, value:{valid if valid is not None else 'None'}")
      logger.info(f"DEBUG pose_from_cluster: Before append - mkpq shape:{mkpq.shape}, mkpr shape:{mkpr.shape}, mkp3d shape:{mkp3d.shape if mkp3d is not None else 'None'}")
      all_mkpq.append(mkpq[valid])
      all_mkpr.append(mkpr[valid])
      all_mkp3d.append(mkp3d[valid])
      all_indices.append(np.full(np.count_nonzero(valid), i))
      logger.info(f"DEBUG pose_from_cluster: Successfully appended arrays for retrieved image {i}")
    except Exception as e:
      logger.error(f"DEBUG pose_from_cluster: Error appending arrays: {e}")
      import traceback
      logger.error(f"DEBUG pose_from_cluster: Traceback:\n{traceback.format_exc()}")
      continue

  if num_matches <= 4:
    logger.info(f"DEBUG pose_from_cluster: Too few matches ({num_matches}), returning failure")
    return (
        {"success": False, "cfg": query_intrinsics},
        [],
        [],
        [],
        [],
        num_matches,
    )
  
  logger.info(f"DEBUG pose_from_cluster: Concatenating arrays, num_matches={num_matches}")
  all_mkpq = np.concatenate(all_mkpq, 0)
  all_mkpr = np.concatenate(all_mkpr, 0)
  all_mkp3d = np.concatenate(all_mkp3d, 0)
  all_indices = np.concatenate(all_indices, 0)
  logger.info(f"DEBUG pose_from_cluster: Arrays concatenated - mkpq: {all_mkpq.shape}, mkp3d: {all_mkp3d.shape}")
  
  # Check if arrays are empty after filtering (all matches may have been invalid)
  if len(all_mkpq) == 0 or len(all_mkp3d) == 0:
    logger.warning(f"DEBUG pose_from_cluster: Empty arrays after filtering - mkpq: {all_mkpq.shape}, mkp3d: {all_mkp3d.shape}, returning failure")
    return (
        {"success": False, "cfg": query_intrinsics},
        [],
        [],
        [],
        [],
        0,
    )

  # pycolmap >=0.5.0: absolute_pose_estimation expects pycolmap.Camera object, not dict
  logger.info(f"DEBUG pose_from_cluster: Creating camera object from query_intrinsics")
  if isinstance(query_intrinsics, dict):
    logger.info(f"DEBUG pose_from_cluster: query_intrinsics is dict with keys: {query_intrinsics.keys()}")
    camera = pycolmap.Camera(
        model=query_intrinsics['model'],
        width=query_intrinsics['width'],
        height=query_intrinsics['height'],
        params=query_intrinsics['params']
    )
  else:
    logger.info(f"DEBUG pose_from_cluster: query_intrinsics is object with attrs: {dir(query_intrinsics)}")
    # Assume it's already a Camera-like object with model, width, height, params attributes
    camera = pycolmap.Camera(
        model=query_intrinsics.model, 
        width=query_intrinsics.width, 
        height=query_intrinsics.height, 
        params=query_intrinsics.params
    )
  logger.info(f"DEBUG pose_from_cluster: Camera created: {camera}")
  
  # pycolmap 0.6.0: absolute_pose_estimation expects numpy arrays (N, 2) and (N, 3), not lists
  # Ensure arrays are contiguous and correct dtype
  logger.info(f"DEBUG pose_from_cluster: Preparing points arrays")
  points2D_array = np.ascontiguousarray(all_mkpq, dtype=np.float64)
  points3D_array = np.ascontiguousarray(all_mkp3d, dtype=np.float64)
  logger.info(f"DEBUG pose_from_cluster: points2D shape: {points2D_array.shape}, points3D shape: {points3D_array.shape}")
  
  # pycolmap >=0.5.0: max_error_px is passed via estimation_options
  logger.info(f"DEBUG pose_from_cluster: Creating estimation options")
  estimation_options = pycolmap.AbsolutePoseEstimationOptions()
  estimation_options.ransac.max_error = 48.00
  
  logger.info(f"DEBUG pose_from_cluster: Calling pycolmap.absolute_pose_estimation")
  try:
    ret = pycolmap.absolute_pose_estimation(
        points2D_array, points3D_array, camera, estimation_options=estimation_options
    )
    logger.info(f"DEBUG pose_from_cluster: absolute_pose_estimation returned type: {type(ret)}, value: {ret}")
  except Exception as e:
    logger.error(f"DEBUG pose_from_cluster: absolute_pose_estimation raised exception: {e}")
    import traceback
    logger.error(f"DEBUG pose_from_cluster: Traceback:\n{traceback.format_exc()}")
    raise
  
  logger.info(f"DEBUG pose_from_cluster: Processing pycolmap 0.5.0 return format")
  if ret is None:
    logger.error(f"DEBUG pose_from_cluster: ret is None! Cannot process")
    raise ValueError("absolute_pose_estimation returned None")
  
  # pycolmap >=0.5.0: Return format changed to include cam_from_world (Rigid3d)
  # Extract qvec and tvec from Rigid3d object and create a picklable result dict
  result = {}
  result["cfg"] = query_intrinsics
  
  if "cam_from_world" in ret and ret["cam_from_world"] is not None:
    logger.info(f"DEBUG pose_from_cluster: Extracting pose from cam_from_world")
    cam_from_world = ret["cam_from_world"]
    # Extract quaternion and translation from Rigid3d
    # Rigid3d has rotation (Rotation3d) and translation properties
    # Ensure proper conversion to 1D numpy arrays
    quat_raw = cam_from_world.rotation.quat
    trans_raw = cam_from_world.translation
    quat_xyzw = np.asarray(quat_raw).flatten()  # pycolmap 0.6.0 returns XYZW format
    logger.info(f"DEBUG pose_from_cluster: pycolmap returned quat (XYZW): {quat_xyzw}")
    
    # Convert XYZW to WXYZ format (expected by downstream code)
    result["qvec"] = qxyzw_to_qwxyz(quat_xyzw)
    result["tvec"] = np.asarray(trans_raw).flatten()  # Ensure 1D array
    result["num_inliers"] = ret.get("num_inliers", 0)
    result["success"] = result["num_inliers"] > 4
    
    # Store inliers as numpy array (if present), exclude unpicklable objects
    if "inliers" in ret:
      result["inliers"] = np.asarray(ret["inliers"])
    
    logger.info(f"DEBUG pose_from_cluster: Converted to WXYZ format - qvec: {result['qvec']}, tvec: {result['tvec']}, inliers: {result['num_inliers']}")
  else:
    logger.warning(f"DEBUG pose_from_cluster: No cam_from_world in result, localization failed")
    result["success"] = False
    result["num_inliers"] = ret.get("num_inliers", 0)
  
  logger.info(f"DEBUG pose_from_cluster: Returning from pose_from_cluster with success={result['success']}")
  return result, all_mkpq, all_mkpr, all_mkp3d, all_indices, num_matches


def read_cameras_text(path):
  """Read camera intrinsics. See format below.

  Also see colmap: src/base/reconstruction.cc
      void Reconstruction::WriteCamerasText(const std::string& path)
      void Reconstruction::ReadCamerasText(const std::string& path)

  `#camera_id model width height params`

  model is one of:

  - SIMPLE_PINHOLE: params are f, cx, cy
  - PINHOLE: params are fx, cx, cy
  - OPENCV: params are fx, fy, cx, cy, k1, k2, p1, p2

  Args:
      path: Path to cameras file.

  Returns:
      Dict mapping camera_id to Camera objects
  """
  cameras = {}
  with open(path, "r") as fid:
    line = fid.readline().strip()
    if "#camera_id model width height params" not in line:
      raise ValueError(
          "Invalid cameras file, expected format:\n"
          "#camera_id model width height params\n"
          "got format:\n" + line
      )
    line = fid.readline().strip()
    while line:
      if len(line) > 0 and line[0] != "#":
        elems = line.split()
        camera_id = elems[0]  # str instead of int
        model = elems[1].upper()
        width = int(elems[2])
        height = int(elems[3])
        params = np.array(tuple(map(float, elems[4:])))
        cameras[camera_id] = Camera(
            id=camera_id, model=model, width=width, height=height, params=params
        )
      line = fid.readline().strip()
  return cameras


def read_images_extrinsics(extrinsics_path: Path):
  """Read image extrinsics. Text file format:

  `#image_name camera_id qx qy qz qw tx ty tz`

  **Note**: Rotation and translation specify the camera extrinsic transform
  (world_to_camera)

  Args:
      extrinsics_path: Path to images file.

  Returns:
      Dict mapping image_name to namespace with attributes image_name, qvec
      (quaternion rotation), tvec (translation vector) and camera_id.
  """
  images = {}
  with open(extrinsics_path, "r") as fid:
    line = fid.readline().strip()
    if "#image_name camera_id qx qy qz qw tx ty tz" not in line:
      raise ValueError(
          "Invalid images file, expected format:\n"
          "#image_name camera_id qx qy qz qw tx ty tz\n"
          "got format:\n" + line
      )
    line = fid.readline().strip()
    while line:
      if len(line) > 0 and line[0] != "#":
        elems = line.split()
        image_name = elems[0]
        camera_id = elems[1]
        qvec = np.array(tuple(map(float, elems[2:6])))
        qvec = qxyzw_to_qwxyz(qvec)
        tvec = np.array(tuple(map(float, elems[6:9])))
        images[image_name] = SimpleNamespace(
            name=image_name, qvec=qvec, tvec=tvec, camera_id=camera_id
        )
      line = fid.readline().strip()
  return images


def read_calibration(
    dataset_dir: Path,
    rgb_ext: str = "jpg",
    depth_ext: str = ".png",
    mesh_file: str = None,
):
  """Read camera calibration information for all dataset images.

  Args:
      dataset_dir: Path containing cameras.txt (camera intrinsics) and
          images.txt (image extrinsics) text files.
      rgb_ext: RGB images file extension (e.g. 'jpg')
      depth_ext: Depth images or 3D mesh file extension (e.g. '.png' or '.ply')
      mesh_file: Use this mesh file instead of depth images.

  Returns:
      Dict mapping image_name to namespace with attributes image_name,
      depth_name, qvec (quaternion rotation), tvec (translation vector),
      camera_id and Camera (intrinsics)
  """
  cameras = read_cameras_text(dataset_dir / "cameras.txt")
  calibration = read_images_extrinsics(dataset_dir / "images.txt")
  for cal in calibration.values():
    cal.intrinsics = cameras[cal.camera_id]
    rgbn = cal.name.split("/")
    if mesh_file is None:
      cal.depth_name = "/".join(
          (
              *rgbn[:-2],
              rgbn[-2].replace("rgb", "depth"),
              rgbn[-1].replace(rgb_ext, depth_ext),
          )
      )
    else:
      cal.depth_name = mesh_file
  return calibration


def write_calibration_text(
    out_dir: Path,
    cameras: Dict = None,
    images: Dict = None,
    single_camera=False,
    model_scale: float = 1.0,
):
  """Save calibration data as "cameras.txt" and "images.txt"
  cameras.txt file format:
      `#camera_id model width height params`

  model is one of:

  - SIMPLE_PINHOLE: params are f, cx, cy
  - PINHOLE: params are fx, cx, cy
  - OPENCV: params are fx, fy, cx, cy, k1, k2, p1, p2

  images.txt file format:
      `#image_name camera_id qx qy qz qw tx ty tz`

  Args:
      out_dir: Output directory
      cameras: camera intrinsic parameters. Skip writing if None.
      images: camera extrinsic parametsers. Skip writing if None.
      single_camera: Only use the first camera
      model_scale: Optional value to scale up the model (translation)
  """
  if cameras is not None:
    with open(out_dir / "cameras.txt", "w", encoding="utf-8") as camfile:
      camfile.write("#camera_id model width height params\n")
      for camera in cameras.values():
        params = " ".join(map(str, camera.params))
        camfile.write(
            f"{camera.id} {camera.model} {camera.width} "
            f"{camera.height} {params}\n"
        )
        if single_camera:
          camera_id = camera.id
          break

  if images is not None:
    with open(out_dir / "images.txt", "w", encoding="utf-8") as imfile:
      imfile.write("#image_name camera_id qx qy qz qw tx ty tz\n")
      for image in images.values():
        qvec = " ".join(map(str, qwxyz_to_qxyzw(image.qvec)))
        tvec = " ".join(map(str, model_scale * np.array(image.tvec)))
        camid = camera_id if single_camera else image.camera_id
        imfile.write(" ".join((image.name, str(camid), qvec, tvec)) + "\n")


def main(
    dataset_dir,
    db_feature_paths,
    retrieval,
    query_intrinsics: Dict,
    features: Sequence[Path],
    matches: Sequence[Path],
    results_path,
    skip_matches,
    match_dense,
    data_config,
):

  assert retrieval.exists(), retrieval
  assert all(f.exists() for f in features), features
  assert all(m.exists() for m in matches), matches
  result = SimpleNamespace()

  retrieval_dict = parse_retrieval(retrieval)
  query = next(iter(retrieval_dict.keys()))
  retrieval_calibration = read_calibration(
      dataset_dir, data_config.rgb_ext, data_config.depth_ext, data_config.mesh_file
  )
  have_gt = False

  if (
      "gt_query_cameras" in data_config
      and data_config.gt_query_cameras is not None
      and "gt_query_images" in data_config
      and data_config.gt_query_images is not None
  ):
    query_cameras = read_cameras_text(data_config.gt_query_cameras)
    query_poses = read_images_extrinsics(data_config.gt_query_images)
    have_gt = True
    min_retrieval_dset, min_retrieval_dist = find_nearest_pose(
        query_poses, retrieval_calibration
    )

  feature_files = tuple(h5py.File(f, "r") for f in features)
  match_files = tuple(h5py.File(m, "r") for m in matches)

  def open_or_skip_h5(filepath, mode="r"):
    try:
      return h5py.File(filepath, mode)
    except OSError:
      return None

  db_feature_files = tuple(open_or_skip_h5(f, "r") for f in db_feature_paths)

  logs = {"features": features, "matches": matches, "retrieval": retrieval, "loc": {}}
  logger.info("Starting localization...")
  retrieved = retrieval_dict[query]
  logger.info(f"DEBUG: Retrieved images: {retrieved}")
  logger.info(f"DEBUG: Query intrinsics type: {type(query_intrinsics)}, value: {query_intrinsics}")
  
  ret, mkpq, mkpr, mkp3d, indices, num_matches = pose_from_cluster(
      dataset_dir,
      db_feature_files,
      query,
      retrieved,
      feature_files,
      match_files,
      retrieval_calibration,
      query_intrinsics,
      skip_matches,
      match_dense,
      data_config.depth_scale,
      data_config.depth_max,
  )

  logger.info(f"DEBUG: pose_from_cluster returned - ret type: {type(ret)}, ret value: {ret}")
  logger.info(f"DEBUG: num_matches: {num_matches}, mkpq shape: {np.array(mkpq).shape if len(mkpq) > 0 else 'empty'}")
  
  if ret is None:
    logger.error("DEBUG: ret is None! pose_from_cluster returned None")
    raise ValueError("pose_from_cluster returned None")
  
  if not isinstance(ret, dict):
    logger.error(f"DEBUG: ret is not a dict! Type: {type(ret)}")
    raise ValueError(f"Expected ret to be dict, got {type(ret)}")

  result.success = ret["success"]
  result.num_matches = num_matches
  result.n_keypoints = len(mkpq)
  logger.info(f"DEBUG: result.success: {result.success}, result.num_matches: {result.num_matches}")
  
  if ret["success"]:
    logger.info(f"DEBUG: Localization successful, extracting qvec and tvec")
    result.qvec = ret["qvec"]
    result.tvec = ret["tvec"]
    result.n_inliers = ret["num_inliers"]
    logger.info(f"DEBUG: qvec: {result.qvec}, tvec: {result.tvec}, inliers: {result.n_inliers}")
  else:
    logger.info(f"DEBUG: Localization failed, using first retrieved image pose")
    result.qvec = retrieval_calibration[retrieved[0]].qvec
    result.tvec = retrieval_calibration[retrieved[0]].tvec
    result.n_inliers = -1
    logger.info(f"DEBUG: Fallback qvec: {result.qvec}, tvec: {result.tvec}")

  logger.info(f"DEBUG main: Creating logs dict with query: {query}")
  logger.info(f"DEBUG main: result.qvec type: {type(result.qvec)}, shape: {result.qvec.shape if hasattr(result.qvec, 'shape') else 'N/A'}")
  logger.info(f"DEBUG main: result.tvec type: {type(result.tvec)}, shape: {result.tvec.shape if hasattr(result.tvec, 'shape') else 'N/A'}")
  logger.info(f"DEBUG main: result.qvec: {result.qvec}")
  logger.info(f"DEBUG main: result.tvec: {result.tvec}")
  logger.info(f"DEBUG main: result.n_inliers: {result.n_inliers}")
  logger.info(f"DEBUG main: result.success: {result.success}")
  
  logs["loc"] = {
      query: {
          "db": retrieved,
          "PnP_ret": ret,
          "keypoints_query": mkpq,
          "keypoints_db": mkpr,
          "3d_points": mkp3d,
          "indices_db": indices,
          "num_matches": num_matches,
      }
  }
  logger.info(f"DEBUG main: Created logs['loc'] for query: {query}")
  
  if have_gt:
    logger.info(f"DEBUG main: Evaluating with ground truth - qvec: {result.qvec}, tvec: {result.tvec}")
    logger.info("Evaluating...")
    evaluate(
        {query: (result.qvec, result.tvec)},
        {query: (query_poses[query].qvec, query_poses[query].tvec)},
        error_basis={query: min_retrieval_dist[query]},
        logs=logs,
    )

  logger.info(f"DEBUG main: Writing results to file: {results_path}")
  logger.info(f"DEBUG main: result.qvec before formatting: {result.qvec}")
  logger.info(f"DEBUG main: result.tvec before formatting: {result.tvec}")
  
  with open(results_path, "a") as fres:
    fres.write(
        "#query_image qw qx qy qz tx ty tz e_t(cm) e_t_rel(%) e_R(deg)"
        " success n_keypoints n_matches n_inliers\n"
    )
    qvec = " ".join(map(str, result.qvec))
    tvec = " ".join(map(str, result.tvec))
    logger.info(f"DEBUG main: Formatted qvec string: {qvec}")
    logger.info(f"DEBUG main: Formatted tvec string: {tvec}")
    if have_gt:
      e_t = logs["loc"][query]["e_t"]
      e_t_rel = logs["loc"][query]["e_t_rel"]
      e_R = logs["loc"][query]["e_R"]
      eval_str = f" {e_t*100:.2f} {e_t_rel*100:.2f} {e_R:.2f} "
      logger.info(f"DEBUG main: Ground truth eval - e_t: {e_t*100:.2f}cm, e_t_rel: {e_t_rel*100:.2f}%, e_R: {e_R:.2f}deg")
    else:
      eval_str = " -1 -1 -1 "
      logger.info(f"DEBUG main: No ground truth available, using eval_str: {eval_str}")
    result_line = f"{query} {qvec} {tvec} {eval_str} {result.success} {result.n_keypoints} {result.num_matches} {result.n_inliers}\n"
    logger.info(f"DEBUG main: Writing result line to file: {result_line.strip()}")
    fres.write(result_line)
    print(
        f"{query} {eval_str} {result.success} {result.n_keypoints} "
        f"{result.num_matches} {result.n_inliers}\n"
    )
  logs_path = f"{results_path}_logs.pkl"
  logger.info(f"DEBUG main: Saving logs to pickle file: {logs_path}")
  with open(logs_path, "wb") as flog:
    pickle.dump(logs, flog)

  if "gt_mesh_file" in data_config and data_config.gt_mesh_file is not None:
    logger.info(f"DEBUG main: Rendering with mesh file: {data_config.gt_mesh_file}")
    logger.info(f"DEBUG main: Building extrinsic matrix from qvec: {result.qvec}, tvec: {result.tvec}")
    intrinsic_matrix = get_intrinsic_mat(query_intrinsics).numpy()
    extrinsic_matrix = pose_matrix_from_qvec_tvec(result.qvec, result.tvec)
    logger.info(f"DEBUG main: Extrinsic matrix shape: {extrinsic_matrix.shape}")
    render = o3d.visualization.rendering.OffscreenRenderer(
        query_intrinsics.width, query_intrinsics.height
    )
    if data_config.gt_mesh_file[:-4] in (".ply", ".pcd"):
      model = o3d.io.read_point_cloud(str(data_config.gt_mesh_file))
      mat = o3d.visualization.rendering.MaterialRecord()
      render.scene.add_geometry("model", model, mat)
    else:  # '.glb', '.gltf', '.obj'
      model = o3d.io.read_triangle_model(str(data_config.gt_mesh_file))
      render.scene.add_model("model", model)
    render.setup_camera(
        intrinsic_matrix,
        extrinsic_matrix,
        query_intrinsics.width,
        query_intrinsics.height,
    )
    im = render.render_to_image()
    render_path = results_path.parent / f"render-{query}"
    logger.info(f"DEBUG main: Saving render to: {render_path}")
    o3d.io.write_image(str(render_path), im)

  logger.info(f"DEBUG main: BEFORE qwxyz_to_qxyzw - qvec: {result.qvec}")
  result.qvec = qwxyz_to_qxyzw(result.qvec)
  logger.info(f"DEBUG main: AFTER qwxyz_to_qxyzw - qvec: {result.qvec}")
  
  # camera extrinsic (world_to_camera) -> camera location (camera_to_world)
  logger.info(f"DEBUG main: BEFORE qxyzwtinv - qvec: {result.qvec}, tvec: {result.tvec}")
  result.qvec, result.tvec = qxyzwtinv(result.qvec, result.tvec)
  logger.info(f"DEBUG main: AFTER qxyzwtinv (final output) - qvec: {result.qvec}, tvec: {result.tvec}")
  
  return result
