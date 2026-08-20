# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Validate, persist, and load user deployment inputs (Step 1)."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

INPUTS_FILE = "deploy-inputs.json"
STATE_FILE = ".deploy-state.json"

# Local video files are looped through an internal RTSP re-streamer (mediamtx) so the
# rest of the pipeline can treat them exactly like a live camera. See bootstrap_deploy.py
# generate_video_file_override() and references/video-file-publishing.md.
MEDIASERVER_HOST = "mediaserver"
MEDIASERVER_PORT = 8554
VIDEO_FILE_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".ts", ".webm", ".mpg", ".mpeg", ".m4v"}


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


def discover_video_files(video_dir: Path) -> list[Path]:
  """Sorted list of video files directly inside video_dir (non-recursive)."""
  if not video_dir.is_dir():
    raise ValueError(f"video_dir does not exist or is not a directory: {video_dir}")
  files = sorted(
    path for path in video_dir.iterdir()
    if path.is_file() and path.suffix.lower() in VIDEO_FILE_EXTENSIONS
  )
  if not files:
    raise ValueError(
      f"no video files found in {video_dir} (looked for: {sorted(VIDEO_FILE_EXTENSIONS)})"
    )
  return files


def derive_camera_id(path: Path, seen: set[str]) -> str:
  """Filesystem-safe, unique camera_id derived from a video file's name."""
  base = re.sub(r"[^A-Za-z0-9_-]+", "-", path.stem).strip("-").lower() or "camera"
  candidate = base
  suffix = 2
  while candidate in seen:
    candidate = f"{base}-{suffix}"
    suffix += 1
  seen.add(candidate)
  return candidate


def validate_video_files(camera_ids: list[str], video_paths: list[Path]) -> None:
  if len(camera_ids) != len(video_paths):
    raise ValueError("camera_ids and video file paths must have the same length")
  if not camera_ids:
    raise ValueError("at least one camera is required")
  if len(set(camera_ids)) != len(camera_ids):
    raise ValueError("camera_ids must be unique")
  if any("/" in camera_id for camera_id in camera_ids):
    raise ValueError("camera_ids must not contain '/'")
  for path in video_paths:
    if not path.is_file():
      raise ValueError(f"video file does not exist: {path}")
    if path.suffix.lower() not in VIDEO_FILE_EXTENSIONS:
      raise ValueError(
        f"unsupported video file extension: {path} (allowed: {sorted(VIDEO_FILE_EXTENSIONS)})"
      )


def inputs_payload(
  camera_ids: list[str] | None,
  streams: list[str] | None,
  scene_name: str,
  skill_dir: str | None = None,
  video_paths: list[str] | None = None,
  mapping: str = "reconstruction",
  glb_file: str | None = None,
  camera_json: str | None = None,
) -> dict[str, Any]:
  if not scene_name or not scene_name.strip():
    raise ValueError("scene_name is required")

  if video_paths is not None:
    resolved_paths = [Path(p).expanduser().resolve() for p in video_paths]
    if camera_ids is None:
      seen: set[str] = set()
      camera_ids = [derive_camera_id(path, seen) for path in resolved_paths]
    validate_video_files(camera_ids, resolved_paths)
    payload: dict[str, Any] = {
      "scene_name": scene_name.strip(),
      "camera_ids": list(camera_ids),
      "streams": [
        f"rtsp://{MEDIASERVER_HOST}:{MEDIASERVER_PORT}/{camera_id}" for camera_id in camera_ids
      ],
      "source_type": "file",
      "video_paths": [str(path) for path in resolved_paths],
    }
  else:
    if camera_ids is None or streams is None:
      raise ValueError("camera_ids and streams are required")
    validate_inputs(camera_ids, streams, scene_name)
    payload = {
      "scene_name": scene_name.strip(),
      "camera_ids": list(camera_ids),
      "streams": list(streams),
      "source_type": "rtsp",
    }

  payload["mapping"] = mapping
  if glb_file:
    payload["glb_file"] = str(Path(glb_file).expanduser().resolve())
  if camera_json:
    payload["camera_json"] = str(Path(camera_json).expanduser().resolve())

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


def gather_interactive_inputs() -> tuple[Path, dict[str, Any]]:
  print("=== SceneScape Deployment Input Setup ===")
  deploy_dir_str = input("Deploy Directory [default: ./deploy]: ").strip() or "./deploy"
  deploy_dir = Path(deploy_dir_str).expanduser().resolve()

  scene_name = input("Scene Name: ").strip()
  while not scene_name:
    print("Scene name is required!")
    scene_name = input("Scene Name: ").strip()

  print("\nMapping Source Options:")
  print("  1. reconstruction (Default: Auto-generate map from camera streams)")
  print("  2. glb (Pre-made 3D GLB mesh file)")
  print("  3. blueprint (2D floor plan image)")
  print("  4. geospatial (GPS-based map)")
  mapping_choice = input("Select mapping option [1-4, default 1]: ").strip() or "1"
  mapping_map = {"1": "reconstruction", "2": "glb", "3": "blueprint", "4": "geospatial"}
  mapping = mapping_map.get(mapping_choice, "reconstruction")

  glb_file = None
  camera_json = None
  if mapping == "glb":
    glb_file = input("Path to .glb 3D mesh file: ").strip()
    has_cam_json = input("Do you have a pre-calibrated camera.json file? (y/n) [default: y]: ").strip().lower() or "y"
    if has_cam_json.startswith("y"):
      camera_json = input("Path to camera.json file: ").strip()

  print("\nVideo Stream Source Options:")
  print("  1. RTSP streams")
  print("  2. Local video directory")
  source_choice = input("Select source option [1-2, default 1]: ").strip() or "1"

  camera_ids = None
  streams = None
  video_paths = None

  if source_choice == "2":
    vdir = input("Path to video directory: ").strip()
    video_paths = [str(p) for p in discover_video_files(Path(vdir))]
    cids_in = input("Camera IDs (space-separated, or press Enter to auto-derive): ").strip()
    if cids_in:
      camera_ids = cids_in.split()
  else:
    streams_in = input("RTSP URLs (space-separated): ").strip()
    streams = streams_in.split()
    cids_in = input("Camera IDs (space-separated, same order as streams): ").strip()
    camera_ids = cids_in.split()

  payload = inputs_payload(
    camera_ids=camera_ids,
    streams=streams,
    scene_name=scene_name,
    video_paths=video_paths,
    mapping=mapping,
    glb_file=glb_file,
    camera_json=camera_json,
  )
  return deploy_dir, payload


def main() -> None:
  parser = argparse.ArgumentParser(description="Validate and persist SceneScape deployment inputs")
  sub = parser.add_subparsers(dest="command", required=True)

  interactive = sub.add_parser("interactive", help="Interactively prompt for deployment inputs")

  write = sub.add_parser("write", help="Validate and write deploy-inputs.json")
  write.add_argument("--deploy-dir", required=True, type=Path)
  write.add_argument("--scene-name", required=True)
  write.add_argument(
    "--camera-ids", nargs="+",
    help="Required with --streams/--video-files; auto-derived from filenames for --video-dir if omitted",
  )
  source = write.add_mutually_exclusive_group(required=True)
  source.add_argument("--streams", nargs="+", metavar="RTSP_URL", help="One RTSP/RTSPS URL per camera")
  source.add_argument(
    "--video-dir", type=Path,
    help="Directory of local video recordings; one camera per file, sorted by filename",
  )
  source.add_argument(
    "--video-files", nargs="+", metavar="PATH",
    help="Explicit list of local video file paths, one per camera, in order",
  )
  write.add_argument("--mapping", default="reconstruction", help="Scene map source: reconstruction, blueprint, glb, geospatial")
  write.add_argument("--glb-file", help="Path to pre-made .glb 3D mesh file")
  write.add_argument("--camera-json", help="Path to pre-calibrated camera JSON file")
  write.add_argument("--skill-dir", default=None)

  read = sub.add_parser("read", help="Print deploy-inputs.json or checkpoint inputs as JSON")
  read.add_argument("--deploy-dir", required=True, type=Path)

  check = sub.add_parser("check", help="Exit 0 when CLI inputs match saved deploy-inputs.json")
  check.add_argument("--deploy-dir", required=True, type=Path)
  check.add_argument("--scene-name", required=True)
  check.add_argument("--camera-ids", required=True, nargs="+")
  check.add_argument("--streams", required=True, nargs="+")

  args = parser.parse_args()

  if args.command == "interactive":
    deploy_dir, payload = gather_interactive_inputs()
    path = save_inputs(deploy_dir, payload)
    print(f"\nSaved deploy inputs to: {path}")
    return

  if args.command == "write":
    if args.video_dir is not None:
      video_paths = [str(path) for path in discover_video_files(args.video_dir)]
      payload = inputs_payload(
        args.camera_ids, None, args.scene_name, args.skill_dir,
        video_paths=video_paths, mapping=args.mapping,
        glb_file=args.glb_file, camera_json=args.camera_json,
      )
    elif args.video_files is not None:
      payload = inputs_payload(
        args.camera_ids, None, args.scene_name, args.skill_dir,
        video_paths=args.video_files, mapping=args.mapping,
        glb_file=args.glb_file, camera_json=args.camera_json,
      )
    else:
      payload = inputs_payload(
        args.camera_ids, args.streams, args.scene_name, args.skill_dir,
        mapping=args.mapping, glb_file=args.glb_file, camera_json=args.camera_json,
      )
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
