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

The script exits 0 on success and prints the created asset's UID.
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


def create_asset(
  session: requests.Session,
  manager_url: str,
  name: str,
  x_size: float,
  y_size: float,
  z_size: float,
  mark_color: str,
  model_3d: Path | None,
  mass: float | None,
  is_static: bool,
) -> str:
  """POST an Object Library (Asset3D) entry and return its UID."""
  data = {
    "name": name,
    "x_size": x_size,
    "y_size": y_size,
    "z_size": z_size,
    "mark_color": mark_color,
  }
  if mass is not None:
    data["mass"] = mass
  if is_static:
    data["is_static"] = True

  if model_3d is not None:
    if not model_3d.exists():
      raise FileNotFoundError(f"Missing 3D model file: {model_3d}")
    with open(model_3d, "rb") as model_handle:
      resp = session.post(
        f"{manager_url}/api/v1/asset",
        data=data,
        files={"model_3d": (model_3d.name, model_handle, "model/gltf-binary")},
        timeout=30,
      )
  else:
    resp = session.post(f"{manager_url}/api/v1/asset", data=data, timeout=10)

  resp.raise_for_status()
  asset_uid = resp.json()["uid"]
  print(f"Object Library asset created: {name} ({asset_uid})")
  return asset_uid


def main() -> None:
  parser = argparse.ArgumentParser(description="Create an Object Library (Asset3D) entry via the SceneScape manager")
  parser.add_argument("--deploy-dir", required=True, type=Path)
  parser.add_argument("--name", required=True, help="Object class name (must match the detected object type, e.g. 'person', 'vehicle')")
  parser.add_argument("--x-size", type=float, default=1.0, help="Size in meters along the x-axis (default 1.0)")
  parser.add_argument("--y-size", type=float, default=1.0, help="Size in meters along the y-axis (default 1.0)")
  parser.add_argument("--z-size", type=float, default=1.0, help="Size in meters along the z-axis (default 1.0)")
  parser.add_argument("--mark-color", default="#888888", help="Hex color for the object's default marker (default #888888)")
  parser.add_argument("--model-3d", type=Path, default=None, help="Optional .glb file to use instead of the default cuboid shape")
  parser.add_argument("--mass", type=float, default=None, help="Optional mass in kg (default server-side value is 1.0)")
  parser.add_argument("--is-static", action="store_true", help="Mark the object class as unable to move on its own")
  parser.add_argument("--manager-url", default="https://localhost")
  parser.add_argument("--verify-tls", action="store_true", help="Verify TLS using <deploy-dir>/secrets/certs/scenescape-ca.pem")
  args = parser.parse_args()

  deploy_dir: Path = args.deploy_dir
  ca_cert = deploy_dir / "secrets" / "certs" / "scenescape-ca.pem"
  supass = (deploy_dir / "secrets" / "supass").read_text().strip()
  verify_tls: bool | str = str(ca_cert) if args.verify_tls else False

  session = manager_session(args.manager_url, verify_tls, "admin", supass)
  create_asset(
    session,
    args.manager_url,
    args.name,
    args.x_size,
    args.y_size,
    args.z_size,
    args.mark_color,
    args.model_3d,
    args.mass,
    args.is_static,
  )


if __name__ == "__main__":
  main()
