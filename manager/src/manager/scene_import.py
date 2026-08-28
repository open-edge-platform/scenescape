# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import zipfile
import json
import asyncio
import aiofiles
from typing import Any, Callable

from scene_common.rest_client import RESTClient
from scene_common.options import POINT_CORRESPONDENCE, EULER
from scene_common.cam_fields import CAM_COMMON_FIELDS
from scene_common.radar_fields import RADAR_COMMON_FIELDS
from scene_common import log


class ImportScene:
  def __init__(self, zip_path, token):
    self.zip_path = zip_path
    self.extractZip()
    self.rootcert = '/run/secrets/certs/scenescape-ca.pem'
    self.baseUrl = os.getenv("WEBSERVER_URL", "https://web.scenescape.intel.com")
    self.restUrl = self.baseUrl + '/api/v1'
    self.rest = RESTClient(self.restUrl, rootcert=self.rootcert)
    self.rest.token = token
    self.badZipfile = False
    return

  def build_camera_items(self, json_data):
    cam_items = []

    for cam in json_data.get("cameras", []):
      cam_data = {
        "sensor_id": cam.get("uid"),
        **{field: cam.get(field) for field in CAM_COMMON_FIELDS if field in cam},
      }

      transform_type = cam.get("transform_type")
      if transform_type == POINT_CORRESPONDENCE:
        cam_data.update({
          "transform_type": POINT_CORRESPONDENCE,
          "transforms": cam.get("transforms"),
        })
      elif transform_type:
        cam_data.update({
          "transform_type": EULER,
          "translation": cam.get("translation"),
          "rotation": cam.get("rotation"),
        })
      cam_items.append(cam_data)
    return cam_items

  def build_radar_items(self, json_data):
    radar_items = []
    for radar in json_data.get("radars", []):
      radar_data = {
        "sensor_id": radar.get("uid"),
        **{field: radar.get(field) for field in RADAR_COMMON_FIELDS if field in radar},
      }
      transform_type = radar.get("transform_type")
      if transform_type:
        radar_data.update({
          "transform_type": EULER if transform_type != "matrix" else transform_type,
          "translation": radar.get("translation"),
          "rotation": radar.get("rotation"),
          "scale": radar.get("scale", [1.0, 1.0, 1.0]),
        })
        if transform_type == "matrix":
          radar_data["transforms"] = radar.get("transforms")
      radar_items.append(radar_data)
    return radar_items

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
      return self.rest.createScene({"name": json_data["name"],
                                  "scale": json_data['scale'],
                                  "map": (resource_path, map_data)})

  async def loadScene(self, child=None, parent=None):
    import_summary = {
      "scene": None,
      "cameras": None,
      "radars": None,
      "tripwires": None,
      "regions": None,
      "sensors": None,
      "cameras_created": None,
      "radars_created": None,
      "tripwires_created": None,
      "regions_created": None,
      "sensors_created": None,
    }

    json_files = [
      entry.name for entry in os.scandir(self.extract_dir)
      if entry.is_file() and entry.name.lower().endswith(".json")
    ]

    if not json_files:
      import_summary["scene"] = {"scene": ["No JSON file found"]}
      return import_summary

    if len(json_files) > 1:
      import_summary["scene"] = {"scene": ["Multiple JSON files found"]}
      return import_summary

    json_file = os.path.join(self.extract_dir, json_files[0])

    if self.badZipfile:
      import_summary["scene"] = {"scene": ["Cannot find resource file"]}
      return import_summary

    # Load JSON data
    if child:
      json_data = child
    else:
      try:
        async with aiofiles.open(json_file, "r", encoding="utf-8") as f:
          json_data = json.loads(await f.read())
      except Exception:
        import_summary["scene"] = {"scene": ["Failed to parse JSON"]}
        return import_summary

    # find resource (non-json) files
    resource_files = [
      f for f in os.listdir(self.extract_dir)
      if os.path.isfile(os.path.join(self.extract_dir, f)) and not f.lower().endswith(".json")
    ]
    if not resource_files:
      import_summary["scene"] = {"scene": ["No resource files found"]}
      return import_summary

    # match resource with scene name
    matched = next((f for f in resource_files if json_data["name"] in f), None)
    if not matched:
      import_summary["scene"] = {"scene": ["No matching resource file"]}
      return import_summary

    resource_path = os.path.join(self.extract_dir, matched)

    # Upload scene (wrap sync REST call)
    resp = await asyncio.to_thread(self.createSceneMap, json_data, resource_path)
    if resp.errors:
      import_summary["scene"] = resp.errors
      return import_summary

    scene_id = resp.get("uid")

    # Scene update
    scene_data = {k: json_data.get(k) for k in [
      "external_update_rate",
      "camera_calibration", "apriltag_size",
      "number_of_localizations", "global_feature",
      "minimum_number_of_matches", "inlier_threshold",
      "output_lla", "map_corners_lla",
      "mesh_translation", "mesh_rotation", "mesh_scale"
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
    cam_items = self.build_camera_items(json_data)
    cameras_created, camera_errors = await self.bulk_create(
      cam_items, scene_id, self.rest.createCamera)
    import_summary["cameras"] = camera_errors
    import_summary["cameras_created"] = cameras_created

    radar_items = self.build_radar_items(json_data)
    radars_created, radar_errors = await self.bulk_create(
      radar_items, scene_id, self.rest.createRadar)
    import_summary["radars"] = radar_errors
    import_summary["radars_created"] = radars_created

    # Bulk create other resources
    regions_created, region_errors = await self.bulk_create(
      json_data.get("regions", []), scene_id, self.rest.createRegion)
    import_summary["regions"] = region_errors
    import_summary["regions_created"] = regions_created

    tripwires_created, tripwire_errors = await self.bulk_create(
      json_data.get("tripwires", []), scene_id, self.rest.createTripwire)
    import_summary["tripwires"] = tripwire_errors
    import_summary["tripwires_created"] = tripwires_created

    sensors_created, sensor_errors = await self.bulk_create(
      json_data.get("sensors", []), scene_id, self.rest.createSensor)
    import_summary["sensors"] = sensor_errors
    import_summary["sensors_created"] = sensors_created

    # children recursion
    for child_data in json_data.get("children", []):
      child_summary = await self.loadScene(child=child_data, parent=scene_id)
      if any(child_summary[key] for key in (
          "scene", "cameras", "radars", "tripwires", "regions", "sensors")):
        return child_summary

    return import_summary

  async def bulk_create(
      self,
      items: list[dict[str, Any]] | None,
      scene_id: str,
      create_fn: Callable[[dict[str, Any]], Any]) -> tuple[
        list[dict[str, Any]] | None,
        list[tuple[Any, dict[str, Any]]] | None]:
    """Creates many scene resources and returns (created_items, errors)."""
    errors = []
    created = []
    for item in items or []:
      item["scene"] = scene_id
      try:
        resp = await asyncio.to_thread(create_fn, item)
        if getattr(resp, "errors", None):
          errors.append((resp.errors, item))
        else:
          created.append(dict(resp))
      except Exception as e:
        errors.append((e, item))
    return created or None, errors or None
