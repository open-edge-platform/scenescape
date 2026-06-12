# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Validate, persist, and load user deployment inputs (Step 1)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

INPUTS_FILE = "deploy-inputs.json"
STATE_FILE = ".deploy-state.json"


def validate_camera_streams(camera_ids: list[str], streams: list[str]) -> None:
  if len(camera_ids) != len(streams):
    raise ValueError("camera_ids and streams must have the same length")
  if not camera_ids:
    raise ValueError("at least one camera is required")
  if len(set(camera_ids)) != len(camera_ids):
    raise ValueError("camera_ids must be unique")
  if any("/" in camera_id for camera_id in camera_ids):
    raise ValueError("camera_ids must not contain '/'")
  for stream in streams:
    parsed = urlparse(stream)
    if parsed.scheme not in ("rtsp", "rtsps") or not parsed.netloc:
      raise ValueError(f"invalid RTSP URL: {stream}")


def validate_inputs(
  camera_ids: list[str],
  streams: list[str],
  scene_name: str,
) -> None:
  if not scene_name or not scene_name.strip():
    raise ValueError("scene_name is required")
  validate_camera_streams(camera_ids, streams)


def inputs_payload(
  camera_ids: list[str],
  streams: list[str],
  scene_name: str,
  skill_dir: str | None = None,
) -> dict[str, Any]:
  validate_inputs(camera_ids, streams, scene_name)
  payload: dict[str, Any] = {
    "scene_name": scene_name.strip(),
    "camera_ids": list(camera_ids),
    "streams": list(streams),
  }
  if skill_dir:
    payload["skill_dir"] = skill_dir
  return payload


def save_inputs(deploy_dir: Path, payload: dict[str, Any]) -> Path:
  path = deploy_dir / INPUTS_FILE
  deploy_dir.mkdir(parents=True, exist_ok=True)
  path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
  return path


def load_inputs(deploy_dir: Path) -> dict[str, Any]:
  inputs_path = deploy_dir / INPUTS_FILE
  if inputs_path.is_file():
    return json.loads(inputs_path.read_text(encoding="utf-8"))

  state_path = deploy_dir / STATE_FILE
  if state_path.is_file():
    state = json.loads(state_path.read_text(encoding="utf-8"))
    for key in ("scene_name", "camera_ids", "streams"):
      if key not in state:
        raise ValueError(f"checkpoint missing {key}; re-run Step 1 with --fresh")
    return {
      "scene_name": state["scene_name"],
      "camera_ids": state["camera_ids"],
      "streams": state["streams"],
      "skill_dir": state.get("skill_dir"),
    }

  raise FileNotFoundError(
    f"No {INPUTS_FILE} or {STATE_FILE} in {deploy_dir}; gather user inputs first (Step 1)"
  )


def inputs_match(saved: dict[str, Any], candidate: dict[str, Any]) -> bool:
  return (
    saved.get("scene_name") == candidate.get("scene_name")
    and saved.get("camera_ids") == candidate.get("camera_ids")
    and saved.get("streams") == candidate.get("streams")
  )


def main() -> None:
  parser = argparse.ArgumentParser(description="Validate and persist SceneScape deployment inputs")
  sub = parser.add_subparsers(dest="command", required=True)

  write = sub.add_parser("write", help="Validate and write deploy-inputs.json")
  write.add_argument("--deploy-dir", required=True, type=Path)
  write.add_argument("--scene-name", required=True)
  write.add_argument("--camera-ids", required=True, nargs="+")
  write.add_argument("--streams", required=True, nargs="+")
  write.add_argument("--skill-dir", default=None)

  read = sub.add_parser("read", help="Print deploy-inputs.json or checkpoint inputs as JSON")
  read.add_argument("--deploy-dir", required=True, type=Path)

  check = sub.add_parser("check", help="Exit 0 when CLI inputs match saved deploy-inputs.json")
  check.add_argument("--deploy-dir", required=True, type=Path)
  check.add_argument("--scene-name", required=True)
  check.add_argument("--camera-ids", required=True, nargs="+")
  check.add_argument("--streams", required=True, nargs="+")

  args = parser.parse_args()

  if args.command == "write":
    payload = inputs_payload(args.camera_ids, args.streams, args.scene_name, args.skill_dir)
    path = save_inputs(args.deploy_dir, payload)
    print(path)
    return

  if args.command == "read":
    payload = load_inputs(args.deploy_dir)
    print(json.dumps(payload))
    return

  saved = json.loads((args.deploy_dir / INPUTS_FILE).read_text(encoding="utf-8"))
  candidate = inputs_payload(args.camera_ids, args.streams, args.scene_name)
  if inputs_match(saved, candidate):
    return
  raise SystemExit("inputs differ from deploy-inputs.json; use --fresh to redeploy with new values")


if __name__ == "__main__":
  main()
