# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import subprocess
from pathlib import Path
import pytest

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_IMAGE = "intel/scenescape-sources:latest"

MIN_DEB_SOURCE_PACKAGES = 100
MIN_DEB_ARCHIVES = 200

EXPECTED_DEB_PACKAGES = ["curl", "openssl", "glibc", "git", "ffmpeg", "perl", "protobuf", "mosquitto"]
EXPECTED_REPOS = {
  "python": ["paho.mqtt.python", "orjson", "psycopg2", "tqdm"],
  "conan": ["paho.mqtt.c", "paho.mqtt.cpp", "gcc", "m4"],
  "other": ["busybox", "geckodriver"],
}
ARCHIVE_SUFFIXES = (".tar.gz", ".tar.xz", ".tar.bz2", ".tgz", ".tar.zst")

def run(cmd, **kwargs):
  logger.info(f"Running command: {' '.join(cmd)}")
  return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, **kwargs)

def list_in_image(path):
  result = run(["docker", "run", "--rm", "--entrypoint", "ls", SOURCES_IMAGE, "-1", path])
  assert result.returncode == 0, f"Listing {path} in {SOURCES_IMAGE} failed: {result.stderr}"
  return result.stdout.split()

@pytest.fixture(scope="module")
def sources_image():
  build = run(["make", "build-sources-image"])
  logger.debug(build.stdout)
  assert build.returncode == 0, f"make build-sources-image failed:\n{build.stderr[-2000:]}"
  yield SOURCES_IMAGE

@pytest.mark.test_name("NEX-T10581")
def test_sources_image_contains_dependency_sources(sources_image, result_recorder):
  """Sources image builds and exposes non-empty, expected dependency source archives."""
  top_level = list_in_image("/sources")
  assert top_level, "/sources is empty in the sources image"
  for entry in ("deb", "python", "conan", "other", "third-party-programs.txt"):
    assert entry in top_level, f"/sources/{entry} missing; found {top_level}"

  deb_files = list_in_image("/sources/deb")
  archives = [f for f in deb_files if f.endswith(ARCHIVE_SUFFIXES)]
  dsc_files = [f for f in deb_files if f.endswith(".dsc")]
  assert len(dsc_files) >= MIN_DEB_SOURCE_PACKAGES, (
    f"Expected at least {MIN_DEB_SOURCE_PACKAGES} .dsc files, found {len(dsc_files)}"
  )
  assert len(archives) >= MIN_DEB_ARCHIVES, (
    f"Expected at least {MIN_DEB_ARCHIVES} source archives, found {len(archives)}"
  )

  missing = [p for p in EXPECTED_DEB_PACKAGES if not any(f.startswith(f"{p}_") for f in deb_files)]
  assert not missing, f"Debian source packages missing from /sources/deb: {missing}"

  for subdir, repos in EXPECTED_REPOS.items():
    present = list_in_image(f"/sources/{subdir}")
    missing = [r for r in repos if r not in present]
    assert not missing, f"Repositories missing from /sources/{subdir}: {missing}"

  # Negative: a package that is not a dependency must not be shipped.
  assert not any(f.startswith("nonexistent-package_") for f in deb_files)
  missing_dir = run(["docker", "run", "--rm", "--entrypoint", "ls", SOURCES_IMAGE, "/sources/nonexistent"])
  assert missing_dir.returncode != 0, "Listing a nonexistent directory unexpectedly succeeded"

  result_recorder.success()
