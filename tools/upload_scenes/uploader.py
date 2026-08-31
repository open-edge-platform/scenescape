#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared logic for uploading exported scenes to a Scenescape deployment.

Used by the `upload-scenes` CLI and by the test suite's baseline-scene setup,
so the two never drift apart on how a scene archive is imported.
"""

import json
import logging
import os
import time
import zipfile

import requests

DEFAULT_WAIT_SECONDS = 300
POLL_INTERVAL_SECONDS = 5
REQUEST_TIMEOUT_SECONDS = 60
RESOURCE_KEYS = ("cameras", "regions", "tripwires", "sensors")

log = logging.getLogger("upload-scenes")


class SceneScapeClient:
  """The handful of REST calls needed to import a scene and its dependencies."""

  def __init__(self, url, verify):
    self.url = url.rstrip("/")
    self.session = requests.Session()
    self.session.verify = verify
    return

  def _request(self, method, path, **kwargs):
    reply = self.session.request(method, f"{self.url}{path}",
                                 timeout=REQUEST_TIMEOUT_SECONDS, **kwargs)
    reply.raise_for_status()
    return reply.json()

  def authenticate(self, user, password):
    reply = self._request("POST", "/auth", data={"username": user, "password": password})
    self.session.headers["Authorization"] = f"Token {reply['token']}"
    return

  def is_database_ready(self):
    reply = self.session.get(f"{self.url}/database-ready", timeout=REQUEST_TIMEOUT_SECONDS)
    return reply.ok and reply.json().get("databaseReady", False)

  def scene_uid(self, name):
    """Returns the uid of the scene called `name`, or None when it does not exist."""
    results = self._request("GET", "/scenes", params={"name": name}).get("results", [])
    return results[0]["uid"] if results else None

  def asset_exists(self, name):
    return bool(self._request("GET", "/assets", params={"name": name}).get("results", []))

  def create_asset(self, asset):
    return self._request("POST", "/asset", json=asset)

  def create_calibration_marker(self, marker):
    return self._request("POST", "/calibrationmarker", json=marker)

  def import_scene(self, zip_path):
    """Posts a scene archive and returns the server's import summary."""
    with open(zip_path, "rb") as archive:
      files = {"zipFile": (os.path.basename(zip_path), archive, "application/zip")}
      return self._request("POST", "/import-scene/", files=files)


def parse_auth(auth):
  """Splits `user:password`, or reads both out of a Scenescape auth file."""
  if os.path.exists(auth):
    with open(auth, encoding="utf-8") as auth_file:
      data = json.load(auth_file)
    return data["user"], data["password"]

  user, separator, password = auth.partition(":")
  if not separator or not user:
    raise ValueError("--restauth must be an existing auth file or a user:password string")
  return user, password


def wait_for_database(client, timeout):
  """Polls the deployment until it reports its database ready, or the timeout expires."""
  deadline = time.monotonic() + timeout
  while True:
    try:
      if client.is_database_ready():
        return True
    except requests.RequestException as e:
      log.debug(f"Deployment not reachable yet: {e}")
    if time.monotonic() >= deadline:
      return False
    time.sleep(POLL_INTERVAL_SECONDS)


def read_scene_from_zip(zip_path):
  """Reads the scene definition out of a scene archive, or None when unusable."""
  try:
    with zipfile.ZipFile(zip_path) as archive:
      json_names = [name for name in archive.namelist() if name.lower().endswith(".json")]
      if len(json_names) != 1:
        log.error(f"Skipping {zip_path}: expected one JSON file, found {len(json_names)}")
        return None
      scene = json.loads(archive.read(json_names[0]))
  except (OSError, zipfile.BadZipFile, json.JSONDecodeError) as e:
    log.error(f"Failed to read {zip_path}: {e}")
    return None

  name = scene.get("name") if isinstance(scene, dict) else None
  if not name or not isinstance(name, str):
    log.error(f"Skipping {zip_path}: the archived JSON does not describe a scene")
    return None
  return scene


def upload_assets(client, scene):
  """Creates the object library entries a scene relies on, unless they exist already."""
  for asset in scene.get("assets", []):
    name = asset.get("name")
    if not name:
      log.error(f"Ignoring an asset without a name in scene '{scene['name']}'")
      return False
    if client.asset_exists(name):
      continue
    client.create_asset(asset)
  return True


def upload_calibration_markers(client, scene):
  """Creates the AprilTag markers of a scene, which the import endpoint ignores."""
  markers = scene.get("calibration_markers")
  if not markers:
    return True

  uid = client.scene_uid(scene["name"])
  if not uid:
    log.error(f"Cannot add calibration markers, scene '{scene['name']}' was not found")
    return False

  for marker in markers:
    apriltag_id = str(marker["apriltag_id"])
    client.create_calibration_marker({
      "marker_id": f"{uid}_{apriltag_id}",
      "apriltag_id": apriltag_id,
      "dims": marker["dims"],
      "scene": uid,
    })
  return True


def upload_scene(client, scene, zip_path):
  """Imports a single scene archive and reports any problem the server returned."""
  name = scene["name"]
  summary = client.import_scene(zip_path)
  if summary.get("scene"):
    log.error(f"Failed to import scene '{name}': {summary['scene']}")
    return False

  for key in RESOURCE_KEYS:
    if summary.get(key):
      log.warning(f"Scene '{name}' reported problems with {key}: {summary[key]}")
  return True


def upload_one(client, zip_path):
  """Imports a single scene archive plus its assets/markers.

  Returns the scene's uid on success, None on failure or if it already
  exists (in which case the existing uid is still returned).
  """
  scene = read_scene_from_zip(zip_path)
  if scene is None:
    return None

  name = scene["name"]
  existing_uid = client.scene_uid(name)
  if existing_uid:
    log.info(f"Scene '{name}' already exists, skipping {zip_path}")
    return existing_uid

  if not upload_assets(client, scene) \
      or not upload_scene(client, scene, zip_path) \
      or not upload_calibration_markers(client, scene):
    return None

  log.info(f"Uploaded scene '{name}' from {zip_path}")
  return client.scene_uid(name)


def upload_all(client, scene_archives):
  """Uploads every archive, returning the number that failed."""
  failed = 0
  for zip_path in scene_archives:
    try:
      if upload_one(client, zip_path) is None:
        failed += 1
    except requests.RequestException as e:
      log.error(f"Failed to upload {zip_path}: {e}")
      failed += 1
  return failed
