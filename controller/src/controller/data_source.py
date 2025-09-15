# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from abc import ABC, abstractmethod
from pathlib import Path
import json
from scene_common import log
from scene_common.rest_client import RESTClient

class SceneDataSource(ABC):
  @abstractmethod
  def getScenes(self):
    pass

  @abstractmethod
  def getChildScenes(self, scene_uid):
    pass

  @abstractmethod
  def getAssets(self):
    pass

  @abstractmethod
  def updateCamera(self, camera_id, payload):
    pass

  @abstractmethod
  def getCamera(self, camera_id):
    pass


class RestSceneDataSource(SceneDataSource):
  def __init__(self, rest_url, rest_auth, root_cert=None):
    self.rest = RESTClient(rest_url, rootcert=root_cert, auth=rest_auth)
    return

  def getScenes(self):
    return self.rest.getScenes(None)

  def setTRSMatrix(self, scene_uid, matrix):
    return self.rest.updateScene(scene_uid, {'trs_matrix': matrix.tolist()})

  def getChildScenes(self, scene_uid):
    return self.rest.getChildScene({'parent': scene_uid})

  def getAssets(self):
    return self.rest.getAssets({})

  def updateCamera(self, camera_id, payload):
    return self.rest.updateCamera(camera_id, payload)

  def getCamera(self, camera_id):
    return self.rest.getCamera(camera_id)


class FileSceneDataSource(SceneDataSource):
  def __init__(self, paths):
    self.paths = [Path(p) for p in paths]
    self.scenes = []
    self._loadScenesFromFile()
    return

  def _loadScenesFromFile(self):
    self.scenes = []
    for path in self.paths:
      if path.suffix != ".json" or not path.exists():
        continue
      with open(path, "r") as f:
        data = json.load(f)

      if isinstance(data, dict):
        if "results" in data and isinstance(data["results"], list):
          self.scenes.extend(data["results"])
        elif "uid" in data:
          self.scenes.append(data)
      elif isinstance(data, list):
        self.scenes.extend(data)
    return

  def getScenes(self):
    return {"results": self.scenes}

  def getChildScenes(self, scene_uid):
    results = []

    def _extract_children(scene):
      for child in scene.get("children", []):
        link = child.get("link")
        if link and link.get("parent") == scene_uid:
          results.append(link)
        _extract_children(child)

    for scene in self.scenes:
      _extract_children(scene)
    return {"results": results}

  def getAssets(self):
    log.info("[JSON mode] getAssets not supported")
    return []

  def updateCamera(self, camera_id, payload):
    log.info(f"[JSON mode] updateCamera ignored for {camera_id}")
    return None

  def getCamera(self, camera_id):
    for scene in self.scenes:
      for camera in scene.get("cameras", []):
        if camera.get("uid") == camera_id:
          return camera
    log.info(f"[JSON mode] camera {camera_id} not found in file(s)")
    return None
