# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

"""Estimate the camera poses for a dataset using Structure from Motion pipeline
from hloc / COLMAP. This also estimates SfM scale using depth images. The SfM
reconstruction can be visualized for validity using:
    - Rendered images of the sparse point cloud with estimated image poses from
      the datset.
    - Interactive 3D viewer showing the sparse point cloud and the estimated
      image poses from the dataset.

Structure form Motion can take a long time to run (hours). It is recommended to
run on a Xeon machine or with an Nvidia GPU.
"""
from argparse import ArgumentParser
from pathlib import Path
import json
from typing import Optional
import numpy as np
from addict import Dict
from sklearn import linear_model
import open3d as o3d
from open3d.geometry import LineSet
from open3d.visualization.rendering import OffscreenRenderer, MaterialRecord

import pycolmap
from hloc import (
    extract_features,
    match_features,
    match_dense,
    reconstruction,
    pairs_from_retrieval,
)
from hloc.utils import read_write_model as hloc_io
from localize_scenescape import (
    write_calibration_text,
    read_cameras_text,
    read_images_extrinsics,
    get_intrinsic_mat,
    pose_matrix_from_qvec_tvec,
)


def get_colmap_scale(
    images,
    points3D,
    dataset_dir: Path,
    depth_scale: float = 1000.0,
    MAX_IM_PTS=400,
    MAX_IM=400,
):
  """Estimate the scale of the COLMAP model by comparing the depth map and the
      3D SfM points.

  Args:
      images (dict): COLMAP images data structure
      points3D (dict): COLMAP points3D data structure
      dataset_dir (Path): Path to the dataset directory
      depth_scale (float, optional): Scale to convert depth values to meters.
          Defaults to 1000.0 (i.e. depth values are in mm).
      MAX_IM_PTS (int, optional): Maximum number of points per image. Defaults to 400.
      MAX_IM (int, optional): Maximum number of images. Defaults to 400.
  """
  depth_pts, depth_colmap = [], []
  print("Estimating COLMAP model scale...")
  sub_im = int((len(images) - 1) / MAX_IM + 1)
  for image in list(images.values())[::sub_im]:
    print("\r", image.name, end="")
    depth_name = image.name.replace(".jpg", ".png")
    depth = o3d.t.io.read_image(str(dataset_dir / "depth" / depth_name))
    depth = np.squeeze(depth.as_tensor().numpy())
    # TODO: Smooth depth image and use interpolation to get depth at subpixel locations
    # (Nr.5, Nc.5) is pixel center
    imxy = np.floor(image.xys.T).astype(int)
    # [::-1] for (x,y) -> (y,x) = (r,c)
    valid = (imxy[0, :] < depth.shape[1]) & (imxy[1, :] < depth.shape[0])
    im_depth_pts = np.zeros(len(image.xys))
    im_depth_pts[valid] = depth[tuple(imxy[:, valid])[::-1]]
    valid &= (im_depth_pts > 0) & (image.point3D_ids > 0)
    sub_pt = int((np.count_nonzero(valid) - 1) / MAX_IM_PTS + 1)
    if sub_pt == 0:
      continue
    depth_pts.append(im_depth_pts[valid][::sub_pt])
    Rmat = hloc_io.qvec2rotmat(image.qvec)
    im_pts3D = np.fromiter(
        (
            tuple(points3D[pt3_id].xyz)
            for pt3_id in image.point3D_ids[valid][::sub_pt]
        ),
        dtype=np.dtype((float, 3)),
    ).T
    im_pts3D = Rmat @ im_pts3D + image.tvec.reshape(-1, 1)
    depth_colmap.append(im_pts3D[2])  # Get Z

  depth_pts = np.concatenate(depth_pts).reshape(-1, 1) / depth_scale
  depth_colmap = np.concatenate(depth_colmap).reshape(-1, 1)

  estimator = linear_model.LinearRegression(fit_intercept=False)
  ransac = linear_model.RANSACRegressor(
      estimator,
      residual_threshold=0.05,
      max_trials=int(1e7),
      stop_probability=1.0 - 1e-6,
  )
  ransac.fit(depth_pts, depth_colmap)
  inlier_ratio = np.count_nonzero(ransac.inlier_mask_) / len(depth_pts)
  colmap_scale = ransac.estimator_.coef_.item()

  print(
      f"\ncolmap_scale = {colmap_scale:.03f}, Inlier ratio = "
      f"{inlier_ratio:.03f} with threshold 0.05m"
  )
  if inlier_ratio < 0.5:
    print(
        "[WARNING] Estimated scale is approximate. Too few inliers",
        f"({inlier_ratio*100}%)",
    )
  return colmap_scale


def import_from_colmap(dataset_dir: Path, sfm_dir: Path, out_dir: Path):
  """Read a COLMAP SfM reconstruction from a folder (i.e. the folder should
  have images.bin, cameras.bin and points3D.bin files). Estimate scale for the
  reconstruction using depth images and save images.txt and cameras.txt files
  in reloc format.

  Args:
      dataset_dir (Path): Path to dataset directory, with rgb and depth subfolders
      sfm_dir (Path): Path to reconstruction directory
      out_dir (Path): Path to output directory
  """
  cameras, images, points3D = hloc_io.read_model(sfm_dir)
  colmap_scale = get_colmap_scale(images, points3D, dataset_dir)
  write_calibration_text(out_dir, cameras, images, model_scale=colmap_scale)
  pt3d = o3d.t.io.read_point_cloud(str(sfm_dir / "sparse-points.ply"))
  pt3d = pt3d.scale(colmap_scale, center=[0.0, 0.0, 0.0])
  o3d.t.io.write_point_cloud(str(sfm_dir / "sparse-points.ply"), pt3d)


def visualize_sfm(
    images_file: Path,
    cameras_file: Path,
    sfm_points_file: Path,
    save_renders=True,
    show_cameras=False,
    MAX_IM=100,
):
  """Visualize SfM reconstruction.

  Args:
      images_file (Path): Path to images.txt file
      cameras_file (Path): Path to cameras.txt file
      sfm_points_file (Path): Path to the SfM sparse-points.ply file.
      save_renders (bool, optional): Save renders from the estimated camera
          poses to disk. These can be compared with the input dataset images.
          Defaults to True.
      show_cameras (bool, optional): Show camera location in the SfM sparse
          point cloud in an interactive 3D viewer. Defaults to False.
      MAX_IM (int, optional): Maximum number of cameras to show. Defaults to 100.
  """

  camera_color = [1.0, 0.0, 0.0]
  camera = next(iter(read_cameras_text(cameras_file).values()))
  images = read_images_extrinsics(images_file)

  camK = get_intrinsic_mat(camera).numpy()
  cam_vis = []
  sub_im = int((len(images) - 1) / MAX_IM + 1)
  sub_images = list(images.values())[::sub_im]
  for image in sub_images:
    pose = pose_matrix_from_qvec_tvec(image.qvec, image.tvec)
    cam_vis.append(
        LineSet.create_camera_visualization(
            camera.width, camera.height, camK, pose, scale=1.0
        )
    )
    cam_vis[-1].paint_uniform_color(camera_color)

  pcd = o3d.io.read_point_cloud(str(sfm_points_file))
  cam_vis.append(pcd)

  if save_renders:
    dataset_dir = images_file.with_name("rgb")
    sfm_points_file.with_name("renders").mkdir(exist_ok=True)
    render = OffscreenRenderer(camera.width, camera.height)
    point_mat = MaterialRecord()
    point_mat.shader = "defaultUnlit"
    point_mat.point_size = 5
    render.scene.add_geometry("sfm points", pcd, point_mat)
    for image in sub_images:
      dset_im = o3d.io.read_image(str(dataset_dir / image.name))
      dset_imbuf = np.asarray(dset_im)
      dset_imbuf[:] = 170 + dset_imbuf[:] / 3
      render.scene.set_background(color=[1.0, 1.0, 1.0, 0.0], image=dset_im)
      pose = pose_matrix_from_qvec_tvec(image.qvec, image.tvec)
      render.setup_camera(camK, pose, camera.width, camera.height)
      im = render.render_to_image()
      o3d.io.write_image(
          str(sfm_points_file.parent / "renders" / f"render-{image.name}"), im
      )
    print(
        f"Saved {len(sub_images)} renders from estimated poses to "
        f"{sfm_points_file.parent / 'renders'}."
    )

  if show_cameras:
    o3d.visualization.draw(cam_vis, show_ui=True, show_skybox=False, point_size=5)


def pipeline_sfm(
    config: Dict,
    dataset_dir: str,
    output_dir: Optional[str] = None,
    camera: Optional[hloc_io.Camera] = None,
):
  """Localize an RGBD image dataset with Structure from Motion.

  Args:
      config (Dict): System configuration from json file
      dataset_dir (str): Path to dataset directory
      output_dir (str): Path to output directory
      camera (hloc.utils.read_write_model.Camera, optional): Camera. Defaults to None.
  """

  image_dir = Path(dataset_dir) / "rgb"
  output_dir = Path(output_dir) if output_dir is not None else Path(dataset_dir)
  sfm_pairs = output_dir / "pairs-netvlad.txt"

  retrieval_conf = extract_features.confs[config.hloc.global_feature]
  if len(config.hloc.local_feature) > 1 or len(config.hloc.matcher) > 1:
    raise ValueError("Only one local feature / matcher is supported.")
  local_feature = next(iter(config.hloc.local_feature))
  matcher = next(iter(config.hloc.matcher))

  retrieval_path = extract_features.main(retrieval_conf, image_dir, output_dir)
  pairs_from_retrieval.main(
      retrieval_path, sfm_pairs, num_matched=config.hloc.num_loc
  )

  if local_feature == "-":  # semi-dense / direct matching
    matcher_conf = match_dense.confs[matcher] | config.matcher[matcher]

    feature_path, match_path = match_dense.main(
        conf=matcher_conf,
        pairs=sfm_pairs,
        image_dir=image_dir,
        export_dir=output_dir,
        reassign=False,
    )
  else:
    feature_conf = (
        extract_features.confs[local_feature]
        | config.hloc.local_feature[local_feature]
    )
    feature_path = output_dir / f"features-{local_feature}.h5"
    extract_features.main(
        feature_conf, image_dir, output_dir, feature_path=feature_path
    )
    matcher_conf = match_features.confs[matcher] | config.hloc.matcher[matcher]
    match_path = output_dir / f"matches-{local_feature}-{matcher}.h5"
    match_features.main(
        matcher_conf, sfm_pairs, feature_path, output_dir, match_path
    )

  if camera is None:
    image_options = None
    mapper_options = None
  else:  # Fix camera intrinsics
    image_options = {
        "camera_model": camera.model,
        "camera_params": ",".join(map(str, camera.params)),
    }
    mapper_options = {
        "ba_refine_extra_params": False,
        "ba_refine_focal_length": False,
        "ba_refine_principal_point": False,
    }
  model = reconstruction.main(
      output_dir,
      image_dir,
      sfm_pairs,
      feature_path,
      match_path,
      camera_mode=pycolmap.CameraMode.SINGLE,
      image_options=image_options,
      mapper_options=mapper_options,
  )
  model.export_PLY(str(output_dir / "sparse-points.ply"))
  print(f"Saved SfM sparse point cloud to {output_dir / 'sparse-points.ply'}")


def main():
  parser = ArgumentParser(description=__doc__)
  parser.add_argument(
      "config", type=Path, help="Path to the configuration file (json format)."
  )
  parser.add_argument("dataset_dir", type=Path, help="Path to the dataset directory.")
  parser.add_argument(
      "--output_dir",
      type=Path,
      default=None,
      help="Path to the output directory. If not specified, the output will be "
      "saved in the dataset directory.",
  )
  parser.add_argument(
      "--cameras",
      type=Path,
      help="Path to the cameras file with a single camera entry. A SIMPLE_RADIAL "
      "camera is estimated if this is not specified.",
  )
  parser.add_argument(
      "--show_cameras",
      action="store_true",
      help="Show estimated camera poses in 3D viewer",
  )
  args = parser.parse_args()
  if args.output_dir is None:
    args.output_dir = args.dataset_dir

  with open(args.config, "r") as cfg:
    config = Dict(json.load(cfg))

  if args.cameras != Path():
    cameras = read_cameras_text(args.cameras)
    assert len(cameras) == 1
    camera = next(iter(cameras.values()))
  else:
    camera = None
  pipeline_sfm(config, args.dataset_dir, args.output_dir / "sfm", camera=camera)
  import_from_colmap(args.dataset_dir, args.output_dir / "sfm", args.output_dir)
  visualize_sfm(
      args.output_dir / "images.txt",
      args.output_dir / "cameras.txt",
      args.output_dir / "sfm" / "sparse-points.ply",
      show_cameras=args.show_cameras,
  )


if __name__ == "__main__":
  main()
