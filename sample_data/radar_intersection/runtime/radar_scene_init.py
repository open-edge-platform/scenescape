#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Import Radar Intersection (if missing) and sync camera/radar poses from JSON."""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://web.scenescape.intel.com/api/v1"
ZIP = Path("/scene-import/RadarIntersection-scene-import.zip")
SCENE_JSON = Path("/scene-import/RadarIntersection.json")
CTX = ssl._create_unverified_context()


def _req(method: str, path: str, *, data=None, headers=None, multipart=False):
  hdrs = dict(headers or {})
  body = data
  if data is not None and not multipart and not isinstance(data, (bytes, bytearray)):
    body = json.dumps(data).encode()
    hdrs.setdefault("Content-Type", "application/json")
  req = urllib.request.Request(f"{API}{path}", data=body, method=method, headers=hdrs)
  try:
    with urllib.request.urlopen(req, context=CTX, timeout=120) as resp:
      raw = resp.read()
      return resp.status, json.loads(raw) if raw else {}
  except urllib.error.HTTPError as e:
    return e.code, e.read().decode(errors="replace")


def main() -> int:
  password = os.environ.get("SUPASS", "")
  if not password:
    print("radar-scene-init: SUPASS is required", file=sys.stderr)
    return 1

  status, auth = _req(
    "POST", "/auth",
    data=urllib.parse.urlencode({"username": "admin", "password": password}).encode(),
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    multipart=True,
  )
  if status != 200 or not isinstance(auth, dict) or "token" not in auth:
    print(f"radar-scene-init: auth failed HTTP {status}: {auth}", file=sys.stderr)
    return 1
  token = auth["token"]
  hdr = {"Authorization": f"Token {token}"}

  status, scenes = _req("GET", "/scenes", headers=hdr)
  if status != 200 or not isinstance(scenes, dict):
    print(f"radar-scene-init: list scenes failed HTTP {status}", file=sys.stderr)
    return 1
  existing = None
  for s in scenes.get("results", []):
    if s.get("name") == "Radar Intersection":
      existing = s
      break

  if existing is None:
    print("radar-scene-init: importing Radar Intersection scene...")
    boundary = "----RadarSceneBoundary"
    zip_bytes = ZIP.read_bytes()
    body = (
      f"--{boundary}\r\n"
      f'Content-Disposition: form-data; name="zipFile"; '
      f'filename="RadarIntersection-scene-import.zip"\r\n'
      f"Content-Type: application/zip\r\n\r\n"
    ).encode() + zip_bytes + f"\r\n--{boundary}--\r\n".encode()
    status, out = _req(
      "POST", "/import-scene/",
      data=body,
      headers={
        **hdr,
        "Content-Type": f"multipart/form-data; boundary={boundary}",
      },
      multipart=True,
    )
    if status not in (200, 201):
      print(f"radar-scene-init: import failed HTTP {status}: {out}", file=sys.stderr)
      return 1
    print(f"radar-scene-init: import done (HTTP {status})")
    status, scenes = _req("GET", "/scenes", headers=hdr)
    for s in scenes.get("results", []):
      if s.get("name") == "Radar Intersection":
        existing = s
        break
  else:
    print("radar-scene-init: Radar Intersection scene already exists")

  if existing is None:
    print("radar-scene-init: could not resolve scene uid", file=sys.stderr)
    return 1
  scene_uid = existing["uid"]
  cfg = json.loads(SCENE_JSON.read_text(encoding="utf-8"))

  for cam in cfg.get("cameras", []):
    # UI exports often keep transform_type="3d-2d point correspondence" while
    # only storing translation/rotation/scale. The REST API builds the
    # transforms column from those fields only when transform_type is euler.
    transform_type = cam.get("transform_type", "euler")
    if cam.get("transforms") is None and all(
        k in cam for k in ("translation", "rotation")
    ):
      transform_type = "euler"
    payload = {
      "name": cam["name"],
      "sensor_id": cam["uid"],
      "scene": scene_uid,
      "transform_type": transform_type,
      "translation": cam["translation"],
      "rotation": cam["rotation"],
      "scale": cam.get("scale", [1.0, 1.0, 1.0]),
      "intrinsics": cam.get("intrinsics"),
    }
    if cam.get("transforms") is not None:
      payload["transforms"] = cam["transforms"]
    status, cur = _req("GET", f"/camera/{cam['uid']}", headers=hdr)
    if status == 200:
      status2, out = _req("PUT", f"/camera/{cam['uid']}", data=payload, headers=hdr)
    else:
      status2, out = _req("POST", "/camera", data=payload, headers=hdr)
    if status2 not in (200, 201):
      print(f"radar-scene-init: camera {cam['uid']} sync failed HTTP {status2}: {out}",
            file=sys.stderr)
      return 1
    print(f"radar-scene-init: synced camera {cam['uid']} (HTTP {status2})")

  for radar in cfg.get("radars", []):
    payload = {
      "name": radar["name"],
      "sensor_id": radar["uid"],
      "scene": scene_uid,
      "transform_type": radar.get("transform_type", "euler"),
      "translation": radar["translation"],
      "rotation": radar["rotation"],
      "scale": radar.get("scale", [1.0, 1.0, 1.0]),
    }
    status, cur = _req("GET", f"/radar/{radar['uid']}", headers=hdr)
    if status == 200:
      status2, out = _req("PUT", f"/radar/{radar['uid']}", data=payload, headers=hdr)
    else:
      status2, out = _req("POST", "/radar", data=payload, headers=hdr)
    if status2 not in (200, 201):
      print(f"radar-scene-init: radar {radar['uid']} sync failed HTTP {status2}: {out}",
            file=sys.stderr)
      return 1
    print(f"radar-scene-init: synced radar {radar['uid']} (HTTP {status2})")

  # Drop sensors no longer listed in RadarIntersection.json (e.g. s120 cams,
  # intersection-radar2) so the live scene matches the demo budget.
  want_cams = {c["uid"] for c in cfg.get("cameras", [])}
  want_radars = {r["uid"] for r in cfg.get("radars", [])}

  def _scene_uid(obj: dict) -> str | None:
    sc = obj.get("scene")
    if isinstance(sc, dict):
      return sc.get("uid")
    return sc

  status, cams = _req("GET", "/cameras", headers=hdr)
  if status == 200 and isinstance(cams, dict):
    for cam in cams.get("results", []):
      sid = cam.get("sensor_id") or cam.get("uid")
      if sid and sid not in want_cams and _scene_uid(cam) == scene_uid:
        status2, out = _req("DELETE", f"/camera/{sid}", headers=hdr)
        print(f"radar-scene-init: deleted camera {sid} (HTTP {status2})")
  status, radars = _req("GET", "/radars", headers=hdr)
  if status == 200 and isinstance(radars, dict):
    for radar in radars.get("results", []):
      sid = radar.get("sensor_id") or radar.get("uid")
      if sid and sid not in want_radars and _scene_uid(radar) == scene_uid:
        status2, out = _req("DELETE", f"/radar/{sid}", headers=hdr)
        print(f"radar-scene-init: deleted radar {sid} (HTTP {status2})")

  print("radar-scene-init: done")
  return 0


if __name__ == "__main__":
  sys.exit(main())
