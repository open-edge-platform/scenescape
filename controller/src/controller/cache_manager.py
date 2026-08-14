# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Modifications:
# Nokia VPOD (Emerging Products, BLR), 2026

import threading
import requests
from controller.scene import Scene
from controller.data_source import RestSceneDataSource, FileSceneDataSource

from scene_common import log
from scene_common.timestamp import get_epoch_time

REFRESH_TIME = 60
REFRESH_DIRTY_DEBOUNCE_SEC = 0.1

class CacheManager:
  def __init__(self, data_source=None, rest_url=None, rest_auth=None,
               root_cert=None, tracker_config_data=None):
    self._lock = threading.Lock()
    self.cached_child_transforms_by_uid = {}
    self.camera_parameters = {}
    self.tracker_config_data = tracker_config_data if tracker_config_data is not None else {}
    self.cached_scenes_by_uid = {}
    self._cached_scenes_by_cameraID = {}
    self._cached_scenes_by_sensorID = {}
    self._refresh_in_progress = False
    self._refresh_dirty = False
    self._dirty_since = None
    self._refresh_debounce_sec = REFRESH_DIRTY_DEBOUNCE_SEC

    if rest_url and rest_auth:
      self.data_source = RestSceneDataSource(rest_url, rest_auth, root_cert)
    elif data_source:
      self.data_source = FileSceneDataSource(data_source)
    else:
      raise ValueError("Invalid configuration: must provide rest_url/rest_auth or .json file(s)")
    self.refreshScenes()
    return

  def refreshScenes(self):
    """Refresh scene cache from data source.

    CRITICAL DESIGN: No HTTP calls or Scene construct/update may happen while
    self._lock is held. Holding the lock during those operations blocks the MQTT
    callback thread on lookups (sceneWithCameraID/sceneWithID), causing
    permanent "dead-but-alive" stalls.

    Architectural pattern:
    1. HTTP fetch (OUTSIDE lock)
    2. Camera param sync to DB (OUTSIDE lock)
    3. Snapshot existing scenes (BRIEF lock)
    4. Scene.deserialize / updateScene (OUTSIDE lock)
    5. Atomic dict swap (BRIEF lock); clear dirty only if no newer mark arrived
    """
    refresh_started = get_epoch_time()

    # Step 1: Fetch scene data from REST API (OUTSIDE LOCK)
    try:
      result = self.data_source.getScenes()
    except requests.exceptions.Timeout as e:
      log.error(f"[CACHE_REFRESH_TIMEOUT] REST API timeout - continuing with stale cache")
      return
    except requests.exceptions.RequestException as e:
      log.error(f"[CACHE_REFRESH_ERROR] REST API error: {type(e).__name__}: {e} - continuing with stale cache")
      return
    except Exception as e:
      log.error(f"[CACHE_REFRESH_ERROR] Unexpected error: {type(e).__name__}: {e} - continuing with stale cache")
      return

    if 'results' not in result:
      log.error("Failed to get results, error code: ", result.statusCode)
      return

    found = result.get("results", [])

    # Step 2: Sync camera parameters to DB via HTTP (OUTSIDE LOCK)
    for scene_data in found:
      self._refreshCameras(scene_data)

    # Attach tracker config before heavy Scene work (tracker_config_data is
    # written only at CacheManager init / config load).
    for scene_data in found:
      if self.tracker_config_data:
        scene_data["tracker_config"] = [self.tracker_config_data["max_unreliable_time"],
                                      self.tracker_config_data["non_measurement_time_dynamic"],
                                      self.tracker_config_data["non_measurement_time_static"],
                                      self.tracker_config_data["time_chunking_enabled"],
                                      self.tracker_config_data["time_chunking_interval_milliseconds"],
                                      self.tracker_config_data.get("baseline_frame_rate", 30),
                                      self.tracker_config_data.get("suspended_track_timeout_secs", 60.0)]
        scene_data["persist_attributes"] = self.tracker_config_data.get("persist_attributes", {})

    # Step 3: Snapshot existing Scene objects (BRIEF lock — dict copy only)
    with self._lock:
      existing = dict(self.cached_scenes_by_uid or {})

    # Step 4: Build / update Scene objects OUTSIDE lock so MQTT lookups are not blocked
    new_by_uid = {}
    new_by_camera = {}
    new_by_sensor = {}
    for scene_data in found:
      uid = scene_data['uid']
      if uid not in existing:
        log.debug(f"[SCENE_CACHE] Creating new Scene object for uid={uid} name={scene_data.get('name', 'unknown')} (tracker state reset)")
        scene = Scene.deserialize(scene_data)
      else:
        scene = existing[uid]
        log.debug(f"[SCENE_CACHE] Updating existing Scene object for uid={uid} name={scene_data.get('name', 'unknown')} (tracker state preserved)")
        scene.updateScene(scene_data)

      for cameraID in scene.cameras.keys():
        new_by_camera[cameraID] = scene
      for sensorID in scene.sensors.keys():
        new_by_sensor[sensorID] = scene
      new_by_uid[scene.uid] = scene

    # Step 5: Atomic swap of lookup dicts (BRIEF lock)
    with self._lock:
      self.cached_scenes_by_uid = new_by_uid
      self._cached_scenes_by_cameraID = new_by_camera
      self._cached_scenes_by_sensorID = new_by_sensor
      self._cache_refreshed = get_epoch_time()
      # Preserve dirty marks that arrived after this refresh started so a
      # concurrent markDirty() is not wiped by a stale in-flight refresh.
      if self._dirty_since is None or self._dirty_since <= refresh_started:
        self._refresh_dirty = False
        self._dirty_since = None
    return

  def _refreshCameras(self, scene_data):
    for camera in scene_data.get('cameras', []):
      try:
        update_data = {}
        supported_distortion_values = ('k1','k2','p1','p2','k3')

        if camera['uid'] in self.camera_parameters:
          intrinsics = self.camera_parameters[camera['uid']].get('intrinsics')
          if intrinsics and camera.get('intrinsics') != intrinsics:
            update_data['intrinsics'] = intrinsics

          # Note: Filters to supported distortion coefficients based on database schema constraints.
          # Full distortion model support would require database schema extension.
          distortion = self.camera_parameters[camera['uid']].get('distortion')
          if distortion is not None:
            distortion_values = {
              dist_coeff: distortion.get(dist_coeff)
              for dist_coeff in supported_distortion_values
            }
            if camera.get('distortion') != distortion_values:
              update_data['distortion'] = distortion

        if update_data:
          res = self.data_source.updateCamera(camera['uid'], update_data)
          if not res:
            log.warning(f"Failed to update camera {camera['uid']}")

          # Pull updated camera information from db
          camera = self.data_source.getCamera(camera['uid'])
      except Exception as e:
        log.error(f"[CAMERA_REFRESH_ERROR] camera={camera.get('uid', 'unknown')}: {type(e).__name__}: {e}")
    return

  def refreshScenesForCamParams(self, jdata):
    # Check for changes and collect work (INSIDE LOCK - fast, no HTTP).
    # Minimizes lock hold time by only performing dict lookups and comparisons.
    cameras_to_update = []
    needs_refresh = False

    with self._lock:
      if self.cached_scenes_by_uid is None:
        return
      intrinsics_changed = self.cameraParametersChanged(jdata, 'intrinsics')
      distortion_changed = self.cameraParametersChanged(jdata, 'distortion')

      for scene in self.cached_scenes_by_uid.values():
        for camera in scene.cameras:
          if jdata['id'] == camera:
            intrinsics = jdata.get('intrinsics', {})
            cx = intrinsics.get('cx')
            cy = intrinsics.get('cy')

            if cx is not None and cy is not None:
              width = cx * 2
              height = cy * 2
              current_resolution = scene.cameras[camera].pose.resolution if hasattr(scene.cameras[camera].pose, 'resolution') else None
              if current_resolution != [width, height]:
                if camera not in self.camera_parameters:
                  self.camera_parameters[camera] = {}
                self.camera_parameters[camera]['resolution'] = [width, height]
                cameras_to_update.append(scene.cameras[camera])

      if intrinsics_changed or distortion_changed:
        needs_refresh = True

    # HTTP calls OUTSIDE lock (updateCamera, refreshScenes) to prevent MQTT thread blocking.
    # All network I/O happens after releasing lock to avoid deadlock.
    for cam in cameras_to_update:
      self.updateCamera(cam)

    if needs_refresh:
      log.warning(f"[PROFILE_CACHE] Triggering refreshScenes due to intrinsics/distortion change for camera {jdata['id']}")
      self.checkRefresh(force=True)
    return

  def updateCamera(self, cam):
    if cam.cameraID not in self.camera_parameters:
      return
    params = self.camera_parameters[cam.cameraID]
    intrinsics = params.get('intrinsics')
    distortion = params.get('distortion')
    resolution = params.get('resolution')

    payload = {
      'intrinsics': intrinsics,
      'distortion': distortion
    }
    if resolution is not None:
      payload['resolution'] = {
        'width': resolution[0],
        'height': resolution[1]
      }

    res = self.data_source.updateCamera(cam.cameraID, payload)
    if not res:
      log.warning(f"Failed to update camera {cam.cameraID}")
    return

  def cameraParametersChanged(self, message, parameter_type):
    message_parameters = message.get(parameter_type)
    stored_parameters = self.camera_parameters.get(message['id'], {}).get(parameter_type)
    if message_parameters and message_parameters != stored_parameters:
      self.camera_parameters.setdefault(message['id'], {})[parameter_type] = message[parameter_type]
      return True
    return False

  def markDirty(self):
    with self._lock:
      self._refresh_dirty = True
      self._dirty_since = get_epoch_time()

  def checkRefresh(self, force=False):
    now = get_epoch_time()
    needs_refresh = False
    with self._lock:
      periodic_refresh_due = (
          not hasattr(self, 'cached_scenes_by_uid')
          or self.cached_scenes_by_uid is None
          or not hasattr(self, '_cache_refreshed')
          or now - self._cache_refreshed > REFRESH_TIME
      )
      dirty_refresh_due = (
          self._refresh_dirty
          and (
              self._dirty_since is None
              or now - self._dirty_since >= self._refresh_debounce_sec
          )
      )
      if force or periodic_refresh_due or dirty_refresh_due:
        if not self._refresh_in_progress:
          needs_refresh = True
          self._refresh_in_progress = True
        elif force or dirty_refresh_due:
          # Coalesce: an in-flight refresh cannot absorb a concurrent force/dirty
          # request — mark dirty so a follow-up refresh runs after it completes.
          self._refresh_dirty = True
          self._dirty_since = now
    if needs_refresh:
      try:
        self.refreshScenes()  # HTTP / Scene work happen OUTSIDE the lock
      finally:
        followup = False
        with self._lock:
          self._refresh_in_progress = False
          # A concurrent force/dirty request may have been coalesced while we
          # were in-flight — run one more gated refresh if still dirty.
          if self._refresh_dirty:
            followup = True
        if followup:
          self.checkRefresh(force=True)
    return

  def allScenes(self, force_refresh=False):
    self.checkRefresh(force=force_refresh)
    with self._lock:
      return list((self.cached_scenes_by_uid or {}).values())

  # --- Fast lookup methods (no HTTP, no checkRefresh) ---
  # These are safe to call from the MQTT callback thread because they
  # only do in-memory dict lookups under the lock. They never trigger
  # HTTP calls, so they cannot block the paho network loop.

  def sceneWithCameraID(self, cameraID):
    with self._lock:
      return self._cached_scenes_by_cameraID.get(cameraID, None)

  def sceneWithSensorID(self, sensorID):
    with self._lock:
      return self._cached_scenes_by_sensorID.get(sensorID, None)

  def sceneWithID(self, sceneID):
    with self._lock:
      if self.cached_scenes_by_uid:
        return self.cached_scenes_by_uid.get(sceneID, None)
      return None

  def sceneWithRemoteChildID(self, childID):
    with self._lock:
      return self.cached_child_transforms_by_uid.get(childID, None)

  def startPeriodicRefresh(self, interval=None):
    """Start background thread for periodic cache refresh.

    Replaces on-demand checkRefresh() calls on the MQTT callback thread.
    The MQTT thread now uses lookup methods (dict-only, no HTTP).
    This background thread handles the periodic HTTP refresh instead.
    """
    if interval is None:
      interval = REFRESH_TIME
    self._refresh_interval = interval
    self._refresh_stop = threading.Event()
    self._refresh_thread = threading.Thread(
        target=self._periodicRefreshLoop,
        name="CachePeriodicRefresh",
        daemon=True
    )
    self._refresh_thread.start()
    log.info(f"[CACHE] Started periodic refresh thread (interval={interval}s)")

  def stopPeriodicRefresh(self):
    """Stop the background periodic refresh thread."""
    if hasattr(self, '_refresh_stop'):
      self._refresh_stop.set()
      if hasattr(self, '_refresh_thread') and self._refresh_thread.is_alive():
        self._refresh_thread.join(timeout=5.0)
        log.info("[CACHE] Periodic refresh thread stopped")

  def _periodicRefreshLoop(self):
    """Background thread: periodically refreshes scene cache via HTTP.

    Uses checkRefresh(force=True) so concurrent refreshes share the
    _refresh_in_progress gate instead of racing refreshScenes() directly.
    """
    while not self._refresh_stop.wait(timeout=self._refresh_interval):
      try:
        self.checkRefresh(force=True)
        log.debug("[CACHE_PERIODIC_REFRESH] Refresh completed successfully")
      except Exception as e:
        log.error(f"[CACHE_PERIODIC_REFRESH] Error: {type(e).__name__}: {e}")

  def invalidate(self):
    with self._lock:
      self.cached_scenes_by_uid = None
      # Clear lookup dicts
      self._cached_scenes_by_cameraID = {}
      self._cached_scenes_by_sensorID = {}
      if not hasattr(self, 'cached_child_transforms_by_uid') or self.cached_child_transforms_by_uid is None:
        self.cached_child_transforms_by_uid = {}
    return
