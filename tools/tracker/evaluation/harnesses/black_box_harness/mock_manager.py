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
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import numpy as np
import cv2
from scipy.spatial.transform import Rotation

_MOCK_TOKEN = "mock"


def _compute_extrinsics(cam_pts, map_pts, fx, fy, cx, cy):
    """Compute camera extrinsics (translation, rotation, scale) from point correspondences.

    Uses cv2.solvePnP to solve the world-to-camera transform, then inverts it
    to get the camera-to-world pose, matching PointCorrespondenceTransform in
    scene_common/src/scene_common/transform.py.

    Returns:
        dict with keys ``translation`` ([x, y, z]), ``rotation`` (Euler XYZ degrees),
        ``scale`` ([1.0, 1.0, 1.0]), or None if solvePnP fails.
    """
    try:
        cam_arr = np.array(cam_pts, dtype="float32")
        map_arr = np.array(map_pts, dtype="float32")
        if map_arr.shape[1] == 2:
            map_arr = np.hstack((map_arr, np.zeros((map_arr.shape[0], 1), dtype="float32")))
        K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype="float64")
        ok, rvec, tvec = cv2.solvePnP(map_arr, cam_arr, K, None)
        if not ok:
            return None
        rmat = cv2.Rodrigues(rvec)[0]
        # Invert world-to-camera → camera-to-world pose matrix
        pose_mat = np.linalg.inv(np.vstack((np.hstack((rmat, tvec)), [0, 0, 0, 1])))
        # Extract translation
        translation = pose_mat[0:3, 3].tolist()
        # Extract scale from column norms of the rotation sub-matrix
        r_cols = pose_mat[0:3, 0:3]
        scale = [float(np.linalg.norm(r_cols[:, i])) for i in range(3)]
        # Normalise rotation matrix before extracting Euler angles
        r_norm = r_cols / np.array(scale)
        euler_deg = Rotation.from_matrix(r_norm).as_euler('XYZ', degrees=True).tolist()
        return {"translation": translation, "rotation": euler_deg, "scale": scale}
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
        fx, fy, cx, cy = info["intrinsics"]
        extrinsics = _compute_extrinsics(
            info.get("camera points", []),
            info.get("map points", []),
            fx, fy, cx, cy,
        )
        if extrinsics is None:
            extrinsics = {"translation": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]}
        cameras.append({
            "uid": cam_name,
            "name": cam_name,
            "scene": scene_uid,
            "intrinsics": {"fx": fx, "fy": fy, "cx": cx, "cy": cy},
            "distortion": {"k1": 0.0, "k2": 0.0, "p1": 0.0, "p2": 0.0, "k3": 0.0},
            "resolution": [int(info["width"]), int(info["height"])],
            "camera points": info.get("camera points", []),
            "map points": info.get("map points", []),
            "extrinsics": extrinsics,
        })

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
            # Controller calls updateCamera to write back calibration results.
            # Accept and echo back the camera dict (no persistence needed).
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
