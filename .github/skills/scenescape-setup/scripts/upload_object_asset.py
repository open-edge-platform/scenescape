# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Create or update an Object Library entry (Asset3D) via the SceneScape manager REST API. Object
Library entries improve tracking accuracy by giving the tracker expected size/shape for a detected
object class, and optionally a custom 3D model instead of the default cuboid.

Usage:
    python upload_object_asset.py \
        --deploy-dir ~/scenescape-deployment \
        --name forklift \
        --x-size 1.2 --y-size 2.4 --z-size 2.0

    # With a custom .glb shape:
    python upload_object_asset.py \
        --deploy-dir ~/scenescape-deployment \
        --name forklift \
        --x-size 1.2 --y-size 2.4 --z-size 2.0 \
        --model-3d ~/models/forklift.glb

    # Update an existing entry by name (only the given fields are changed):
    python upload_object_asset.py \
        --deploy-dir ~/scenescape-deployment \
        --name forklift --update \
        --z-size 2.2

    # Update an existing entry by UID directly:
    python upload_object_asset.py \
        --deploy-dir ~/scenescape-deployment \
        --uid 3f9c1e2a-... \
        --mark-color "#ff0000"

The script exits 0 on success and prints the created/updated asset's UID.
"""

import argparse
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def manager_session(manager_url: str, verify_tls: bool | str, username: str, password: str) -> requests.Session:
  """Create a requests Session authenticated to the manager via token auth."""
  session = requests.Session()
  session.verify = verify_tls

  resp = session.post(
    f"{manager_url}/api/v1/auth",
    json={"username": username, "password": password},
    timeout=10,
  )
  resp.raise_for_status()
  token = resp.json()["token"]
  session.headers.update({"Authorization": f"Token {token}"})
  return session


def find_asset_uid_by_name(session: requests.Session, manager_url: str, name: str) -> str | None:
  """Look up an existing Object Library entry's UID by exact name match, or None if not found."""
  resp = session.get(f"{manager_url}/api/v1/assets", params={"name": name}, timeout=10)
  resp.raise_for_status()
  for asset in resp.json().get("results", []):
    if asset.get("name") == name:
      return asset["uid"]
  return None


def submit_asset(
  session: requests.Session,
  manager_url: str,
  uid: str | None,
  data: dict,
  model_3d: Path | None,
) -> dict:
  """POST (create, when uid is None) or PUT (update, when uid is given) an Asset3D entry.

  The manager treats PUT /asset/{uid} as a partial update (only the fields present in `data` are
  changed), so callers should omit fields they don't want to touch when updating.
  """
  if uid is None:
    url = f"{manager_url}/api/v1/asset"
    send = session.post
  else:
    url = f"{manager_url}/api/v1/asset/{uid}"
    send = session.put

  if model_3d is not None:
    if not model_3d.exists():
      raise FileNotFoundError(f"Missing 3D model file: {model_3d}")
    with open(model_3d, "rb") as model_handle:
      resp = send(
        url,
        data=data,
        files={"model_3d": (model_3d.name, model_handle, "model/gltf-binary")},
        timeout=30,
      )
  else:
    resp = send(url, data=data, timeout=10)

  resp.raise_for_status()
  return resp.json()


def main() -> None:
  parser = argparse.ArgumentParser(description="Create or update an Object Library (Asset3D) entry via the SceneScape manager")
  parser.add_argument("--deploy-dir", required=True, type=Path)
  parser.add_argument("--name", required=True, help="Object class name (must match the detected object type, e.g. 'person', 'vehicle')")
  parser.add_argument("--uid", default=None, help="Update the existing asset with this UID instead of creating a new one")
  parser.add_argument("--update", action="store_true", help="Update the existing asset matching --name instead of creating a new one (errors if no such asset exists)")
  parser.add_argument("--x-size", type=float, default=None, help="Size in meters along the x-axis (default 1.0 for new assets; omit to leave unchanged on update)")
  parser.add_argument("--y-size", type=float, default=None, help="Size in meters along the y-axis (default 1.0 for new assets; omit to leave unchanged on update)")
  parser.add_argument("--z-size", type=float, default=None, help="Size in meters along the z-axis (default 1.0 for new assets; omit to leave unchanged on update)")
  parser.add_argument("--mark-color", default=None, help="Hex color for the object's default marker (default #888888 for new assets; omit to leave unchanged on update)")
  parser.add_argument("--model-3d", type=Path, default=None, help="Optional .glb file to use instead of the default cuboid shape")
  parser.add_argument("--mass", type=float, default=None, help="Optional mass in kg (default server-side value is 1.0; omit to leave unchanged on update)")
  parser.add_argument("--is-static", action=argparse.BooleanOptionalAction, default=None, help="Mark the object class as unable (--is-static) or able (--no-is-static) to move on its own")
  parser.add_argument("--manager-url", default="https://localhost")
  parser.add_argument("--verify-tls", action="store_true", help="Verify TLS using <deploy-dir>/secrets/certs/scenescape-ca.pem")
  args = parser.parse_args()

  if args.uid and args.update:
    parser.error("--uid and --update are mutually exclusive; use --uid to target a known UID directly, or --update to look one up by --name")

  deploy_dir: Path = args.deploy_dir
  ca_cert = deploy_dir / "secrets" / "certs" / "scenescape-ca.pem"
  supass = (deploy_dir / "secrets" / "supass").read_text().strip()
  verify_tls: bool | str = str(ca_cert) if args.verify_tls else False

  session = manager_session(args.manager_url, verify_tls, "admin", supass)

  uid = args.uid
  if args.update and uid is None:
    uid = find_asset_uid_by_name(session, args.manager_url, args.name)
    if uid is None:
      raise SystemExit(f"--update given but no existing Object Library asset named '{args.name}' was found")
  is_update = uid is not None

  data = {"name": args.name}
  if is_update:
    # Partial update: only send fields the caller explicitly set, leaving the rest unchanged.
    if args.x_size is not None:
      data["x_size"] = args.x_size
    if args.y_size is not None:
      data["y_size"] = args.y_size
    if args.z_size is not None:
      data["z_size"] = args.z_size
    if args.mark_color is not None:
      data["mark_color"] = args.mark_color
  else:
    data["x_size"] = args.x_size if args.x_size is not None else 1.0
    data["y_size"] = args.y_size if args.y_size is not None else 1.0
    data["z_size"] = args.z_size if args.z_size is not None else 1.0
    data["mark_color"] = args.mark_color if args.mark_color is not None else "#888888"

  if args.mass is not None:
    data["mass"] = args.mass
  if args.is_static is not None:
    data["is_static"] = args.is_static

  asset = submit_asset(session, args.manager_url, uid, data, args.model_3d)
  action = "updated" if is_update else "created"
  print(f"Object Library asset {action}: {args.name} ({asset['uid']})")


if __name__ == "__main__":
  main()
