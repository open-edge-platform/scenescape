# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Static-data access for the Observation Processor service.

Resolves the data the ProcessDetections contract declares out-of-band, via the
Manager REST API (scene_common.rest_client.RESTClient):
  - scene_id  -> scene record, scene mesh (GLB) and mesh pose
  - camera_id -> camera intrinsics, image size and camera->world pose
  - category  -> object-library asset: size prior and per-object flags

Builds and caches one observation_conditioning.AmodalReasoner per
(scene, camera) pair; the bake is invalidated whenever the mesh, mesh pose or
camera calibration changes. Caches are loaded eagerly with warm() and have no
expiry: configuration changes always go through the Manager, which publishes
"update" on scenescape/cmd/database — the server subscribes to that topic and
calls invalidate(), waking the readiness worker for a configuration refresh.
Meshes and calibrated-camera reasoners are loaded before publishing the new
snapshot. Unchanged meshes and reasoners are reused after checking mesh content,
mesh pose and calibration; same-URL mesh replacements are detected. Requests
retain the last successfully warmed snapshot throughout refreshes and failures.
"""

import hashlib
import os
import tempfile
import threading
from urllib.parse import urljoin, urlsplit

import numpy as np
import requests
from scipy.spatial.transform import Rotation

from scene_common import log
from scene_common.rest_client import RESTClient
from scene_common.transform import CameraIntrinsics

DEFAULT_REST_URL = "https://web.scenescape.intel.com/api/v1"
DEFAULT_AUTH = "/run/secrets/observation_processor.auth"
DEFAULT_ROOTCERT = "/run/secrets/certs/scenescape-ca.pem"
DEFAULT_MEDIA_ROOT = "/workspace/media"
DEFAULT_NUM_LAYERS = 4
MAX_SCENE_MESH_BYTES = 100 * 1024 * 1024
MESH_DOWNLOAD_CHUNK_SIZE = 64 * 1024
DEFAULT_WORLD_UP = (0.0, 0.0, 1.0)
DISTORTION_KEYS = ("k1", "k2", "p1", "p2", "k3", "k4", "k5", "k6",
                   "s1", "s2", "s3", "s4", "taux", "tauy")

# Fallback prior for categories without an object-library asset
# (see proto CameraDetection.category).
PEDESTRIAN_PRIOR = {
  "mu_x": 0.55, "mu_y": 0.55, "mu_z": 1.70,
  "sigma_x": 0.10, "sigma_y": 0.10, "sigma_z": 0.15,
}
# Assets define sizes but no size uncertainty; derive sigma as this fraction
# of each dimension.
DEFAULT_SIGMA_FRACTION = 0.15


def _http_origin(url):
  try:
    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    hostname = parsed.hostname
    port = parsed.port
  except ValueError:
    return None
  if scheme not in ("http", "https") or hostname is None \
      or parsed.username is not None or parsed.password is not None:
    return None
  if port is None:
    port = 443 if scheme == "https" else 80
  return scheme, hostname.lower(), port


def _read_mesh_response(reply, url):
  if reply.status_code != 200:
    raise StoreUnavailableError(f"download {url}: HTTP {reply.status_code}")
  content_length = reply.headers.get("Content-Length")
  if content_length is not None:
    try:
      declared_size = int(content_length)
    except ValueError as exc:
      raise StoreUnavailableError("scene mesh has invalid Content-Length") from exc
    if declared_size < 0 or declared_size > MAX_SCENE_MESH_BYTES:
      raise StoreUnavailableError(
        f"scene mesh exceeds maximum download size of {MAX_SCENE_MESH_BYTES} bytes")
  content = bytearray()
  for chunk in reply.iter_content(chunk_size=MESH_DOWNLOAD_CHUNK_SIZE):
    if len(content) + len(chunk) > MAX_SCENE_MESH_BYTES:
      raise StoreUnavailableError(
        f"scene mesh exceeds maximum download size of {MAX_SCENE_MESH_BYTES} bytes")
    content.extend(chunk)
  return bytes(content)


class StoreUnavailableError(Exception):
  """The Manager REST API is unreachable; the request is retryable."""


class SceneNotFoundError(Exception):
  """Unknown scene_id."""


class CameraNotFoundError(Exception):
  """Unknown camera_id, or the camera is not part of the scene."""


class CameraNotCalibratedError(Exception):
  """The camera record has no usable intrinsics or pose."""


class InvalidAssetPriorError(ValueError):
  """An object-library asset has invalid size dimensions for projection."""


class SceneMeshMissingError(Exception):
  """The scene has no GLB mesh (image-based map or no map at all)."""


def pose_mat_from_pose(translation, rotation, scale):
  """4x4 pose matrix matching scene_common CameraPose._poseToPoseMat.

  rotation: Euler XYZ in degrees (len 3) or quaternion (len 4).
  """
  rotation = list(rotation)
  if len(rotation) == 4:
    rmat = Rotation.from_quat(rotation).as_matrix()
  else:
    rmat = Rotation.from_euler("XYZ", rotation, degrees=True).as_matrix()
  tvecs = np.asarray(translation, dtype=np.float64).reshape(3, 1)
  pose_mat = np.vstack((np.hstack((rmat, tvecs)), [0.0, 0.0, 0.0, 1.0]))
  return pose_mat @ np.diag(list(_scale_xyz(scale)) + [1.0])


def _scale_xyz(scale):
  if scale is None:
    return (1.0, 1.0, 1.0)
  if isinstance(scale, (int, float)):
    value = float(scale)
    return (value, value, value) if value > 0.0 else (1.0, 1.0, 1.0)
  values = tuple(float(v) for v in scale)[:3]
  if len(values) != 3 or any(v <= 0.0 for v in values):
    return (1.0, 1.0, 1.0)
  return values


def scene_mesh_pose_mat(scene):
  """Mesh->world 4x4 from scene mesh_translation / mesh_rotation / mesh_scale.

  Uses identity components when fields are missing. Never falls back to
  Scene.scale (map pixels-per-metre), which is not a GLB scale.
  """
  translation = scene.get("mesh_translation") or [0.0, 0.0, 0.0]
  rotation = scene.get("mesh_rotation") or [0.0, 0.0, 0.0]
  return pose_mat_from_pose(translation, rotation, scene.get("mesh_scale"))


class CameraInfo:
  """Calibration of one camera: intrinsics, image size and camera->world pose."""

  def __init__(self, record):
    intrinsics = record.get("intrinsics") or {}
    translation = record.get("translation")
    rotation = record.get("rotation")
    if translation is None or rotation is None:
      raise CameraNotCalibratedError(record.get("name") or record.get("uid"))
    self.uid = record.get("uid")
    self.name = record.get("name")
    resolution = record.get("resolution")
    if resolution:
      self.width, self.height = int(resolution[0]), int(resolution[1])
    elif all(k in intrinsics for k in ("cx", "cy")):
      # Pinhole calibrations imply a centered image with no explicit resolution.
      self.width = int(float(intrinsics["cx"]) * 2)
      self.height = int(float(intrinsics["cy"]) * 2)
    else:
      raise CameraNotCalibratedError("camera resolution is required for FOV intrinsics")
    try:
      matrix = CameraIntrinsics(intrinsics, resolution=[self.width, self.height]).intrinsics
      self.intrinsics = {
        "fx": float(matrix[0, 0]), "fy": float(matrix[1, 1]),
        "cx": float(matrix[0, 2]), "cy": float(matrix[1, 2]),
      }
    except (TypeError, ValueError, IndexError, OverflowError, ZeroDivisionError) as exc:
      raise CameraNotCalibratedError("invalid camera intrinsics") from exc
    self.distortion = record.get("distortion")
    self.pose_mat = pose_mat_from_pose(translation, rotation, record.get("scale"))
    self.distortion_coefficients = self._validate_calibration()

  def _validate_calibration(self) -> np.ndarray:
    intrinsics = np.array(list(self.intrinsics.values()), dtype=np.float64)
    if not np.all(np.isfinite(intrinsics)) or min(self.intrinsics["fx"],
                                                 self.intrinsics["fy"]) <= 0:
      raise ValueError("invalid intrinsics")
    if min(self.width, self.height) <= 0 or not np.all(np.isfinite(self.pose_mat)) \
        or abs(np.linalg.det(self.pose_mat[:3, :3])) < 1e-12:
      raise ValueError("invalid resolution or pose")
    distortion = self.distortion
    if isinstance(distortion, dict):
      distortion = [distortion.get(key, 0.0) for key in DISTORTION_KEYS]
    coefficients = np.asarray(distortion if distortion is not None else np.zeros(4),
                              dtype=np.float64)
    if coefficients.ndim != 1 or len(coefficients) not in (4, 5, 8, 12, 14) \
        or not np.all(np.isfinite(coefficients)):
      raise ValueError("invalid distortion")
    return coefficients

  @property
  def k_matrix(self):
    i = self.intrinsics
    return np.array([[i["fx"], 0.0, i["cx"]],
                     [0.0, i["fy"], i["cy"]],
                     [0.0, 0.0, 1.0]], dtype=np.float64)

  def cache_key(self):
    return (
      tuple(round(self.intrinsics[k], 4) for k in ("fx", "fy", "cx", "cy")),
      self.width, self.height,
      tuple(np.round(self.pose_mat.reshape(-1), 5).tolist()),
    )


class AssetPrior:
  """Size prior and map-projection default derived from an object-library asset."""

  def __init__(self, prior, project_to_map=False):
    self.prior = prior
    self.project_to_map = project_to_map

  @classmethod
  def from_asset(cls, asset):
    category = asset.get("name") or "<unknown>"
    size_keys = ("x_size", "y_size", "z_size")
    try:
      sizes = [float(asset.get(key) or 0.0) for key in size_keys]
    except (TypeError, ValueError, OverflowError) as exc:
      raise InvalidAssetPriorError(
        f"asset category '{category}' has non-numeric size dimensions") from exc
    invalid_sizes = [key for key, size in zip(size_keys, sizes)
                     if not np.isfinite(size) or size <= 0.0]
    if invalid_sizes:
      raise InvalidAssetPriorError(
        f"asset category '{category}' has invalid size dimensions: "
        f"{', '.join(invalid_sizes)} must be finite and positive")
    prior = {
      "mu_x": sizes[0], "mu_y": sizes[1], "mu_z": sizes[2],
      "sigma_x": sizes[0] * DEFAULT_SIGMA_FRACTION,
      "sigma_y": sizes[1] * DEFAULT_SIGMA_FRACTION,
      "sigma_z": sizes[2] * DEFAULT_SIGMA_FRACTION,
    }
    return cls(prior, project_to_map=bool(asset.get("project_to_map", False)))


class SceneProvider:
  """REST-backed, event-refreshed access to configuration and prepared geometry."""

  def __init__(self, rest_url=DEFAULT_REST_URL, auth=DEFAULT_AUTH,
               rootcert=DEFAULT_ROOTCERT, media_root=DEFAULT_MEDIA_ROOT,
               num_layers=DEFAULT_NUM_LAYERS):
    self.rest_url = rest_url
    self.auth = auth
    self.rootcert = rootcert
    self.media_root = media_root
    self.num_layers = int(num_layers)
    self._rest = None
    self._lock = threading.Lock()
    self._refresh_event = threading.Event()
    self._generation = 0
    self._loaded_generation = -1
    self._pinned = False
    self._cache = {}        # (kind, key) -> value
    self._world_meshes = {} # scene_id -> (mesh_key, tensor_mesh)
    self._reasoners = {}    # (scene_id, camera_name) -> (key, reasoner)
    self._previous_world_meshes = {}
    self._previous_reasoners = {}

  @classmethod
  def from_env(cls):
    return cls(
      rest_url=os.getenv("OBSERVATION_PROCESSOR_REST_URL", DEFAULT_REST_URL),
      auth=os.getenv("OBSERVATION_PROCESSOR_AUTH", DEFAULT_AUTH),
      rootcert=os.getenv("OBSERVATION_PROCESSOR_ROOTCERT", DEFAULT_ROOTCERT),
      media_root=os.getenv("OBSERVATION_PROCESSOR_MEDIA_ROOT", DEFAULT_MEDIA_ROOT),
    )

  # ---- Cache lifecycle -----------------------------------------------------

  def snapshot(self):
    """Pin one fully warmed configuration for the duration of a request."""
    with self._lock:
      if self._loaded_generation < 0:
        raise StoreUnavailableError("configuration is not initialized")
      snapshot = SceneProvider(self.rest_url, self.auth, self.rootcert,
                               self.media_root, self.num_layers)
      snapshot._cache = self._cache
      snapshot._world_meshes = self._world_meshes
      snapshot._reasoners = self._reasoners
      snapshot._rest = self._rest
      snapshot._loaded_generation = self._loaded_generation
      snapshot._generation = self._loaded_generation
      snapshot._pinned = True
    return snapshot

  @property
  def has_snapshot(self) -> bool:
    """Whether a fully warmed configuration is available for requests."""
    with self._lock:
      return self._loaded_generation >= 0

  @property
  def needs_refresh(self) -> bool:
    """Whether startup or a database event requires a new snapshot."""
    with self._lock:
      return self._loaded_generation != self._generation

  def warm(self) -> None:
    """Build and atomically publish configuration, meshes and reasoners.

    Failed or superseded refreshes never publish a partially loaded snapshot.
    """
    with self._lock:
      generation = self._generation
      snapshot = SceneProvider(self.rest_url, self.auth, self.rootcert,
                               self.media_root, self.num_layers)
      snapshot._previous_world_meshes = self._world_meshes.copy()
      snapshot._previous_reasoners = self._reasoners.copy()
    snapshot._load_configuration()
    with self._lock:
      if generation != self._generation:
        log.info("SceneProvider: database changed during warmup; retrying next probe")
        return
      self._cache = snapshot._cache
      self._world_meshes = snapshot._world_meshes
      self._reasoners = snapshot._reasoners
      self._loaded_generation = generation

  def _load_configuration(self) -> None:
    scenes = self._call("getScenes", None)
    if scenes.statusCode != 200:
      raise StoreUnavailableError(f"scenes: HTTP {scenes.statusCode}")
    records = list(scenes.get("results", []))
    with self._lock:
      for record in records:
        self._cache[("scene", record["uid"])] = dict(record)
    for record in records:
      self._cached("cameras", record["uid"],
                   lambda uid=record["uid"]: self._fetch_cameras(uid))
    self._cached("assets", None, self._fetch_assets)
    for record in records:
      self._warm_geometry(record)
    log.info(f"SceneProvider: warmed {len(records)} scenes, "
             f"{len(self._world_meshes)} meshes and {len(self._reasoners)} reasoners")

  def _warm_geometry(self, scene: dict) -> None:
    if not self.scene_has_mesh(scene):
      return
    scene_id = scene["uid"]
    self.get_world_mesh(scene_id)
    for record in self._cache[("cameras", scene_id)]:
      try:
        self.get_reasoner(scene_id, record["uid"])
      except CameraNotCalibratedError as exc:
        log.warning(f"SceneProvider: skipping uncalibrated camera {record['uid']}: {exc}")

  def invalidate(self) -> None:
    """Schedule a full refresh, retaining the previous snapshot until it succeeds."""
    with self._lock:
      self._generation += 1
      self._refresh_event.set()

  def wait_for_refresh(self, timeout: float) -> None:
    """Wait for a database event or the next periodic readiness probe."""
    self._refresh_event.wait(timeout)
    self._refresh_event.clear()

  # ---- REST plumbing -----------------------------------------------------

  def _client(self):
    with self._lock:
      if self._rest is None:
        try:
          self._rest = RESTClient(self.rest_url, auth=self.auth,
                                  rootcert=self.rootcert)
        except (requests.exceptions.RequestException, RuntimeError, OSError,
                ValueError) as exc:
          raise StoreUnavailableError(str(exc)) from exc
      return self._rest

  def _call(self, method, *args):
    """Call a RESTClient method; connection problems drop the client."""
    client = self._client()
    try:
      return getattr(client, method)(*args)
    except requests.exceptions.RequestException as exc:
      with self._lock:
        self._rest = None
      raise StoreUnavailableError(str(exc)) from exc

  def is_ready(self):
    """True when the Manager REST API answers an authenticated request."""
    try:
      result = self._call("getScenes", {"name": "__readiness_probe__"})
    except StoreUnavailableError:
      return False
    return result.statusCode == 200

  def _cached(self, kind, key, fetch):
    with self._lock:
      cache = self._cache
      if (kind, key) in cache:
        return cache[(kind, key)]
    value = fetch()
    with self._lock:
      cache[(kind, key)] = value
    return value

  # ---- Scenes, cameras, assets --------------------------------------------

  def get_scene(self, scene_id):
    """Scene record for `scene_id`; raises SceneNotFoundError / StoreUnavailableError."""
    if self._pinned:
      with self._lock:
        scene = self._cache.get(("scene", scene_id))
      if scene is None:
        raise SceneNotFoundError(scene_id)
      return scene
    return self._cached("scene", scene_id, lambda: self._fetch_scene(scene_id))

  def _fetch_scene(self, scene_id):
    result = self._call("getScene", scene_id)
    if result.statusCode == 404:
      raise SceneNotFoundError(scene_id)
    if result.statusCode != 200:
      raise StoreUnavailableError(f"scene {scene_id}: HTTP {result.statusCode}")
    return dict(result)

  def get_camera(self, scene_id, camera_id):
    """CameraInfo for `camera_id` within `scene_id`.

    Raises CameraNotFoundError, CameraNotCalibratedError, SceneNotFoundError
    or StoreUnavailableError.
    """
    scene = self.get_scene(scene_id)
    cameras = self._cached("cameras", scene_id,
                           lambda: self._fetch_cameras(scene["uid"]))
    for record in cameras:
      if camera_id == record.get("uid"):
        try:
          return CameraInfo(record)
        except (TypeError, ValueError, IndexError, OverflowError) as exc:
          raise CameraNotCalibratedError("invalid camera calibration") from exc
    raise CameraNotFoundError(camera_id)

  def _fetch_cameras(self, scene_uid):
    result = self._call("getCameras", {"scene": scene_uid})
    if result.statusCode != 200:
      raise StoreUnavailableError(f"cameras of {scene_uid}: HTTP {result.statusCode}")
    return list(result.get("results", []))

  def get_asset_prior(self, category):
    """AssetPrior for `category`; pedestrian fallback when no asset matches."""
    assets = self._cached("assets", None, self._fetch_assets)
    asset = assets.get(category)
    if asset is None:
      return AssetPrior(dict(PEDESTRIAN_PRIOR))
    return AssetPrior.from_asset(asset)

  def _fetch_assets(self):
    result = self._call("getAssets", None)
    if result.statusCode != 200:
      raise StoreUnavailableError(f"assets: HTTP {result.statusCode}")
    return {a.get("name"): a for a in result.get("results", [])}

  # ---- Scene mesh ----------------------------------------------------------

  @staticmethod
  def scene_has_mesh(scene):
    map_url = scene.get("map") or ""
    return map_url.lower().endswith(".glb")

  def get_world_mesh(self, scene_id):
    """Scene mesh as an open3d tensor TriangleMesh in the world frame.

    Raises SceneMeshMissingError for scenes without a GLB mesh.
    """
    with self._lock:
      meshes = self._world_meshes
    scene = self.get_scene(scene_id)
    if not self.scene_has_mesh(scene):
      raise SceneMeshMissingError(scene_id)
    mesh_key = (scene["map"], tuple(np.round(
      scene_mesh_pose_mat(scene).reshape(-1), 6).tolist()))
    with self._lock:
      entry = meshes.get(scene_id)
      if entry is not None and entry[0][:2] == mesh_key:
        return entry[1]
    data = self._mesh_bytes(scene["map"])
    mesh_key += (hashlib.sha256(data).digest(),)
    previous = self._previous_world_meshes.get(scene_id)
    if previous is not None and previous[0] == mesh_key:
      mesh = previous[1]
    else:
      mesh = self._load_world_mesh(scene, data)
    with self._lock:
      meshes[scene_id] = (mesh_key, mesh)
    return mesh

  def _load_world_mesh(self, scene, data=None):
    if data is None:
      data = self._mesh_bytes(scene["map"])
    mesh = self._glb_to_tensor_mesh(data)
    mesh.transform(scene_mesh_pose_mat(scene))
    log.info("SceneProvider: loaded scene mesh", scene.get("name"),
             f"url={scene['map']}")
    return mesh

  def _mesh_bytes(self, map_url):
    """Mesh file content: shared media volume first, HTTP download fallback."""
    path = self._local_media_path(map_url)
    if path is not None:
      with open(path, "rb") as handle:
        return handle.read()
    return self._download(map_url)

  def _local_media_path(self, map_url):
    if not self.media_root or not os.path.isdir(self.media_root):
      return None
    url_path = urlsplit(urljoin(self.rest_url, map_url)).path
    marker = "/media/"
    if marker not in url_path:
      return None
    root = os.path.realpath(self.media_root)
    full = os.path.realpath(os.path.join(root, url_path.split(marker, 1)[1]))
    # Keep resolved paths inside the media root (defends against traversal).
    if not full.startswith(root + os.sep) or not os.path.isfile(full):
      return None
    return full

  def _download(self, url):
    # Manager may return media URLs relative to the server root.
    url = urljoin(self.rest_url, url)
    manager_origin = _http_origin(self.rest_url)
    if manager_origin is None or _http_origin(url) != manager_origin:
      raise StoreUnavailableError("scene mesh URL must share the Manager origin")
    client = self._client()
    reply = None
    try:
      reply = client.session.get(url, headers={"Authorization": f"Token {client.token}"},
                                 verify=client.verify_ssl, timeout=client.timeout,
                                 stream=True, allow_redirects=False)
      return _read_mesh_response(reply, url)
    except requests.exceptions.RequestException as exc:
      raise StoreUnavailableError(str(exc)) from exc
    finally:
      if reply is not None:
        reply.close()

  @staticmethod
  def _glb_to_tensor_mesh(data):
    """GLB bytes -> tensor TriangleMesh, read raw like the platform's mesh_util.

    Buffers are used as stored in the file; the Manager-provided mesh pose
    (mesh_translation / mesh_rotation / mesh_scale) owns any axis conversion.
    """
    import open3d as o3d

    with tempfile.NamedTemporaryFile(suffix=".glb") as handle:
      handle.write(data)
      handle.flush()
      legacy = o3d.io.read_triangle_mesh(handle.name)
    if legacy.is_empty():
      raise SceneMeshMissingError("scene mesh is empty or unreadable")
    return o3d.t.geometry.TriangleMesh.from_legacy(legacy)

  # ---- Amodal reasoners -----------------------------------------------------

  def get_reasoner(self, scene_id, camera_id):
    """Cached AmodalReasoner for (scene, camera); rebuilt when inputs change."""
    from observation_conditioning import AmodalReasoner

    with self._lock:
      reasoners = self._reasoners
    camera = self.get_camera(scene_id, camera_id)
    mesh = self.get_world_mesh(scene_id)
    key = (camera.cache_key(), id(mesh), self.num_layers)
    cache_id = (scene_id, camera_id)
    with self._lock:
      entry = reasoners.get(cache_id)
      if entry is not None and entry[0] == key:
        return entry[1]
    previous = self._previous_reasoners.get(cache_id)
    if previous is not None and previous[0] == key:
      reasoner = previous[1]
    else:
      reasoner = AmodalReasoner(
        mesh=mesh,
        rwc_z_up=np.asarray(DEFAULT_WORLD_UP, dtype=np.float64),
        camera_intrinsics=camera.k_matrix,
        camera_extrinsics=camera.pose_mat,
        width=camera.width,
        height=camera.height,
        num_layers=self.num_layers,
      )
      log.info("SceneProvider: built AmodalReasoner", scene_id, camera_id,
               f"{camera.width}x{camera.height}")
    with self._lock:
      reasoners[cache_id] = (key, reasoner)
    return reasoner
