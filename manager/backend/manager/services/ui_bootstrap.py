# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""UI island bootstrap payloads — single source for Django templates and /api/v1/ui-bootstrap."""

from __future__ import annotations

import json

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import get_object_or_404
from django.urls import reverse

from manager.models import Asset3D, Cam, Scene, SingletonSensor


def user_auth_token(user) -> str:
  """Return a DRF Token string, creating one if the user has none yet."""
  if user is None or not getattr(user, "is_authenticated", False):
    return ""
  try:
    token = user.auth_token
    return str(token.key) if token else ""
  except ObjectDoesNotExist:
    from rest_framework.authtoken.models import Token
    token, _ = Token.objects.get_or_create(user=user)
    return str(token.key)


def _chrome_active_nav(request) -> str | None:
  match = getattr(request, "resolver_match", None)
  name = getattr(match, "url_name", None) if match else None
  if name in ("index", "sceneDetail"):
    return "scenes"
  if name in ("cam_list", "cam_create", "cam_update", "cam_calibrate", "cam_delete"):
    return "cameras"
  if name in (
      "singleton_sensor_list",
      "singleton_sensor_create",
      "singleton_sensor_update",
      "singleton_sensor_delete",
  ):
    return "sensors"
  if name == "model_list":
    return "models"
  if name in ("asset_list", "asset_create", "asset_update", "asset_delete"):
    return "assets"
  return None


def build_chrome_bootstrap(request) -> dict:
  """JSON payload for the React chrome island (`ss-chrome-bootstrap`)."""
  user = getattr(request, "user", None)
  authenticated = bool(user and getattr(user, "is_authenticated", False))
  docs_version = settings.DOCS_VERSION
  is_kubernetes = bool(settings.KUBERNETES_SERVICE_HOST)
  urls = {
    "home": "/",
    "scenes": "/",
    "cameras": reverse("cam_list"),
    "sensors": reverse("singleton_sensor_list"),
    "assets": reverse("asset_list"),
    "admin": "/admin",
    "signOut": "/sign_out",
    "docs": (
      f"https://docs.openedgeplatform.intel.com/{docs_version}"
      "/scenescape/index.html"
    ),
    "support": "https://github.com/open-edge-platform/scenescape/issues",
    "intel": "https://www.intel.com/",
    "intelLogo": f"{settings.STATIC_URL}images/intel-logo.svg",
  }
  # model_list is only registered when KUBERNETES_SERVICE_HOST is set.
  if is_kubernetes:
    urls["models"] = reverse("model_list")
  return {
    "authenticated": authenticated,
    "username": user.username if authenticated else "",
    "isStaff": bool(authenticated and getattr(user, "is_staff", False)),
    "isKubernetes": is_kubernetes,
    "appName": settings.APP_PROPER_NAME,
    "appVersion": settings.APP_VERSION_NUMBER,
    "appGitCommit": settings.APP_GIT_COMMIT,
    "docsVersion": docs_version,
    "urls": urls,
    "activeNav": _chrome_active_nav(request),
  }


def build_scenes_home_bootstrap(request) -> dict:
  scenes = Scene.objects.order_by("name")
  scenes_payload = []
  for scene in scenes:
    scenes_payload.append({
      "id": str(scene.id),
      "name": scene.name,
      "georeferenced": bool(scene.output_lla and scene.map_corners_lla),
      "thumbnailUrl": scene.thumbnail.url if scene.thumbnail else None,
      "mapUrl": scene.map.url if scene.map else None,
      "detailUrl": reverse("sceneDetail", args=[scene.id]),
      "detail3dUrl": reverse("scene_detail", args=[scene.id]),
      "manageUrl": f"{reverse('index')}?ss=scene-manage&id={scene.id}",
      "deleteUrl": (
        reverse("scene_delete", args=[scene.id])
        if request.user.is_superuser else None
      ),
      "counts": {
        "sensors": scene.sensor_set.count(),
        "regions": scene.regions.count(),
        "tripwires": scene.tripwires.count(),
      },
    })
  return {
    "authToken": user_auth_token(request.user),
    "isSuperuser": request.user.is_superuser,
    "scenes": scenes_payload,
  }


def build_scene_detail_bootstrap(request, scene_id) -> dict:
  from manager.views import getAllChildrenMetaData

  scene = get_object_or_404(Scene, pk=scene_id)
  child_rois, child_trips, child_sensors = getAllChildrenMetaData(scene_id)

  cameras = []
  sensors = []
  for sensor in scene.sensor_set.all().order_by("name"):
    if sensor.type == "camera":
      cameras.append({
        "id": str(sensor.id),
        "sensorId": sensor.sensor_id,
        "name": sensor.name,
        "calibrateHref": f"?ss=calibrate-cam&id={sensor.id}",
        "cmdTopic": f"scenescape/cmd/camera/{sensor.sensor_id}",
        "deleteUrl": (
          reverse("cam_delete", args=[sensor.id])
          if request.user.is_superuser else None
        ),
      })
    elif sensor.type == "generic":
      sensors.append({
        "id": str(sensor.id),
        "sensorId": sensor.sensor_id,
        "name": sensor.name,
        "iconUrl": sensor.icon.url if sensor.icon else None,
        "areaJson": sensor.areaJSON(),
        "calibrateHref": f"?ss=calibrate-sensor&id={sensor.id}",
        "editHref": f"?ss=sensor-edit&id={sensor.sensor_id}",
        "deleteUrl": (
          reverse("singleton_sensor_delete", args=[sensor.id])
          if request.user.is_superuser else None
        ),
      })

  children = []
  for link in scene.children.all():
    child = link.child
    child_name = child.name if child else (link.child_name or "Child")
    if child is not None:
      rest_uid = str(child.id)
    elif link.remote_child_id:
      rest_uid = str(link.remote_child_id)
    else:
      rest_uid = str(link.id)
    children.append({
      "id": str(link.id),
      "name": child_name,
      "childType": link.child_type,
      "remoteChildId": (
        str(link.remote_child_id) if link.remote_child_id else None
      ),
      "detailUrl": reverse("sceneDetail", args=[child.id]) if child else None,
      "thumbnailUrl": (
        child.thumbnail.url if child and child.thumbnail else None
      ),
      "mapUrl": child.map.url if child and child.map else None,
      "restUid": rest_uid,
      "editHref": f"?ss=child-edit&id={rest_uid}",
      "deleteUrl": (
        reverse("child_delete", args=[link.id])
        if request.user.is_superuser else None
      ),
    })

  try:
    regions = json.loads(scene.roiJSON() or "[]")
  except (TypeError, json.JSONDecodeError):
    regions = []
  try:
    tripwires = json.loads(scene.tripwireJSON() or "[]")
  except (TypeError, json.JSONDecodeError):
    tripwires = []

  return {
    "scene": {
      "id": str(scene.id),
      "name": scene.name,
      "scale": scene.scale,
      "mapUrl": scene.map.url if scene.map else None,
      "thumbnailUrl": scene.thumbnail.url if scene.thumbnail else None,
      "wssConnection": scene.wssConnection(),
      "outputLla": bool(scene.output_lla),
      "georeferenced": bool(scene.output_lla and scene.map_corners_lla),
    },
    "cameras": cameras,
    "sensors": sensors,
    "children": children,
    "regions": regions if isinstance(regions, list) else [],
    "tripwires": tripwires if isinstance(tripwires, list) else [],
    "assetMarkColors": {
      asset.name: asset.mark_color
      for asset in Asset3D.objects.all()
    },
    "counts": {
      "sensors": len(sensors),
      "regions": len(regions) if isinstance(regions, list) else 0,
      "tripwires": len(tripwires) if isinstance(tripwires, list) else 0,
      "children": len(children),
    },
    "urls": {
      "scenesHome": reverse("index"),
      "camList": reverse("cam_list"),
      "sensorList": reverse("singleton_sensor_list"),
      "scene3d": reverse("scene_detail", args=[scene.id]),
      "sceneEdit": (
        reverse("scene_update", args=[scene.id])
        if request.user.is_superuser else None
      ),
      "sceneDelete": (
        reverse("scene_delete", args=[scene.id])
        if request.user.is_superuser else None
      ),
      "camCreate": (
        f"{reverse('cam_create')}?scene={scene.id}"
        if request.user.is_superuser else None
      ),
    },
    "authToken": user_auth_token(request.user),
    "isSuperuser": request.user.is_superuser,
    "isKubernetes": bool(settings.KUBERNETES_SERVICE_HOST),
    "appVersion": getattr(settings, "APP_VERSION_NUMBER", None),
    "appGitCommit": getattr(settings, "APP_GIT_COMMIT", None),
    "googleMapsApiKey": getattr(settings, "GOOGLE_MAPS_API_KEY", "") or "",
    "mapboxApiKey": getattr(settings, "MAPBOX_API_KEY", "") or "",
    "deleteImpact": {
      "sensors": scene.sensor_set.count(),
      "regions": scene.regions.count(),
      "tripwires": scene.tripwires.count(),
    },
    "childRoiJson": child_rois,
    "childTripwireJson": child_trips,
    "childSensorJson": child_sensors,
    "scenes": [
      {
        "id": str(s.id),
        "name": s.name,
        "georeferenced": bool(s.output_lla and s.map_corners_lla),
        "mapUrl": s.map.url if s.map else None,
      }
      for s in Scene.objects.order_by("name")
    ],
  }


def _scene_picker() -> list[dict]:
  return [
    {"id": str(s.id), "name": s.name}
    for s in Scene.objects.order_by("name")
  ]


def build_cameras_list_bootstrap(request) -> dict:
  primary = None
  if request.user.is_superuser:
    primary = {
      "label": "+ New Camera",
      "href": f"{reverse('cam_list')}?ss=cam-create",
      "id": "new-camera",
    }
  rows = []
  for cam in Cam.objects.all():
    scene = cam.scene
    actions = []
    if request.user.is_superuser:
      if scene:
        actions.append({
          "label": "Manage",
          "href": f"{reverse('cam_list')}?ss=calibrate-cam&id={cam.id}",
        })
      else:
        actions.append({
          "label": "Edit",
          "href": f"{reverse('cam_list')}?ss=cam-edit&id={cam.sensor_id}",
        })
      actions.append({
        "label": "Delete",
        "href": reverse("cam_delete", args=[cam.id]),
        "tone": "danger",
      })
    rows.append({
      "id": str(cam.id),
      "cells": [
        {"text": str(cam)},
        {"text": cam.sensor_id},
        {
          "text": str(scene) if scene else "--",
          "href": (
            f"{reverse('sceneDetail', args=[scene.id])}?from=cam-list"
            if scene else None
          ),
        },
      ],
      "actions": actions,
    })
  return {
    "title": "Cameras",
    "breadcrumbs": [{"label": "Cameras"}],
    "primaryAction": primary,
    "columns": ["Camera Name", "Camera ID", "Scene"],
    "rows": rows,
    "emptyMessage": "No cameras are available.",
    "isSuperuser": request.user.is_superuser,
  }


def build_sensors_list_bootstrap(request) -> dict:
  primary = None
  if request.user.is_superuser:
    primary = {
      "label": "+ New Sensor",
      "href": f"{reverse('singleton_sensor_list')}?ss=sensor-create",
      "id": "new-sensor",
    }
  rows = []
  for sensor in SingletonSensor.objects.all():
    scene = sensor.scene
    actions = []
    if request.user.is_superuser:
      if scene:
        actions.append({
          "label": "Manage",
          "href": (
            f"{reverse('singleton_sensor_list')}"
            f"?ss=calibrate-sensor&id={sensor.id}"
          ),
        })
      else:
        actions.append({
          "label": "Edit",
          "href": (
            f"{reverse('singleton_sensor_list')}"
            f"?ss=sensor-edit&id={sensor.sensor_id}"
          ),
        })
      actions.append({
        "label": "Delete",
        "href": reverse("singleton_sensor_delete", args=[sensor.id]),
        "tone": "danger",
      })
    rows.append({
      "id": str(sensor.id),
      "cells": [
        {"text": str(sensor)},
        {"text": sensor.sensor_id},
        {
          "text": str(scene) if scene else "--",
          "href": (
            f"{reverse('sceneDetail', args=[scene.id])}?from=sensor-list"
            if scene else None
          ),
        },
        {
          "text": (
            sensor.get_singleton_type_display().replace("_", " ").title()
            if sensor.singleton_type else "—"
          ),
        },
      ],
      "actions": actions,
    })
  return {
    "title": "Sensors",
    "breadcrumbs": [{"label": "Sensors"}],
    "primaryAction": primary,
    "columns": ["Sensor Name", "Sensor ID", "Scene", "Type"],
    "rows": rows,
    "emptyMessage": "No sensors are available.",
    "isSuperuser": request.user.is_superuser,
  }


def build_assets_list_bootstrap(request) -> dict:
  primary = None
  if request.user.is_superuser:
    primary = {
      "label": "+ New Object",
      "href": f"{reverse('asset_list')}?ss=asset-create",
      "id": "new-asset",
    }
  rows = []
  for asset in Asset3D.objects.all():
    actions = []
    if request.user.is_superuser:
      actions.append({
        "label": "Update",
        "href": f"{reverse('asset_list')}?ss=asset-edit&id={asset.id}",
        "id": f"obj-manage-{asset.name}",
      })
      actions.append({
        "label": "Delete",
        "href": reverse("asset_delete", args=[asset.id]),
        "tone": "danger",
      })
    mark = (asset.mark_color or "").strip() or "#888888"
    size_text = f"{asset.x_size:g} × {asset.y_size:g} × {asset.z_size:g}"
    if asset.model_3d:
      model_name = asset.model_3d.name.rsplit("/", 1)[-1]
    else:
      model_name = "—"
    rows.append({
      "id": str(asset.id),
      "cells": [
        {"text": asset.name},
        {"text": size_text},
        {"text": mark, "swatch": mark},
        {"text": model_name},
        {"text": f"{asset.tracking_radius:g} m"},
      ],
      "actions": actions,
    })
  return {
    "title": "Object Library",
    "breadcrumbs": [{"label": "Object Library"}],
    "primaryAction": primary,
    "columns": [
      "Name", "Size", "Mark color", "3D model", "Tracking radius",
    ],
    "rows": rows,
    "emptyMessage": "No objects are available.",
    "isSuperuser": request.user.is_superuser,
  }


def build_list_sheets_bootstrap(request, kind: str) -> dict:
  kind = (kind or "").strip().lower()
  if kind not in ("cam", "sensor", "asset"):
    raise ValueError("list-sheets bootstrap requires id=cam|sensor|asset")
  payload = {
    "authToken": user_auth_token(request.user),
    "isSuperuser": request.user.is_superuser,
    "kind": kind,
    "defaultSceneId": None,
    "scenes": _scene_picker() if kind in ("cam", "sensor") else [],
  }
  if kind == "cam":
    payload["isKubernetes"] = bool(settings.KUBERNETES_SERVICE_HOST)
    payload["cameras"] = [
      {
        "id": str(cam.id),
        "sensorId": cam.sensor_id,
        "name": str(cam),
        "sceneId": str(cam.scene_id) if cam.scene_id else None,
      }
      for cam in Cam.objects.all()
    ]
  elif kind == "sensor":
    payload["sensors"] = [
      {
        "id": str(sensor.id),
        "sensorId": sensor.sensor_id,
        "name": str(sensor),
        "sceneId": str(sensor.scene_id) if sensor.scene_id else None,
      }
      for sensor in SingletonSensor.objects.all()
    ]
  return payload


def build_models_directory_bootstrap(request) -> dict:
  return {
    "authToken": user_auth_token(request.user),
    "isSuperuser": request.user.is_superuser,
  }


def build_sign_in_bootstrap(request) -> dict:
  docs_version = settings.DOCS_VERSION
  next_url = request.GET.get("next") or ""
  return {
    "appName": settings.APP_PROPER_NAME,
    "appVersion": settings.APP_VERSION_NUMBER,
    "intelLogo": f"{settings.STATIC_URL}images/intel-logo.svg",
    "intelHref": "https://www.intel.com/",
    "nextUrl": next_url,
    "docsVersion": docs_version,
  }


def resolve_ui_bootstrap(request, page: str, entity_id: str | None = None) -> dict:
  """Return bootstrap dict for page name. Raises ValueError for bad page/id."""
  page = (page or "").strip().lower()
  if page == "chrome":
    return build_chrome_bootstrap(request)
  if page in ("scenes", "scenes-home", "home"):
    return build_scenes_home_bootstrap(request)
  if page in ("scene", "scene-detail"):
    if not entity_id:
      raise ValueError("scene bootstrap requires id")
    return build_scene_detail_bootstrap(request, entity_id)
  if page in ("cameras", "cam-list", "cam"):
    return build_cameras_list_bootstrap(request)
  if page in ("sensors", "sensor-list", "singleton-sensor"):
    return build_sensors_list_bootstrap(request)
  if page in ("assets", "asset-list", "object-library"):
    return build_assets_list_bootstrap(request)
  if page in ("models", "model-list", "models-directory"):
    return build_models_directory_bootstrap(request)
  if page in ("list-sheets", "sheets"):
    return build_list_sheets_bootstrap(request, entity_id or "")
  if page in ("sign-in", "signin", "login"):
    return build_sign_in_bootstrap(request)
  raise ValueError(f"unknown page: {page}")
