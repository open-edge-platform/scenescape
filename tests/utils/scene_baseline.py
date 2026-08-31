#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Baseline scene setup for functional/UI test stacks.

Replaces the old EXAMPLEDB/testdb.tar.bz2 mechanism: instead of loading a
Django fixture straight into the database, the fixture scenes under
tests/resources/scenes are imported through the same REST API a real
deployment uses (via tools/upload_scenes/uploader.py). The resulting rows are
then snapshotted with `manage.py dumpdata` inside the web container, so that
per-test restores stay a single `loaddata` call — the same cost as the old
tar-based fixture.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_UPLOAD_SCENES_DIR = _REPO_ROOT / "tools" / "upload_scenes"
if str(_UPLOAD_SCENES_DIR) not in sys.path:
  sys.path.insert(0, str(_UPLOAD_SCENES_DIR))

from uploader import SceneScapeClient, parse_auth, upload_one  # noqa: E402

_RESOURCES_DIR = Path(__file__).resolve().parents[1] / "resources" / "scenes"

# Keys used by ServiceProfile/_PROFILE_SCENE_ARCHIVES to pick which archives a
# stack needs. Values are tuples of archive paths, uploaded in order.
SCENE_ARCHIVES = {
  "demo": (_RESOURCES_DIR / "Demo.zip",),
  "calibration": (_RESOURCES_DIR / "Queuing.zip",),
  "retail_and_queuing": (_RESOURCES_DIR / "Retail.zip", _RESOURCES_DIR / "Queuing.zip"),
}

# Snapshot excludes rows recreated separately by scenescape-init/createuser
# on every restore, and the transient upload bookkeeping record.
BASELINE_PATH = "/tmp/scenescape_baseline.json"
_DUMPDATA_EXCLUDES = ("manager.PubSubACL", "manager.SceneImport")


def upload_baseline_scenes(resturl, rootcert, auth_path, archive_keys):
  """Imports the archives for *archive_keys* and returns {scene_name: uid}.

  @param    resturl       REST API base URL of the target deployment
  @param    rootcert      CA certificate path used to verify the server
  @param    auth_path     controller.auth file used to authenticate
  @param    archive_keys  keys into SCENE_ARCHIVES to upload
  @return                 dict mapping scene name -> uid
  """
  client = SceneScapeClient(resturl, verify=rootcert)
  user, password = parse_auth(str(auth_path))
  client.authenticate(user, password)

  scene_uids = {}
  for archive_key in archive_keys:
    for archive_path in SCENE_ARCHIVES[archive_key]:
      uid = upload_one(client, str(archive_path))
      if uid is None:
        raise RuntimeError(f"Failed to upload {archive_path} to {resturl}")
      scene_uids[archive_path.stem] = uid

  return scene_uids


def dumpdata_command(manage):
  """Returns the shell command that snapshots the current DB to BASELINE_PATH.

  @param    manage    path to manage.py inside the web container, e.g. "$SCENESCAPE_HOME/manage.py"
  """
  exclude_args = " ".join(f"-e {model}" for model in _DUMPDATA_EXCLUDES)
  return f"python {manage} dumpdata manager {exclude_args} --indent 2 -o {BASELINE_PATH}"
