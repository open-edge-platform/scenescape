# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Create a SceneScape scene from a pre-made map file (blueprint image or .glb/.ply mesh).

Automates the manual REST steps documented in references/scene-map-alternatives.md for the
`mapping=glb`/`blueprint` deployment paths (`.glb`/`.ply` meshes auto-compute `scale`; a 2D
blueprint image needs pixels-per-meter passed via --scale). Retry-safe: if a scene with
--scene-name already exists and its stored map's original filename matches --map-file's, its
uid is reused instead of creating a duplicate. If the name matches but the map's filename
differs, this refuses to silently register cameras against a stale scene -- pick a new
--scene-name instead. (A byte-content comparison isn't possible: the manager re-encodes/
re-exports every uploaded .glb, so the stored file never matches the upload byte-for-byte.)
"""

from __future__ import annotations

import argparse
import ssl
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter


class _CAOnlyAdapter(HTTPAdapter):
  """Verify the server certificate's chain against our own CA bundle. This script reaches the
  manager via https://<base-url-host> (e.g. the docker-published 'localhost'), while the
  deployment cert's only SAN is web.scenescape.intel.com, so the hostname actually dialed can't
  be used for the match; assert against the cert's real SAN instead of disabling verification
  (which would accept any CA-signed certificate for any host)."""

  EXPECTED_HOSTNAME = "web.scenescape.intel.com"

  def __init__(self, ca_cert: str, *args, **kwargs):
    self._ca_cert = ca_cert
    super().__init__(*args, **kwargs)

  def init_poolmanager(self, *args, **kwargs):
    context = ssl.create_default_context(cafile=self._ca_cert)
    kwargs["ssl_context"] = context
    kwargs["assert_hostname"] = self.EXPECTED_HOSTNAME
    return super().init_poolmanager(*args, **kwargs)


def manager_session(base_url: str, ca_cert: Path, supass_path: Path) -> requests.Session:
  """Authenticated requests.Session verifying TLS against the deployment's own CA bundle."""
  if not base_url.lower().startswith("https://"):
    # _CAOnlyAdapter is only mounted on "https://"; an http:// base_url would silently fall
    # back to requests' default unencrypted, unverified transport for the admin password.
    raise ValueError(f"base_url must use https://, got: {base_url!r}")
  if not ca_cert.is_file():
    raise FileNotFoundError(f"CA cert not found: {ca_cert}")

  session = requests.Session()
  session.mount("https://", _CAOnlyAdapter(str(ca_cert)))

  supass = supass_path.read_text(encoding="utf-8").strip()
  resp = session.post(
    f"{base_url}/api/v1/auth",
    json={"username": "admin", "password": supass},
    timeout=30,
  )
  resp.raise_for_status()
  session.headers.update({"Authorization": f"Token {resp.json()['token']}"})
  return session


def find_scene_by_name(session: requests.Session, base_url: str, scene_name: str) -> dict | None:
  resp = session.get(f"{base_url}/api/v1/scenes", params={"name": scene_name}, timeout=30)
  resp.raise_for_status()
  results = resp.json().get("results", resp.json()) if isinstance(resp.json(), dict) else resp.json()
  for scene in results:
    if scene.get("name") == scene_name:
      return scene
  return None


_DEDUP_SUFFIX_LEN = 7  # Django Storage.get_alternative_name()'s random suffix length


def original_map_stem(stored_map_url: str) -> str:
  """Best-effort recovery of the originally-uploaded filename (without extension) from the
  manager's stored /media/ URL. Django's storage only appends a random suffix
  ("_<7 chars>") to the stem when a same-named file already exists in storage; strip it if
  present so a same-name re-upload still compares equal."""
  stem = Path(urlparse(stored_map_url).path).stem
  suffix = stem[-(_DEDUP_SUFFIX_LEN + 1):]
  if len(suffix) == _DEDUP_SUFFIX_LEN + 1 and suffix[0] == "_" and suffix[1:].isalnum():
    stem = stem[: -(_DEDUP_SUFFIX_LEN + 1)]
  return stem


def create_scene(
  session: requests.Session,
  base_url: str,
  scene_name: str,
  map_file: Path,
  scale: str,
  camera_calibration: str,
) -> str:
  with map_file.open("rb") as f:
    resp = session.post(
      f"{base_url}/api/v1/scene",
      data={
        "name": scene_name,
        "scale": scale,
        "map_type": "map_upload",
        "camera_calibration": camera_calibration,
      },
      files={"map": (map_file.name, f)},
      # GLB upload triggers synchronous Open3D mesh alignment + thumbnail rendering
      # (Scene.autoAlignSceneMap()/saveThumbnail()), which can take a couple of minutes on
      # a headless/software-rendered EGL setup.
      timeout=300,
    )
  resp.raise_for_status()
  return resp.json()["uid"]


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--deploy-dir", required=True, type=Path)
  parser.add_argument("--scene-name", required=True)
  parser.add_argument("--map-file", required=True, type=Path)
  parser.add_argument(
    "--scale", default="1",
    help="Pixels per meter (blueprint images only; .glb/.ply meshes auto-compute and overwrite this)",
  )
  parser.add_argument(
    "--camera-calibration", default="Manual", choices=("Manual", "Markerless"),
    help="'Markerless' only applies to a Polycam .zip scan",
  )
  parser.add_argument("--base-url", default="https://localhost")
  args = parser.parse_args()

  if not args.map_file.is_file():
    print(f"ERROR: map file not found: {args.map_file}", file=sys.stderr)
    sys.exit(2)

  supass_path = args.deploy_dir / "secrets" / "supass"
  if not supass_path.is_file():
    print(f"ERROR: {supass_path} not found", file=sys.stderr)
    sys.exit(2)

  ca_cert = args.deploy_dir / "secrets" / "certs" / "scenescape-ca.pem"
  session = manager_session(args.base_url, ca_cert, supass_path)

  existing = find_scene_by_name(session, args.base_url, args.scene_name)
  if existing is None:
    scene_uid = create_scene(
      session, args.base_url, args.scene_name, args.map_file, args.scale, args.camera_calibration,
    )
    print(f"Created scene '{args.scene_name}'")
  else:
    scene_uid = existing["uid"]
    existing_map_url = existing.get("map")
    existing_stem = original_map_stem(existing_map_url) if existing_map_url else None
    if existing_stem != args.map_file.stem:
      print(
        f"ERROR: scene '{args.scene_name}' (uid={scene_uid}) already exists with a different "
        f"map ({existing_map_url!r}) than {args.map_file}. Refusing to silently reuse a stale "
        "scene and register cameras against the wrong map -- use a different --scene-name, or "
        "delete/replace the existing scene's map first.",
        file=sys.stderr,
      )
      sys.exit(2)
    print(f"Reusing existing scene '{args.scene_name}' (map matches)")

  print(f"Done. Scene UID: {scene_uid}")


if __name__ == "__main__":
  main()
