# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import zipfile
import json
import asyncio
from uuid import UUID
from typing import Any, Callable

import aiofiles
import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from rest_framework.exceptions import ValidationError

from manager.models import ChildScene
from manager.scene_archive import (
  LINK_FIELDS, remote_link_data, scene_map_path, validate_archive, validate_existing_link,
)
from manager.serializers import SceneSerializer
from scene_common.rest_client import RESTClient, RESTResult
from scene_common.options import POINT_CORRESPONDENCE, EULER
from scene_common.cam_fields import CAM_COMMON_FIELDS
from scene_common import log


class ImportScene:
  def __init__(self, zip_path, token, restore_ids=False, remote_credentials=None, reuse_existing=False):
    self.zip_path = zip_path
    self.badZipfile = False
    self.restore_ids = restore_ids
    self.reuse_existing = reuse_existing
    self.existing_scenes = {}
    self.remote_credentials = remote_credentials or {}
    self.extractZip()
    self.rootcert = '/run/secrets/certs/scenescape-ca.pem'
    self.baseUrl = os.getenv("WEBSERVER_URL", "https://web.scenescape.intel.com")
    self.restUrl = self.baseUrl + '/api/v1'
    self.rest = RESTClient(self.restUrl, rootcert=self.rootcert)
    self.rest.token = token
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
          # map_transform_fields requires scale to write transforms; default if archive omits it.
          "scale": cam.get("scale") or [1.0, 1.0, 1.0],
        })
      cam_items.append(cam_data)
    return cam_items

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
      scene_data = {"name": json_data["name"], "scale": json_data.get("scale"),
                    "map": SimpleUploadedFile(os.path.basename(resource_path), f.read())}
    serializer = SceneSerializer(data=scene_data)
    if not serializer.is_valid():
      return RESTResult(400, errors=serializer.errors)
    extra = {"id": UUID(str(json_data["uid"]))} if self.restore_ids else {}
    try:
      scene = serializer.save(**extra)
    except (IntegrityError, ValidationError):
      return RESTResult(400, errors={"scene": ["Scene creation failed; check name and UUID collisions"]})
    result = RESTResult(201)
    result["uid"] = str(scene.pk)
    return result

  def preflight(self, json_data):
    try:
      self.existing_scenes = validate_archive(
        json_data, self.extract_dir, self.restore_ids, self.remote_credentials, self.reuse_existing)
    except (ValueError, TypeError, KeyError) as error:
      return {"scene": [str(error)]}
    return None

  def restore_local_link(self, child, scene_id, parent):
    data = {key: child.get("link", {})[key] for key in LINK_FIELDS if key in child.get("link", {})}
    data.update({"child_type": "local", "child": scene_id, "parent": parent})
    return self.restore_link(data)

  def restore_link(self, data):
    try:
      if self.reuse_existing:
        lookup = {"child_id": data["child"]} if data["child_type"] == "local" else {
          "remote_child_id": data["remote_child_id"]}
        existing = ChildScene.objects.filter(**lookup).first()
        if existing is not None:
          validate_existing_link(existing, data, data["parent"])
          return RESTResult(200)
      return self.rest.createChildScene(data)
    except (ValueError, requests.RequestException) as error:
      log.error(f"Scene link restoration failed ({type(error).__name__})")
      message = str(error) if isinstance(error, ValueError) else "Cannot contact child-link API"
      return RESTResult(400, errors={"scene": [message]})

  async def restore_remote_links(self, json_data, scene_id):
    for link in json_data.get("remote_children", []):
      data = remote_link_data(link, self.remote_credentials)
      data["parent"] = scene_id
      response = await asyncio.to_thread(self.restore_link, data)
      if response.errors:
        return {"scene": [f"Failed to restore remote child {link['remote_child_id']}"]}
    return None

  async def prepare_scene(self, json_data, summary):
    """Create scene resources only for missing scenes; reused scenes remain untouched."""
    existing_id = self.existing_scenes.get(json_data["name"])
    if existing_id is not None:
      log.info(f"Reusing scene '{json_data['name']}' without changing its resources")
      return existing_id
    resource_path = scene_map_path(json_data, self.extract_dir)
    response = await asyncio.to_thread(self.createSceneMap, json_data, resource_path)
    if response.errors:
      summary["scene"] = response.errors
      return None
    scene_id = response.get("uid")
    await self.populate_scene(json_data, scene_id, summary)
    return scene_id

  async def update_scene_settings(self, scene_id, data):
    if data:
      response = await asyncio.to_thread(self.rest.updateScene, scene_id, data)
      return response.errors
    return None

  async def loadScene(self, child=None, parent=None):
    import_summary = {
      "scene": None,
      "cameras": None,
      "tripwires": None,
      "regions": None,
      "sensors": None,
      "calibration_markers": None,
      "cameras_created": None,
      "tripwires_created": None,
      "regions_created": None,
      "sensors_created": None,
      "calibration_markers_created": None,
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

    if not child:
      import_summary["scene"] = await asyncio.to_thread(self.preflight, json_data)
      if import_summary["scene"]:
        return import_summary
    scene_id = await self.prepare_scene(json_data, import_summary)
    if import_summary["scene"]:
      return import_summary

    if child:
      link_response = await asyncio.to_thread(self.restore_local_link, child, scene_id, parent)
      if link_response.errors:
        import_summary["scene"] = link_response.errors
        return import_summary
    import_summary["scene"] = await self.restore_remote_links(json_data, scene_id)
    if import_summary["scene"]:
      return import_summary

    error_fields = ("scene", "cameras", "tripwires", "regions", "sensors", "calibration_markers")
    for child_data in json_data.get("children", []):
      child_summary = await self.loadScene(child=child_data, parent=scene_id)
      if any(child_summary[key] for key in error_fields):
        return child_summary

    return import_summary

  async def populate_scene(self, json_data, scene_id, import_summary):
    # Scene update. Omit keys absent from the export: several of these model
    # fields are non-nullable, so sending an explicit null for one missing key
    # would reject the whole partial update (including camera_calibration).
    scene_data = {k: json_data[k] for k in [
      "use_tracker", "regulated_rate", "external_update_rate",
      "camera_calibration", "apriltag_size",
      "number_of_localizations", "global_feature", "local_feature", "matcher",
      "minimum_number_of_matches", "inlier_threshold",
      "output_lla", "map_corners_lla",
      "geospatial_provider", "map_zoom", "map_center_lat", "map_center_lng", "map_bearing",
      "mesh_translation", "mesh_rotation", "mesh_scale"
    ] if json_data.get(k) is not None}
    import_summary["scene"] = await self.update_scene_settings(scene_id, scene_data)
    if import_summary["scene"]:
      return import_summary

    # Bulk create cameras with transform handling
    cam_items = self.build_camera_items(json_data)
    cameras_created, camera_errors = await self.bulk_create(
      cam_items, scene_id, self.rest.createCamera)
    import_summary["cameras"] = camera_errors
    import_summary["cameras_created"] = cameras_created
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

    # Calibration markers are scoped to this scene via a synthetic marker_id.
    markers = json_data.get("calibration_markers", []) or []
    for marker in markers:
      marker["marker_id"] = f"{scene_id}_{marker.get('apriltag_id')}"
    markers_created, marker_errors = await self.bulk_create(
      markers, scene_id, self.rest.createCalibrationMarker)
    import_summary["calibration_markers"] = marker_errors
    import_summary["calibration_markers_created"] = markers_created

  async def bulk_create(
      self,
      items: list[dict[str, Any]] | None,
      scene_id: str,
      create_fn: Callable[[dict[str, Any]], Any],
  ) -> tuple[list[dict[str, Any]] | None, list[tuple[Any, dict[str, Any]]] | None]:
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
        log.error(f"Scene resource creation failed ({type(e).__name__})")
        errors.append(({"error": [f"Resource creation failed ({type(e).__name__})"]}, item))
    return created or None, errors or None
