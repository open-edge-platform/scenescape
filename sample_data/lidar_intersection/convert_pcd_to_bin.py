# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Convert DAIR-V2X-Seq (V2X-Seq-SPD) binary_compressed PCD files to raw
float32 BIN files.

Each output .bin file contains N×4 float32 values (x, y, z, intensity)
packed contiguously - the format expected by DLStreamer g3dlidarparse. Used
by the `lidar-data-init` service (see
../../docs/user-guide/how-to-guides/run-lidar-intersection-demo.md) to
convert the manually-downloaded raw dataset's `velodyne/*.pcd` files into
the `velodyne_bin/*.bin` files `lidar_publisher.py` reads directly.

Converts every `*.pcd` file found in `PCD_VELODYNE_DIR` (frame id = file
name without extension) - no dependency on the dataset's `data_info.json`,
so only the `velodyne/` subdirectory needs to be available, not the full
`infrastructure-side/` tree (`lidar-data-init` mounts `velodyne/` and
`image/` directly for exactly this reason).

`PCD_VELODYNE_DIR`/`PCD_BIN_DIR` env vars override the input/output
directories; unset, this behaves like the original standalone script
(reading/writing next to a co-located `infrastructure-side/` directory).
"""

import glob
import os

from pypcd4 import PointCloud


DATA_ROOT = os.environ.get(
  "PCD_DATA_ROOT", os.path.join(os.path.dirname(__file__), "infrastructure-side")
)
VELODYNE_DIR = os.environ.get("PCD_VELODYNE_DIR", os.path.join(DATA_ROOT, "velodyne"))
BIN_DIR = os.environ.get("PCD_BIN_DIR", os.path.join(DATA_ROOT, "velodyne_bin"))


def convert_frame(pcd_path: str, bin_path: str) -> None:
  pc = PointCloud.from_path(pcd_path)
  points = pc.numpy(("x", "y", "z", "intensity"))  # shape (N, 4), float32
  points.tofile(bin_path)


def main() -> None:
  pcd_paths = sorted(glob.glob(os.path.join(VELODYNE_DIR, "*.pcd")))

  os.makedirs(BIN_DIR, exist_ok=True)
  total = len(pcd_paths)
  print(f"Converting {total} frames from {VELODYNE_DIR} -> {BIN_DIR}")

  for i, pcd_path in enumerate(pcd_paths):
    frame_id = os.path.splitext(os.path.basename(pcd_path))[0]
    bin_path = os.path.join(BIN_DIR, f"{frame_id}.bin")
    convert_frame(pcd_path, bin_path)
    if (i + 1) % 50 == 0 or (i + 1) == total:
      print(f"  {i + 1}/{total} done")

  print("Conversion complete.")


if __name__ == "__main__":
  main()
