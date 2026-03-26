#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Compose file image rewriting.

Replicates the sed transformation from tests/runtest:42-44 that rewrites
``image: scenescape*`` lines to use the appropriate test image.
"""

import re
from pathlib import Path


def rewrite_compose_images(source_path, test_image, tmpdir):
  """Rewrite scenescape image references in a compose file.

  Args:
    source_path: Path to the original compose YAML file.
    test_image: Full test image name (e.g. "scenescape-manager-test:2026.0.0").
    tmpdir: Directory for the rewritten temporary file.

  Returns:
    Path to the rewritten compose file.
  """
  content = Path(source_path).read_text()

  # The compose files have lines like:
  #   image: scenescape-controller:${VERSION:-latest}
  #   image: scenescape-manager:${VERSION:-latest}
  # Replace the image name portion, preserving any ${VERSION} tag.
  content = re.sub(
    r'^(\s*image:\s+)scenescape[^\s]*',
    rf'\g<1>{test_image}',
    content,
    flags=re.MULTILINE,
  )

  out_path = tmpdir / Path(source_path).name
  # Handle duplicate filenames from different subdirectories (e.g. dlstreamer/broker.yml)
  if out_path.exists():
    stem = Path(source_path).parent.name
    out_path = tmpdir / f"{stem}-{Path(source_path).name}"

  out_path.write_text(content)
  return out_path
