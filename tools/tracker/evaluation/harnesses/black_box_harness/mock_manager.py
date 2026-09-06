# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Minimal Manager REST API mock server.

Serves the two endpoints that both Controller and Tracker Service call
to load scene configuration, matching production behaviour exactly:

 POST /api/v1/auth              → {"token": "mock"}
 GET  /api/v1/scenes            → {"results": [<scene>]}
 GET  /api/v1/scenes/child      → {"results": []}
 GET  /api/v1/assets            → {"results": []}
 GET  /api/v1/camera/<uid>      → <camera>
 POST /api/v1/camera/<uid>      → <camera>   (accepts updateCamera, no-ops)

Scene format follows the Manager REST serializer (CamSerializer):
 cameras carry ``camera points`` / ``map points`` so Camera.__init__
 constructs a PointCorrespondenceTransform, identical to production.

Run as a standalone process inside the Docker network:
 python mock_manager.py <port> <scene_config_json>

<scene_config_json>: JSON string of the dataset scene config
                     (output of dataset.get_scene_config()).
"""

import json
import math
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import numpy as np
import cv2
from scipy.spatial.transform import Rotation

_MOCK_TOKEN = "mock"

# Distortion key order matches CameraIntrinsics.DISTORTION_KEYS in
# scene_common/src/scene_common/transform.py.
_DISTORTION_KEYS = (
  'k1', 'k2', 'p1', 'p2', 'k3', 'k4', 'k5', 'k6',
  's1', 's2', 's3', 's4', 'taux', 'tauy',
)

_MAX_COPLANAR_DETERMINANT = 0.1


def _intrinsics_to_list(intrinsics):
  """Normalize intrinsics (``[fx, fy, cx, cy]`` list or ``{fx,fy,cx,cy}`` dict).

  Returns a 4-element ``[fx, fy, cx, cy]`` list.
  """
  if isinstance(intrinsics, dict):
    values = [intrinsics.get(k) for k in ("fx", "fy", "cx", "cy")]
  else:
    values = list(intrinsics)

  if len(values) != 4 or any(v is None for v in values):
    raise ValueError(f"Invalid intrinsics (expected [fx, fy, cx, cy]): {intrinsics!r}")

  return [float(v) for v in values]


def _distortion_to_array(distortion):
  """Convert distortion (list, dict, or None) to a 14-element float64 array.

  Mirrors CameraIntrinsics._setDistortion() in
  scene_common/src/scene_common/transform.py.
  """
  if distortion is None:
    return np.zeros(14, dtype=np.float64)
  if isinstance(distortion, dict):
    distortion = [distortion.get(k, 0.0) for k in _DISTORTION_KEYS]
  arr = np.array(distortion, dtype=np.float64)
  return np.pad(arr, (0, 14 - len(arr)))


def _calculate_determinant(points):
  """Mirrors PointCorrespondenceTransform.calculateDeterminant."""
  p1, p2, p3, p4 = points
  v1 = np.array([p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]])
  v2 = np.array([p3[0] - p1[0], p3[1] - p1[1], p3[2] - p1[2]])
  v3 = np.array([p4[0] - p1[0], p4[1] - p1[1], p4[2] - p1[2]])
  return np.linalg.det(np.array([v1, v2, v3]))


def _are_coplanar(points):
  """Mirrors PointCorrespondenceTransform.arePointsCoplanar."""
  if len(points) == 5:
    for i in range(len(points)):
      subset = [points[j] for j in range(len(points)) if j != i]
      if abs(_calculate_determinant(subset)) > _MAX_COPLANAR_DETERMINANT:
        return False
  elif len(points) == 4:
    if abs(_calculate_determinant(points)) > _MAX_COPLANAR_DETERMINANT:
      return False
  return True


def _pose_mat_to_extrinsics(mat):
  """Extract JSON-serializable extrinsics from a 4×4 camera-to-world pose matrix.

  Mirrors CameraPose._poseMatToPose() in
  scene_common/src/scene_common/transform.py.
  """
  rmat = mat[0:3, 0:3]
  translation = mat[0:3, 3].tolist()
  euler_deg = Rotation.from_matrix(rmat).as_euler('XYZ', degrees=True).tolist()
  scale = [
    float(mat[3, 3] * math.sqrt(rmat[0, 0]**2 + rmat[1, 0]**2 + rmat[2, 0]**2)),
    float(mat[3, 3] * math.sqrt(rmat[0, 1]**2 + rmat[1, 1]**2 + rmat[2, 1]**2)),
    float(mat[3, 3] * math.sqrt(rmat[0, 2]**2 + rmat[1, 2]**2 + rmat[2, 2]**2)),
  ]
  return {"translation": translation, "rotation": euler_deg, "scale": scale}


def _compute_extrinsics(cam_pts, map_pts, intrinsics, distortion=None):
  """Compute camera extrinsics from 2-D/3-D point correspondences.

  Exactly mirrors PointCorrespondenceTransform._calculatePoseMat() in
  scene_common/src/scene_common/transform.py, including:
  - distortion coefficients via CameraIntrinsics._setDistortion logic
  - coplanarity check selecting SOLVEPNP_P3P vs SOLVEPNP_ITERATIVE
  - pose extraction via _poseMatToPose

  Args:
    cam_pts:     list of [u, v] image points.
    map_pts:     list of [x, y] or [x, y, z] world points.
    intrinsics:  [fx, fy, cx, cy] camera intrinsics.
    distortion:  distortion as list, dict (DISTORTION_KEYS), or None.

  Returns:
    dict with 'translation', 'rotation' (Euler XYZ degrees), 'scale', or None.
  """
  try:
    cam_arr = np.array(cam_pts, dtype="float32")
    map_arr = np.array(map_pts, dtype="float32")
    if map_arr.shape[1] == 2:
      map_arr = np.hstack((map_arr, np.zeros((map_arr.shape[0], 1))))

    fx, fy, cx, cy = intrinsics
    K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype="float64")
    dist = _distortion_to_array(distortion)

    computation_method = cv2.SOLVEPNP_ITERATIVE
    if not _are_coplanar(map_arr.tolist()) and len(map_arr) < 6:
      computation_method = cv2.SOLVEPNP_P3P

    ok, rvec, tvec = cv2.solvePnP(map_arr, cam_arr, K, dist,
                   flags=computation_method)
    if not ok:
      return None

    rmat = cv2.Rodrigues(rvec)[0]
    pose_mat = np.linalg.inv(np.vstack((np.hstack((rmat, tvec)), [0, 0, 0, 1])))
    return _pose_mat_to_extrinsics(pose_mat)
  except Exception:
    return None


def _build_rest_scene(scene_config: dict) -> dict:
  """Convert dataset scene config to Manager REST /api/v1/scenes format.

  The scene dict embedded in ``{"results": [...]}`` must satisfy:
  - ``uid``, ``name``
  - ``cameras`` list, each camera dict with ``uid``, ``name``,
   ``resolution``, ``intrinsics`` (dict), ``distortion`` (dict),
   and calibration data in the format Camera.__init__ accepts:
   ``camera points`` + ``map points``.

  Cameras also include ``extrinsics`` (translation/rotation/scale) computed
  from the point correspondences so the Tracker Service can load the scene
  without re-running calibration.

  This is exactly what the Manager serializes from its database.
  """
  scene_uid = scene_config.get("uid") or scene_config["name"]

  cameras = []
  for cam_name, info in scene_config.get("sensors", {}).items():
    fx, fy, cx, cy = _intrinsics_to_list(info["intrinsics"])
    dist_raw = info.get("distortion")

    # Prefer explicit extrinsics (canonical camera->world pose) when the dataset
    # provides them; otherwise derive them from point correspondences via
    # solvePnP, exactly as the production Manager does.
    explicit_extrinsics = info.get("extrinsics")
    if explicit_extrinsics is not None:
      extrinsics = explicit_extrinsics
      cam_points: list = []
      map_points: list = []
    else:
      cam_points = info.get("camera points", [])
      map_points = info.get("map points", [])
      extrinsics = _compute_extrinsics(cam_points, map_points, [fx, fy, cx, cy], dist_raw)
      if extrinsics is None:
        extrinsics = {"translation": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]}

    dist_dict = dict(zip(_DISTORTION_KEYS, _distortion_to_array(dist_raw).tolist()))
    camera = {
      "uid": cam_name,
      "name": cam_name,
      "scene": scene_uid,
      "intrinsics": {"fx": fx, "fy": fy, "cx": cx, "cy": cy},
      "distortion": dist_dict,
      "resolution": [int(info["width"]), int(info["height"])],
      "extrinsics": extrinsics,
    }
    if cam_points and map_points:
      # Point-correspondence datasets: keep the legacy keys for the Python
      # controller's Camera.__init__ (PointCorrespondenceTransform).
      camera["camera points"] = cam_points
      camera["map points"] = map_points
    else:
      # Explicit-extrinsics datasets: expose the flat pose keys the Python
      # controller's Camera.__init__ accepts, matching the production Manager.
      camera["translation"] = extrinsics["translation"]
      camera["rotation"] = extrinsics["rotation"]
      camera["scale"] = extrinsics["scale"]
    cameras.append(camera)

  return {
    "uid": scene_uid,
    "name": scene_config["name"],
    "scale": scene_config.get("scale"),
    "map": scene_config.get("map"),
    "cameras": cameras,
    "sensors": [],
    "regions": [],
    "use_tracker": True,
    "regulated_rate": scene_config.get("regulated_rate", 30.0),
    "external_update_rate": scene_config.get("external_update_rate", 30.0),
  }


class MockManagerHandler(BaseHTTPRequestHandler):
  """HTTP request handler for the mock Manager REST API."""

  def log_message(self, fmt, *args):  # suppress default access log
    pass

  def _send_json(self, status: int, body: dict) -> None:
    data = json.dumps(body).encode()
    self.send_response(status)
    self.send_header("Content-Type", "application/json")
    self.send_header("Content-Length", str(len(data)))
    self.end_headers()
    self.wfile.write(data)

  def _read_body(self) -> bytes:
    length = int(self.headers.get("Content-Length", 0))
    return self.rfile.read(length) if length else b""

  # ------------------------------------------------------------------

  def do_POST(self):
    path = urlparse(self.path).path.rstrip("/")

    if path == "/api/v1/auth":
      # Both Controller (form-data) and Tracker Service call this.
      self._send_json(200, {"token": _MOCK_TOKEN})
      return

    if path.startswith("/api/v1/camera/"):
      uid = path.removeprefix("/api/v1/camera/")
      cameras = self.server.scene.get("cameras", [])
      cam = next((c for c in cameras if c["uid"] == uid), {"uid": uid})
      try:
        payload = json.loads(self._read_body())
        cam = {**cam, **payload}
      except Exception:
        pass
      self._send_json(200, cam)
      return

    self._send_json(404, {"error": "not found"})

  def do_GET(self):
    parsed = urlparse(self.path)
    path = parsed.path.rstrip("/")

    if path == "/api/v1/scenes":
      self._send_json(200, {"results": [self.server.scene]})
      return

    if path == "/api/v1/scenes/child":
      self._send_json(200, {"results": []})
      return

    if path == "/api/v1/assets":
      self._send_json(200, {"results": []})
      return

    if path.startswith("/api/v1/camera/"):
      uid = path.removeprefix("/api/v1/camera/")
      cameras = self.server.scene.get("cameras", [])
      cam = next((c for c in cameras if c["uid"] == uid), None)
      if cam:
        self._send_json(200, cam)
      else:
        self._send_json(404, {"error": f"camera {uid} not found"})
      return

    self._send_json(404, {"error": "not found"})

def run(port: int, scene_config: dict) -> None:
  """Start the mock server; blocks until interrupted."""
  scene = _build_rest_scene(scene_config)
  server = HTTPServer(("0.0.0.0", port), MockManagerHandler)
  server.scene = scene
  print(f"[MockManager] Listening on 0.0.0.0:{port}  scene={scene['uid']}", flush=True)
  server.serve_forever()

if __name__ == "__main__":
  if len(sys.argv) != 3:
    print("Usage: mock_manager.py <port> <scene_config_json>", file=sys.stderr)
    sys.exit(1)
  run(int(sys.argv[1]), json.loads(sys.argv[2]))
