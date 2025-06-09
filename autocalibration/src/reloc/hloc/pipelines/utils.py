"""Example:
python -m hloc.pipelines.utils --dataset_dir datasets/inloc/
"""
import argparse
import csv
from pathlib import Path
from scipy.spatial.transform import Rotation as R
from ..localize_inloc import get_scan_pose


def get_database_pose(dataset_dir, rpath):
  """Get pose for image rpath in dataset_dir using alignment txt files and
  image azimuth and elevation.

  Returns:
      q_wxyz, tvec
  """
  rpath = str(rpath)
  Tr = get_scan_pose(dataset_dir, rpath)
  parts = rpath.split("_")
  az = float(parts[-2])
  el = float(parts[-1].split(".")[0])
  # camera pose: camera -> world
  cam_pose = R.from_euler("zy", ((az, el),), degrees=True).inv()
  quat = (R.from_matrix(Tr[:3, :3]) * cam_pose).as_quat()
  quat[0], quat[3] = quat[3], quat[0]  # xyzw -> wxyz
  return quat, Tr[:3, -1:]


if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument("--dataset_dir", type=Path, required=True)
  args = parser.parse_args()
  with open(args.dataset_dir / "dataset_poses.csv", "w", newline="") as dpfile:
    dpfile.write("#filename qw qx qy qz tx ty tz\n")
    csv_dp = csv.writer(dpfile, delimiter=" ", lineterminator="\n")
    for rpath in sorted(args.dataset_dir.glob("database/cutouts/*/*/*.jpg")):
      quat, trans = get_database_pose(args.dataset_dir, rpath)
      csv_dp.writerow([rpath] + quat.ravel().tolist() + trans.ravel().tolist())
