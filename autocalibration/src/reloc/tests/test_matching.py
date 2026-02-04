#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Test feature matching functionality."""

import sys
import tempfile
from pathlib import Path
from test_utils import setup_hloc_path, print_test_header, print_test_result


def create_test_image(output_path: Path, width: int = 640, height: int = 480):
  """Create synthetic test image."""
  try:
    import numpy as np
    from PIL import Image, ImageDraw

    img = np.zeros((height, width, 3), dtype=np.uint8)
    square_size = 40
    for i in range(0, height, square_size):
      for j in range(0, width, square_size):
        if (i // square_size + j // square_size) % 2 == 0:
          img[i:i+square_size, j:j+square_size] = [200, 200, 200]

    pil_img = Image.fromarray(img)
    draw = ImageDraw.Draw(pil_img)
    draw.ellipse([100, 100, 180, 180], fill=(255, 100, 100))
    draw.rectangle([400, 200, 500, 300], fill=(100, 255, 100))

    pil_img.save(output_path)
    return True
  except ImportError:
    return False


def test_feature_matching():
  """Test feature matching between images - SKIPPED (SuperGlue not used in SceneScape)."""
  print_test_header("Feature Matching (SuperGlue) - SKIPPED")
  print("  ⚠️  SuperGlue not used in SceneScape, test skipped")
  print_test_result(True, "Skipped - not used in SceneScape")
  return True


def main():
  """Run matching tests."""
  try:
    setup_hloc_path()
  except RuntimeError as e:
    print(f"❌ {e}")
    return 1

  passed = test_feature_matching()
  return 0 if passed else 1


if __name__ == '__main__':
  sys.exit(main())
