# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Re-encode the DAIR-V2X-Seq (V2X-Seq-SPD) camera `.jpg` frames at a lower
JPEG quality so `jpegdec`/`gvadetect` in the camera branch (and the
`lidar_publisher.py` "getimage" preview, which republishes the frame off
disk as-is) have less data to read/decode per frame.

Only re-compresses (same pixel dimensions) - never resizes - since
`bounding_box_px` coordinates and the scene's camera calibration are tied to
the original image resolution.

Used by the `lidar-data-init` service (see
../../docs/user-guide/how-to-guides/run-lidar-intersection-demo.md).
`JPEG_SRC_DIR`/`JPEG_DST_DIR`/`JPEG_QUALITY` env vars override the
input/output directories and target quality (1-95, Pillow's `keep` maximum).
"""

import glob
import os

from PIL import Image

SRC_DIR = os.environ.get("JPEG_SRC_DIR", "/src/image")
DST_DIR = os.environ.get("JPEG_DST_DIR", "/dst/lidar_intersection/images")
QUALITY = int(os.environ.get("JPEG_QUALITY", "50"))


def reencode_frame(src_path: str, dst_path: str) -> None:
  with Image.open(src_path) as im:
    im.convert("RGB").save(dst_path, format="JPEG", quality=QUALITY, optimize=True)


def main() -> None:
  jpg_paths = sorted(glob.glob(os.path.join(SRC_DIR, "*.jpg")))

  os.makedirs(DST_DIR, exist_ok=True)
  total = len(jpg_paths)
  print(f"Re-encoding {total} frames from {SRC_DIR} -> {DST_DIR} at quality={QUALITY}")

  for i, src_path in enumerate(jpg_paths):
    dst_path = os.path.join(DST_DIR, os.path.basename(src_path))
    reencode_frame(src_path, dst_path)
    if (i + 1) % 50 == 0 or (i + 1) == total:
      print(f"  {i + 1}/{total} done")

  print("Re-encoding complete.")


if __name__ == "__main__":
  main()
