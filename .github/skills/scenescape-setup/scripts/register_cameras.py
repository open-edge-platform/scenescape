# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Register cameras from a pre-calibrated camera.json against a SceneScape scene via REST.

Generalizes the ad hoc registration used in references/scene-map-alternatives.md: auto-detects
the per-camera identifier key (sensor_id/uid/name/id), auto-detects euler vs quaternion rotation,
accepts explicit --camera-map overrides when the JSON's identifiers don't match deployed
camera_ids, cleans up orphaned (scene=None) cameras with a colliding name before creating, and is
safe to re-run: a camera already registered to --scene-uid is updated in place instead of
re-created.
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter

# Keys tried in order to find a camera's identifier inside one entry of the camera.json.
IDENTIFIER_KEYS = ("sensor_id", "uid", "name", "id")


class _CAOnlyAdapter(HTTPAdapter):
  """Verify the server certificate's chain against our own CA bundle, but skip hostname
  matching: this script reaches the manager via https://<base-url-host> (e.g. the docker-published
  'localhost'), while the deployment cert's only SAN is web.scenescape.intel.com. The CA is
  deployment-local and pinned from disk, so chain trust still defeats a MITM without requiring
  a hostname match."""

  def __init__(self, ca_cert: str, *args, **kwargs):
    self._ca_cert = ca_cert
    super().__init__(*args, **kwargs)

  def init_poolmanager(self, *args, **kwargs):
    context = ssl.create_default_context(cafile=self._ca_cert)
    context.check_hostname = False
    kwargs["ssl_context"] = context
    # urllib3 also does its own post-handshake hostname match independent of
    # ssl_context.check_hostname; disable that too or it re-raises the same mismatch.
    kwargs["assert_hostname"] = False
    return super().init_poolmanager(*args, **kwargs)


def load_cameras(camera_json_path: Path) -> list[dict[str, Any]]:
  data = json.loads(camera_json_path.read_text(encoding="utf-8"))
  if isinstance(data, dict):
    cameras = data.get("cameras")
    if cameras is None:
      raise ValueError(
        f"{camera_json_path}: expected a top-level 'cameras' list or a JSON list, got a dict "
        "with no 'cameras' key"
      )
  elif isinstance(data, list):
    cameras = data
  else:
    raise ValueError(f"{camera_json_path}: expected a JSON list or dict, got {type(data)}")
  if not cameras:
    raise ValueError(f"{camera_json_path}: no cameras found")
  return cameras


def camera_identifier(cam: dict[str, Any]) -> str:
  for key in IDENTIFIER_KEYS:
    value = cam.get(key)
    if value:
      return value
  raise ValueError(f"camera entry has none of {IDENTIFIER_KEYS}: {cam}")


def parse_camera_map(pairs: list[str] | None) -> dict[str, str]:
  """--camera-map entries look like 'json_identifier=camera_id'."""
  mapping: dict[str, str] = {}
  for pair in pairs or []:
    if "=" not in pair:
      raise ValueError(f"--camera-map entry must be 'identifier=camera_id', got: {pair}")
    identifier, camera_id = pair.split("=", 1)
    mapping[identifier.strip()] = camera_id.strip()
  return mapping


def resolve_camera_id(identifier: str, camera_map: dict[str, str], known_camera_ids: list[str] | None) -> str | None:
  """Explicit --camera-map wins; otherwise fall back to an exact/case-insensitive match
  against the deployed camera_ids (when supplied). Never guesses a fuzzy match."""
  if identifier in camera_map:
    return camera_map[identifier]
  if known_camera_ids is None:
    return identifier
  if identifier in known_camera_ids:
    return identifier
  lowered = {cid.lower(): cid for cid in known_camera_ids}
  return lowered.get(identifier.lower())


def transform_fields(cam: dict[str, Any]) -> tuple[str, list[float]]:
  """Return (transform_type, rotation), auto-detecting quaternion input by rotation length
  when transform_type is absent or ambiguous. The manager REST API itself converts
  quaternion -> euler server-side (see CamSerializer.map_transform_fields), so the raw
  quaternion values are passed through unchanged rather than converted here."""
  rotation = cam.get("rotation")
  if rotation is None:
    raise ValueError(f"camera {camera_identifier(cam)}: missing 'rotation'")

  transform_type = cam.get("transform_type")
  if transform_type not in ("euler", "quaternion"):
    transform_type = "quaternion" if len(rotation) == 4 else "euler"

  return transform_type, rotation


def resolution_payload(cam: dict[str, Any]) -> dict[str, int] | None:
  resolution = cam.get("resolution")
  if resolution is None:
    return None
  if isinstance(resolution, dict):
    return {"width": resolution["width"], "height": resolution["height"]}
  if isinstance(resolution, (list, tuple)) and len(resolution) == 2:
    return {"width": resolution[0], "height": resolution[1]}
  raise ValueError(f"unrecognized resolution format: {resolution!r}")


def manager_session(base_url: str, ca_cert: Path, supass_path: Path) -> requests.Session:
  """Authenticated requests.Session verifying TLS against the deployment's own CA bundle
  (never disables verification: that would let a MITM on the auth request capture the
  admin password)."""
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


def get_existing_camera(session: requests.Session, base_url: str, camera_id: str) -> dict[str, Any] | None:
  resp = session.get(f"{base_url}/api/v1/camera/{camera_id}", timeout=30)
  if resp.status_code != 200:
    return None
  return resp.json()


def delete_orphaned(session: requests.Session, base_url: str, camera_id: str, existing: dict[str, Any] | None) -> None:
  """Best-effort cleanup: an existing camera with this name but scene=None blocks creation
  with 'orphaned camera with the name ... already exists' (see repo memory notes)."""
  if existing is None or existing.get("scene") is not None:
    return
  session.delete(f"{base_url}/api/v1/camera/{camera_id}", timeout=30)
  print(f"Deleted orphaned camera: {camera_id}")


def register_cameras(
  session: requests.Session,
  base_url: str,
  scene_uid: str,
  cameras: list[dict[str, Any]],
  camera_map: dict[str, str],
  known_camera_ids: list[str] | None,
) -> int:
  failures = 0
  unresolved: list[str] = []

  for cam in cameras:
    identifier = camera_identifier(cam)
    camera_id = resolve_camera_id(identifier, camera_map, known_camera_ids)
    if camera_id is None:
      unresolved.append(identifier)
      continue

    transform_type, rotation = transform_fields(cam)
    payload: dict[str, Any] = {
      "name": camera_id,
      "sensor_id": camera_id,
      "scene": scene_uid,
      "transform_type": transform_type,
      "translation": cam["translation"],
      "rotation": rotation,
      "scale": cam.get("scale", [1.0, 1.0, 1.0]),
      "intrinsics": cam["intrinsics"],
    }
    resolution = resolution_payload(cam)
    if resolution:
      payload["resolution"] = resolution

    existing = get_existing_camera(session, base_url, camera_id)
    delete_orphaned(session, base_url, camera_id, existing)

    if existing is not None and existing.get("scene") not in (None, scene_uid):
      print(f"SKIP {camera_id} (from {identifier}): already registered to a different scene "
            f"({existing['scene']})", file=sys.stderr)
      failures += 1
      continue

    if existing is not None and existing.get("scene") == scene_uid:
      # Retry-safe: update the camera already registered to this scene instead of
      # re-POSTing a create, which CamSerializer.validate_name() would reject as a duplicate.
      resp = session.post(f"{base_url}/api/v1/camera/{camera_id}", json=payload, timeout=60)
      action = "Updated"
    else:
      resp = session.post(f"{base_url}/api/v1/camera", json=payload, timeout=60)
      action = "Registered"

    print(f"{action} {camera_id} (from {identifier}): {resp.status_code}")
    if resp.status_code >= 400:
      print("  ", resp.text[:500])
      failures += 1

  if unresolved:
    print(
      "\nERROR: could not resolve these camera.json identifiers to a known camera_id: "
      f"{unresolved}\nPass --camera-map 'identifier=camera_id' for each, e.g.:\n"
      + "\n".join(f"  --camera-map '{ident}=<camera_id>'" for ident in unresolved),
      file=sys.stderr,
    )
    failures += len(unresolved)

  return failures


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
    "--deploy-dir", required=True, type=Path,
    help="For secrets/supass and secrets/certs/scenescape-ca.pem",
  )
  parser.add_argument("--scene-uid", required=True)
  parser.add_argument("--camera-json", required=True, type=Path)
  parser.add_argument(
    "--camera-ids", nargs="*", default=None,
    help="Deployed camera_ids to match camera.json identifiers against (default: no validation)",
  )
  parser.add_argument(
    "--camera-map", nargs="*", default=None, metavar="IDENTIFIER=CAMERA_ID",
    help="Explicit overrides when camera.json identifiers don't match camera_ids",
  )
  parser.add_argument("--base-url", default="https://localhost")
  args = parser.parse_args()

  supass_path = args.deploy_dir / "secrets" / "supass"
  if not supass_path.is_file():
    print(f"ERROR: {supass_path} not found", file=sys.stderr)
    sys.exit(2)

  ca_cert = args.deploy_dir / "secrets" / "certs" / "scenescape-ca.pem"
  cameras = load_cameras(args.camera_json)
  camera_map = parse_camera_map(args.camera_map)
  session = manager_session(args.base_url, ca_cert, supass_path)

  failures = register_cameras(
    session, args.base_url, args.scene_uid, cameras, camera_map, args.camera_ids,
  )
  sys.exit(1 if failures else 0)


if __name__ == "__main__":
  main()
