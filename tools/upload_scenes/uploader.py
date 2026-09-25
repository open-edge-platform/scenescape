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
# Each scene lives in its own directory: <scene>/<scene>.zip. The archived
# JSON carries the scene's calibration_markers directly, plus each camera's
# "command"/"camerachain" fields; on Kubernetes, kubeclient builds each
# camera's DL Streamer pipeline from those two DB fields, while Compose's
# dlsps containers use static pipeline JSON and simply ignore them.
# Object library (Asset3D) entries have no scene FK, so they aren't part of
# any scene archive; see read_object_library()/upload_object_library().

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

  def calibration_marker_exists(self, marker_id):
    try:
      self._request("GET", f"/calibrationmarker/{marker_id}")
      return True
    except requests.HTTPError as e:
      if e.response is not None and e.response.status_code == 404:
        return False
      raise

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


def is_application_ready(client, timeout, user, password):
  """Polls until the deployment accepts auth, or the timeout expires."""
  deadline = time.monotonic() + timeout
  while True:
    try:
      client.authenticate(user, password)
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


def read_object_library(path):
  """Reads a standalone object-library.json (a plain list of asset dicts).

  Returns [] when the file is absent (the library is optional), or None when
  present but unreadable/malformed.
  """
  if not os.path.isfile(path):
    return []
  try:
    with open(path, encoding="utf-8") as library_file:
      library = json.load(library_file)
  except (OSError, json.JSONDecodeError) as e:
    log.error(f"Failed to read {path}: {e}")
    return None
  if not isinstance(library, list):
    log.error(f"{path} must contain a JSON list of asset objects")
    return None
  return library


def upload_object_library(client, library):
  """Creates object library (Asset3D) entries, unless they already exist by name.

  Assets have no scene FK: they're a global library shared by every scene, so
  they're provisioned once from a standalone file instead of per-scene archives.
  """
  for asset in library:
    if not isinstance(asset, dict):
      log.error("Ignoring malformed object library entry: not an object")
      return False
    name = asset.get("name")
    if not name or not isinstance(name, str):
      log.error("Ignoring an object library entry without a valid name")
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

  if not isinstance(markers, (list, tuple)):
    log.error("Scene '%s' has invalid 'calibration_markers' entry (expected list)", scene.get('name'))
    return False

  uid = client.scene_uid(scene["name"])
  if not uid:
    log.error("Cannot add calibration markers, scene '%s' was not found", scene.get('name'))
    return False

  for marker in markers:
    if not isinstance(marker, dict):
      log.error("Ignoring malformed marker in scene '%s': not an object", scene.get('name'))
      return False
    if "apriltag_id" not in marker:
      log.error("Ignoring marker without 'apriltag_id' in scene '%s'", scene.get('name'))
      return False
    apriltag_id = str(marker["apriltag_id"])
    if "dims" not in marker:
      log.error("Ignoring marker without 'dims' in scene '%s'", scene.get('name'))
      return False
    marker_id = f"{uid}_{apriltag_id}"
    if client.calibration_marker_exists(marker_id):
      continue
    client.create_calibration_marker({
      "marker_id": marker_id,
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

  failed = False
  for key in RESOURCE_KEYS:
    if summary.get(key):
      log.error(f"Failed to import {key} for scene '{name}': {summary[key]}")
      failed = True
  return not failed


def upload_one(client, zip_path):
  """Imports a single scene archive plus its calibration markers.

  Returns the scene's uid on success (including when it already exists), or
  None on failure.
  """
  scene = read_scene_from_zip(zip_path)
  if scene is None:
    return None

  name = scene["name"]
  existing_uid = client.scene_uid(name)
  if existing_uid:
    log.info(f"Scene '{name}' already exists, reconciling markers for {zip_path}")
    if not upload_calibration_markers(client, scene):
      return None
    return existing_uid

  if not upload_scene(client, scene, zip_path) \
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
    except Exception as e:
      # Treat data/structure errors in an archive as a per-archive failure and
      # continue with the rest of the batch.
      log.error("Failed to process %s: %s", zip_path, e)
      failed += 1
  return failed
