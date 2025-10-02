# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import zipfile
import json
import asyncio
import aiofiles

from scene_common.rest_client import RESTClient
from scene_common.options import POINT_CORRESPONDENCE, EULER
from scene_common import log

class ImportScene:
  def __init__(self, zip_path, token):
    self.zip_path = zip_path
    self.extractZip()
    self.rootcert = '/run/secrets/certs/scenescape-ca.pem'
    self.resturl = 'https://web.scenescape.intel.com/api/v1'
    self.rest = RESTClient(self.resturl, rootcert=self.rootcert)
    self.rest.token = token
    self.badZipfile = False
    return

  def extractZip(self):
    self.extract_dir = os.path.splitext(self.zip_path)[0]
    os.makedirs(self.extract_dir, exist_ok=True)
    try:
      with zipfile.ZipFile(self.zip_path, 'r') as zip_ref:
        if not zip_ref.namelist():
          self.badZipfile = True
          return
        for member in zip_ref.namelist():
          filename = os.path.basename(member)
          if not filename:
            continue
          source = zip_ref.open(member)
          target_path = os.path.join(self.extract_dir, filename)
          with open(target_path, "wb") as target:
            with source as source_file:
              target.write(source_file.read())
      log.info(f"ZIP extracted to: {self.extract_dir}")
      return True
    except zipfile.BadZipFile:
      self.badZipfile = True
    return

  def createSceneMap(self, json_data, resource_path):
    with open(resource_path, "rb") as f:
      map_data = f.read()
      return self.rest.createScene({"name": json_data["name"], "map": (resource_path, map_data)})

  async def loadScene(self, child=None, parent=None):
    errors = {
      "scene": None,
      "cameras": None,
      "tripwires": None,
      "regions": None,
      "sensors": None,
    }

    basename = os.path.basename(self.extract_dir)
    json_file = os.path.join(self.extract_dir, f"{basename}.json")

    if not os.path.exists(json_file) or self.badZipfile:
      errors["scene"] = {"scene": ["Cannot find JSON or resource file"]}
      return errors

    # Load JSON data
    if child:
      json_data = child
    else:
      try:
        async with aiofiles.open(json_file, "r", encoding="utf-8") as f:
          json_data = json.loads(await f.read())
      except Exception:
        errors["scene"] = {"scene": ["Failed to parse JSON"]}
        return errors

    # find resource (non-json) files
    resource_files = [
      f for f in os.listdir(self.extract_dir)
      if os.path.isfile(os.path.join(self.extract_dir, f)) and not f.lower().endswith(".json")
    ]
    if not resource_files:
      errors["scene"] = {"scene": ["No resource files found"]}
      return errors

    # match resource with scene name
    matched = next((f for f in resource_files if json_data["name"] in f), None)
    if not matched:
      errors["scene"] = {"scene": ["No matching resource file"]}
      return errors

    resource_path = os.path.join(self.extract_dir, matched)

    # Upload scene (wrap sync REST call)
    resp = await asyncio.to_thread(self.createSceneMap, json_data, resource_path)
    if resp.errors:
      errors["scene"] = resp.errors
      return errors

    scene_id = resp.get("uid")

    # Scene update
    scene_data = {k: json_data.get(k) for k in [
      "scale", "regulate_rate", "external_update_rate",
      "camera_calibration", "apriltag_size",
      "number_of_localizations", "global_feature",
      "minimum_number_of_matches", "inlier_threshold",
      "output_lla", "map_corners_lla"
    ]}
    if child:
      scene_data["parent"] = parent

    update_response = await asyncio.to_thread(self.rest.updateScene, scene_id, scene_data)

    # Child link handling
    if child and "link" in child:
      link = child["link"]
      link.pop("uid", None)
      link.pop("transform", None)
      child_uid = update_response.content["uid"]
      parent_uid = update_response.content["parent"]
      link["child"] = child_uid
      link["parent"] = parent_uid
      update_response = await asyncio.to_thread(self.rest.updateChildScene, child_uid, link)
      log.info("Child link updated:", update_response)

    # Bulk create cameras with transform handling
    cam_items = []
    for cam in json_data.get("cameras", []):
      cam_data = {"name": cam["name"], "scale": cam["scale"], "sensor_id": cam["uid"], "intrinsics": cam["intrinsics"]}
      if "transform_type" in cam:
        if cam["transform_type"] == POINT_CORRESPONDENCE:
          cam_data["transforms"] = cam.get("transforms")
          cam_data["transform_type"] = POINT_CORRESPONDENCE
        else:
          cam_data["transform_type"] = EULER
          cam_data["translation"] = cam.get("translation")
          cam_data["rotation"] = cam.get("rotation")
      cam_items.append(cam_data)
    errors["cameras"] = await self.bulk_create(cam_items, scene_id, self.rest.createCamera)

    # Bulk create other resources
    errors["regions"] = await self.bulk_create(json_data.get("regions", []), scene_id, self.rest.createRegion)
    errors["tripwires"] = await self.bulk_create(json_data.get("tripwires", []), scene_id, self.rest.createTripwire)
    errors["sensors"] = await self.bulk_create(json_data.get("sensors", []), scene_id, self.rest.createSensor)

    # children recursion
    for child_data in json_data.get("children", []):
      child_errors = await self.loadScene(child=child_data, parent=scene_id)
      for key, val in child_errors.items():
        if val:
          return child_errors

    return errors

  async def bulk_create(self, items, scene_id, create_fn):
    errors = []
    for item in items or []:
      item["scene"] = scene_id
      try:
        resp = await asyncio.to_thread(create_fn, item)
        if getattr(resp, "errors", None):
          errors.append((resp.errors, item))
      except Exception as e:
        errors.append((e, item))
    return errors or None
