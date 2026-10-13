#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Generic CLI for point-cloud test and verification workflows.

The tool bundles a small set of composable commands that are useful for
exercising and validating the AutoCalibration perceptual-sensor localization
feature (and point-cloud tooling in general):

  glb-to-cloud   Sample a point cloud (PCD/PLY) from a mesh (GLB/PLY).
  transform      Apply a 4x4 rigid transform to a point-cloud file.
  localize       POST a point cloud to the perceptual-sensor localization API.
  status         GET (optionally poll) the localization status for a sensor.

Each command reads from and writes to files so the steps can be chained, e.g.
generate a scene cloud, transform it by a known matrix to emulate a sensor, POST
it for localization, and poll for the recovered transform as verification
evidence.
"""

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import numpy as np
import open3d as o3d
import requests

# The calibration engine and REST client live in autocalibration/src, which is
# on the import path inside the container. On the host it is added explicitly so
# the tool can run without a container.
_AUTOCALIB_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_AUTOCALIB_SRC) not in sys.path:
  sys.path.insert(0, str(_AUTOCALIB_SRC))

from point_cloud_registration import (PointCloudRegistration,  # noqa: E402
                                       PointCloudRegistrationError,
                                       SUPPORTED_FORMATS)

DEFAULT_API_URL = "https://localhost/api/v1/autocalibration"
DEFAULT_SCENE_SAMPLE_POINTS = 200000
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_POLL_TIMEOUT = 120.0
# Statuses that indicate the localization has finished (successfully or not).
TERMINAL_STATUSES = ("success", "error")


# ---------------------------------------------------------------------------
# Point-cloud helpers
# ---------------------------------------------------------------------------

def _format_from_path(path):
  """Return the point-cloud format ("pcd"/"ply") implied by a file extension."""
  ext = os.path.splitext(str(path))[1].lower().lstrip(".")
  if ext not in SUPPORTED_FORMATS:
    raise ValueError(
        f"Unsupported point-cloud extension '.{ext}'; expected one of "
        f"{', '.join('.' + f for f in SUPPORTED_FORMATS)}")
  return ext


def write_point_cloud(pcd, path, ascii_fmt=False, compressed=True):
  """Write a point cloud to PCD or PLY, choosing the format from the extension.

  @param   pcd         o3d.geometry.PointCloud to persist.
  @param   path        Destination path ending in .pcd or .ply.
  @param   ascii_fmt   Write ASCII instead of binary.
  @param   compressed  Use compressed binary encoding (PCD only; ignored for
                       ASCII output).
  """
  _format_from_path(path)
  os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
  ok = o3d.io.write_point_cloud(
      str(path), pcd, write_ascii=ascii_fmt, compressed=compressed)
  if not ok:
    raise RuntimeError(f"Failed to write point cloud to {path}")
  return path


def read_point_cloud(path):
  """Read a PCD/PLY point cloud from disk into an Open3D point cloud."""
  _format_from_path(path)
  if not os.path.exists(path):
    raise FileNotFoundError(f"Point cloud file not found: {path}")
  pcd = o3d.io.read_point_cloud(str(path))
  if pcd.is_empty():
    raise ValueError(f"Point cloud file contains no points: {path}")
  return pcd


def load_matrix(path):
  """Load a 4x4 (or 3x4) transform matrix from a JSON or whitespace file.

  Accepts a JSON nested array, or 12/16 plain numbers separated by whitespace
  and/or commas. A 3x4 matrix is promoted to 4x4 with a [0, 0, 0, 1] row.

  @param   path   Path to the matrix file.

  @return  4x4 numpy array of float64.
  """
  text = Path(path).read_text(encoding="utf-8")
  try:
    values = np.array(json.loads(text), dtype=float)
  except json.JSONDecodeError:
    tokens = text.replace(",", " ").split()
    values = np.array([float(tok) for tok in tokens], dtype=float)

  flat = values.reshape(-1)
  if flat.size == 16:
    matrix = flat.reshape(4, 4)
  elif flat.size == 12:
    matrix = np.vstack([flat.reshape(3, 4), [0.0, 0.0, 0.0, 1.0]])
  else:
    raise ValueError(
        f"Transform matrix must contain 12 or 16 numbers, got {flat.size}")
  return matrix


# ---------------------------------------------------------------------------
# REST client helpers
# ---------------------------------------------------------------------------

def _parse_credentials(auth):
  """Return (user, password) from an auth JSON file or a 'user:password' string."""
  if os.path.exists(auth):
    with open(auth, encoding="utf-8") as handle:
      data = json.load(handle)
    return data["user"], data["password"]
  sep = auth.find(":")
  if sep < 0:
    raise SystemExit(
        "error: --auth must be 'user:password' or a path to an auth JSON file")
  return auth[:sep], auth[sep + 1:]


def _derive_auth_url(api_url):
  """Return the manager auth endpoint (scheme://host/api/v1/auth) for an API URL."""
  parts = urlsplit(api_url)
  return urlunsplit((parts.scheme, parts.netloc, "/api/v1/auth", "", ""))


def resolve_token(api_url, auth=None, token=None, auth_url=None, cacert=None,
                  timeout=10):
  """Obtain an API token.

  Authentication is handled by the manager service (not the autocalibration
  service), so credentials are exchanged for a token at the manager's auth
  endpoint before talking to the localization API. A pre-issued `token` is used
  as-is; without credentials or a token, `None` is returned (anonymous).
  """
  if token:
    return token
  if not auth:
    return None
  user, password = _parse_credentials(auth)
  endpoint = auth_url or _derive_auth_url(api_url)
  verify = cacert if cacert else False
  try:
    reply = requests.post(
        endpoint, data={"username": user, "password": password},
        verify=verify, timeout=timeout)
  except requests.exceptions.RequestException as err:
    raise SystemExit(f"error: authentication request to {endpoint} failed: {err}")
  if reply.status_code != 200:
    raise SystemExit(
        f"error: authentication failed ({reply.status_code}) at {endpoint}: "
        f"{reply.text}")
  try:
    return reply.json()["token"]
  except (ValueError, KeyError):
    raise SystemExit(
        f"error: unexpected auth response from {endpoint}: {reply.text}")


def build_client(url, auth=None, token=None, auth_url=None, cacert=None,
                 timeout=10):
  """Construct an AutoCalibrationClient for the perceptual-sensor endpoints.

  Credentials are exchanged for a token at the manager's auth endpoint first,
  then the token is attached to the autocalibration client. TLS verification is
  disabled by default (self-signed localhost); pass a CA certificate path via
  `cacert` to enable it.
  """
  from autocalibration_client import AutoCalibrationClient  # noqa: E402

  resolved = resolve_token(
      url, auth=auth, token=token, auth_url=auth_url, cacert=cacert,
      timeout=timeout)
  verify_ssl = cacert if cacert else False
  return AutoCalibrationClient(
      url=url, token=resolved, verify_ssl=verify_ssl, timeout=timeout)


def _do_request(client, method, path, **kwargs):
  """Issue a request via the client, converting transport errors to a clean exit."""
  try:
    return client.request(method, path, **kwargs)
  except requests.exceptions.RequestException as err:
    raise SystemExit(f"error: request to {path} failed: {err}")


def _print_response(resp):
  """Pretty-print an HTTP response's status code and JSON/text body."""
  try:
    body = resp.json()
  except ValueError:
    body = resp.text
  print(f"HTTP {resp.status_code}")
  print(json.dumps(body, indent=2, sort_keys=True) if isinstance(body, (dict, list)) else body)
  return body


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_glb_to_cloud(args):
  """Sample a point cloud from a mesh and serialize it to PCD/PLY."""
  out_format = _format_from_path(args.output)
  engine = PointCloudRegistration(scene_sample_points=args.number_of_points)
  try:
    pcd = engine.scene_mesh_to_point_cloud(
        args.input, number_of_points=args.number_of_points)
  except PointCloudRegistrationError as err:
    raise SystemExit(f"error: {err}")

  if args.estimate_normals:
    pcd.estimate_normals(
        o3d.geometry.KDTreeSearchParamHybrid(
            radius=args.normal_radius, max_nn=args.normal_max_nn))

  write_point_cloud(
      pcd, args.output, ascii_fmt=args.ascii, compressed=not args.ascii)
  print(f"Wrote {len(pcd.points)} points to {args.output} ({out_format})")
  return 0


def cmd_transform(args):
  """Apply a 4x4 transform to a point-cloud file."""
  pcd = read_point_cloud(args.input)
  matrix = load_matrix(args.matrix)
  pcd.transform(matrix)
  write_point_cloud(
      pcd, args.output, ascii_fmt=args.ascii, compressed=not args.ascii)
  print(f"Transformed {len(pcd.points)} points -> {args.output}")
  return 0


def cmd_localize(args):
  """POST a point cloud to the perceptual-sensor localization endpoint."""
  raw = Path(args.pointcloud).read_bytes()
  body = {
      "sceneId": args.scene_id,
      "pointcloud": base64.b64encode(raw).decode("ascii"),
  }
  if args.format:
    body["format"] = args.format
  if args.modality:
    body["modality"] = args.modality
  if args.initial_transform:
    body["initialTransform"] = load_matrix(args.initial_transform).tolist()

  client = build_client(
      args.url, auth=args.auth, token=args.token, auth_url=args.auth_url,
      cacert=args.cacert, timeout=args.timeout)
  resp = _do_request(
      client, "POST", f"perceptual-sensors/{args.sensor_id}/localization", json=body)
  body = _print_response(resp)
  ok = resp.status_code in (200, 202)
  status = body.get("status") if isinstance(body, dict) else None
  return 0 if ok and status != "error" else 1


def cmd_status(args):
  """GET (optionally poll) the localization status for a sensor."""
  client = build_client(
      args.url, auth=args.auth, token=args.token, auth_url=args.auth_url,
      cacert=args.cacert, timeout=args.timeout)
  path = f"perceptual-sensors/{args.sensor_id}/localization"

  deadline = time.monotonic() + args.timeout_poll
  while True:
    resp = _do_request(client, "GET", path)
    body = _print_response(resp)
    status = body.get("status") if isinstance(body, dict) else None

    if not args.poll or status in TERMINAL_STATUSES:
      return 0 if status == "success" or (not args.poll and resp.status_code == 200) else 1

    if time.monotonic() >= deadline:
      print(f"Timed out after {args.timeout_poll:.0f}s waiting for a terminal status")
      return 1
    time.sleep(args.interval)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _add_client_arguments(parser):
  """Attach the shared REST client arguments to a subcommand parser."""
  parser.add_argument(
      "--url", default=DEFAULT_API_URL,
      help=f"Base API URL (default: {DEFAULT_API_URL})")
  parser.add_argument(
      "--auth", help="user:password or path to an auth JSON file")
  parser.add_argument(
      "--auth-url",
      help="Manager auth endpoint (default: derived as scheme://host/api/v1/auth)")
  parser.add_argument("--token", help="Pre-issued API token")
  parser.add_argument(
      "--cacert", help="CA certificate path to enable TLS verification")
  parser.add_argument(
      "--timeout", type=float, default=10.0,
      help="Per-request timeout in seconds (default: 10)")


def build_parser():
  """Build the top-level argument parser for the CLI."""
  parser = argparse.ArgumentParser(
      prog="perceptual_sensor_cli",
      description="Point-cloud test and verification CLI for AutoCalibration.")
  subparsers = parser.add_subparsers(dest="command", required=True)

  glb = subparsers.add_parser(
      "glb-to-cloud", help="Sample a point cloud from a mesh (GLB/PLY).")
  glb.add_argument("input", help="Input mesh file (GLB or PLY)")
  glb.add_argument("output", help="Output point cloud file (.pcd or .ply)")
  glb.add_argument(
      "--number-of-points", type=int, default=DEFAULT_SCENE_SAMPLE_POINTS,
      help=f"Points to sample (default: {DEFAULT_SCENE_SAMPLE_POINTS})")
  glb.add_argument(
      "--estimate-normals", action="store_true",
      help="Estimate per-point normals before writing")
  glb.add_argument(
      "--normal-radius", type=float, default=0.1,
      help="Normal estimation search radius in meters (default: 0.1)")
  glb.add_argument(
      "--normal-max-nn", type=int, default=30,
      help="Max neighbours for normal estimation (default: 30)")
  glb.add_argument(
      "--ascii", action="store_true", help="Write ASCII instead of binary")
  glb.set_defaults(func=cmd_glb_to_cloud)

  xform = subparsers.add_parser(
      "transform", help="Apply a 4x4 transform to a point-cloud file.")
  xform.add_argument("input", help="Input point cloud file (.pcd or .ply)")
  xform.add_argument("output", help="Output point cloud file (.pcd or .ply)")
  xform.add_argument(
      "--matrix", required=True,
      help="Transform matrix file (JSON 4x4 or 12/16 whitespace numbers)")
  xform.add_argument(
      "--ascii", action="store_true", help="Write ASCII instead of binary")
  xform.set_defaults(func=cmd_transform)

  localize = subparsers.add_parser(
      "localize", help="POST a point cloud to the localization endpoint.")
  localize.add_argument("--sensor-id", required=True, help="Perceptual sensor id")
  localize.add_argument("--scene-id", required=True, help="Target scene id (UUID)")
  localize.add_argument(
      "--pointcloud", required=True, help="Point cloud file to send (.pcd/.ply)")
  localize.add_argument(
      "--format", choices=SUPPORTED_FORMATS,
      help="Explicit point cloud format (default: server auto-detect)")
  localize.add_argument("--modality", help="Optional sensor modality hint")
  localize.add_argument(
      "--initial-transform",
      help="Optional initial 4x4 transform guess (matrix file)")
  _add_client_arguments(localize)
  localize.set_defaults(func=cmd_localize)

  status = subparsers.add_parser(
      "status", help="GET (optionally poll) localization status.")
  status.add_argument("--sensor-id", required=True, help="Perceptual sensor id")
  status.add_argument(
      "--poll", action="store_true",
      help="Poll until a terminal status or timeout")
  status.add_argument(
      "--interval", type=float, default=DEFAULT_POLL_INTERVAL,
      help=f"Poll interval in seconds (default: {DEFAULT_POLL_INTERVAL})")
  status.add_argument(
      "--timeout-poll", type=float, default=DEFAULT_POLL_TIMEOUT,
      help=f"Poll timeout in seconds (default: {DEFAULT_POLL_TIMEOUT})")
  _add_client_arguments(status)
  status.set_defaults(func=cmd_status)

  return parser


def main(argv=None):
  parser = build_parser()
  args = parser.parse_args(argv)
  return args.func(args)


if __name__ == "__main__":
  sys.exit(main())
