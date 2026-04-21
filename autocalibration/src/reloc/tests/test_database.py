#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Test database operations."""

import sys
import tempfile
from pathlib import Path
from test_utils import setup_hloc_path, print_test_header, print_test_result


def test_database_operations():
  """Test COLMAP database creation and operations."""
  print_test_header("Database Operations")

  try:
    from hloc.utils.database import COLMAPDatabase
    import numpy as np

    with tempfile.TemporaryDirectory() as tmpdir:
      db_path = Path(tmpdir) / "test.db"

      print("  Creating database...")
      db = COLMAPDatabase.connect(db_path)

      # Create database schema
      db.create_tables()

      # Add camera
      print("  Adding camera...")
      camera_id = db.add_camera(
        model=1,  # SIMPLE_PINHOLE
        width=640,
        height=480,
        params=np.array([500.0, 320.0, 240.0])
      )

      # Add image
      print("  Adding image...")
      image_id = db.add_image(
        name="test.jpg",
        camera_id=camera_id
      )

      # Add keypoints
      print("  Adding keypoints...")
      keypoints = np.random.rand(100, 2).astype(np.float32) * [640, 480]
      db.add_keypoints(image_id, keypoints)

      db.commit()

      # Verify
      cameras = db.execute("SELECT * FROM cameras").fetchall()
      images = db.execute("SELECT * FROM images").fetchall()

      if len(cameras) != 1 or len(images) != 1:
        print_test_result(False, f"{len(cameras)} cameras, {len(images)} images")
        return False

      print(f"  ✓ Database operations successful")
      print(f"  ✓ {len(cameras)} camera, {len(images)} image")

      db.close()

    print_test_result(True)
    return True

  except Exception as e:
    print(f"  ❌ Error: {e}")
    import traceback
    traceback.print_exc()
    print_test_result(False, str(e))
    return False


def main():
  """Run database tests."""
  try:
    setup_hloc_path()
  except RuntimeError as e:
    print(f"❌ {e}")
    return 1

  passed = test_database_operations()
  return 0 if passed else 1


if __name__ == '__main__':
  sys.exit(main())
