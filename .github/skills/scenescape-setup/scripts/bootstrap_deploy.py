# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Generate deployment files (skill steps 2–6)."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from deploy_inputs import load_inputs

DLSTREAMER_FOLDERS = ("model-proc-files", "mosquitto", "user_scripts")


def skill_dir_from_arg(value: Path) -> Path:
  path = value.resolve()
  if not (path / "references" / "docker-compose-template.md").is_file():
    raise ValueError(f"Not a scenescape-setup skill directory: {path}")
  return path


def fetch_dlstreamer_assets(deploy_dir: Path) -> None:
  """Sparse-checkout pipeline support folders from the upstream repo."""
  dl_dir = deploy_dir / "dlstreamer-pipeline-server"
  gstplugins = dl_dir / "user_scripts" / "gstplugins"
  required_plugins = (
    "sscape_post_decode_timestamp_capture.py",
    "sscape_post_inference_data_publish.py",
    "sscape_policies.py",
    "sscape_3d_detector.py",
  )
  if (
    (dl_dir / "model-proc-files" / "person-detection-retail-0013.json").is_file()
    and all((gstplugins / name).is_file() for name in required_plugins)
  ):
    return

  tmp = deploy_dir / "_scenescape-tmp"
  if tmp.exists():
    shutil.rmtree(tmp)

  subprocess.run(
    [
      "git", "clone", "--filter=blob:none", "--sparse", "--branch", "feature/sscape-app-skill",
      "https://github.com/open-edge-platform/scenescape.git",
      str(tmp),
    ],
    check=True,
  )
  subprocess.run(["git", "sparse-checkout", "init", "--no-cone"], cwd=tmp, check=True)
  subprocess.run(
    [
      "git", "sparse-checkout", "set",
      "/dlstreamer-pipeline-server/model-proc-files",
      "/dlstreamer-pipeline-server/mosquitto",
      "/dlstreamer-pipeline-server/user_scripts",
    ],
    cwd=tmp,
    check=True,
  )

  dl_dir.mkdir(parents=True, exist_ok=True)
  repo_dl = tmp / "dlstreamer-pipeline-server"
  for folder in DLSTREAMER_FOLDERS:
    src = repo_dl / folder
    dst = dl_dir / folder
    if dst.exists():
      shutil.rmtree(dst)
    shutil.copytree(src, dst)
  shutil.rmtree(tmp)

  missing = [name for name in required_plugins if not (gstplugins / name).is_file()]
  if missing:
    raise FileNotFoundError(
      "Sparse checkout of user_scripts is missing required gstplugins: "
      + ", ".join(missing)
    )


def copy_skill_assets(skill_dir: Path, deploy_dir: Path) -> None:
  scripts_dst = deploy_dir / "scripts"
  scripts_dst.mkdir(parents=True, exist_ok=True)

  for pattern in ("*.py", "*.sh"):
    for src in (skill_dir / "scripts").glob(pattern):
      shutil.copy2(src, scripts_dst / src.name)

  subprocess.run(["chmod", "+x", *map(str, scripts_dst.glob("*.sh"))], check=False)


def copy_secrets_scripts(skill_dir: Path, deploy_dir: Path) -> None:
  secrets_dir = deploy_dir / "secrets"
  secrets_dir.mkdir(parents=True, exist_ok=True)
  for name in ("generate_secrets.sh", "openssl.cnf"):
    shutil.copy2(skill_dir / "assets" / name, secrets_dir / name)
  subprocess.run(["chmod", "+x", str(secrets_dir / "generate_secrets.sh")], check=False)


def copy_controller_configs(skill_dir: Path, deploy_dir: Path) -> None:
  controller_dir = deploy_dir / "controller"
  controller_dir.mkdir(parents=True, exist_ok=True)
  for name in ("tracker-config.json", "reid-config.json"):
    shutil.copy2(skill_dir / "assets" / name, controller_dir / name)


def generate_docker_compose(skill_dir: Path, deploy_dir: Path) -> None:
  """Extract the ```yaml fenced block from the compose template and substitute
  ${SECRETSDIR}. Done in pure Python (no shell) since deploy_dir/secrets_dir are
  user-supplied paths and must never be interpolated into a shell command string."""
  template = skill_dir / "references" / "docker-compose-template.md"
  secrets_dir = deploy_dir / "secrets"

  lines: list[str] = []
  in_block = False
  for line in template.read_text(encoding="utf-8").splitlines():
    if not in_block and line.strip() == "```yaml":
      in_block = True
      continue
    if in_block and line.strip() == "```":
      break
    if in_block:
      lines.append(line)

  if not lines:
    raise ValueError(f"No ```yaml fenced block found in {template}")

  compose_text = "\n".join(lines).replace("${SECRETSDIR}", str(secrets_dir)) + "\n"
  (deploy_dir / "docker-compose.yml").write_text(compose_text, encoding="utf-8")


def generate_video_file_override(deploy_dir: Path, payload: dict) -> None:
  """When Step 1 inputs are local video files (payload["source_type"] == "file"),
  write docker-compose.override.yml with a local RTSP re-streamer (mediamtx + ffmpeg)
  that loops each file so the rest of the deployment (pipeline generation, RTSP
  validation, proxy bypass) treats it exactly like a live camera pointed at
  rtsp://mediaserver:8554/<camera_id>. docker compose auto-merges *.override.yml
  files with docker-compose.yml, so no other orchestration changes are required.
  See references/video-file-input.md."""
  override_path = deploy_dir / "docker-compose.override.yml"
  if payload.get("source_type") != "file":
    if override_path.exists():
      override_path.unlink()
    return

  camera_ids = payload["camera_ids"]
  video_paths = payload["video_paths"]

  input_clauses = []
  map_clauses = []
  volume_lines = []
  for index, (camera_id, video_path) in enumerate(zip(camera_ids, video_paths)):
    container_path = f"/videos/{camera_id}{Path(video_path).suffix}"
    input_clauses.append(f"-re -stream_loop -1 -i {container_path}")
    map_clauses.append(
      f"-map {index}:v -c:v libx264 -preset veryfast -an -f rtsp "
      f"-rtsp_transport tcp rtsp://mediaserver:8554/{camera_id}"
    )
    volume_lines.append(f"      - {video_path}:{container_path}:ro")

  command = "-nostdin " + " ".join(input_clauses) + " " + " ".join(map_clauses)
  volumes_block = "\n".join(volume_lines)
  spdx_file_copyright = "SPDX-FileCopyrightText"
  spdx_license_identifier = "SPDX-License-Identifier"

  override_path.write_text(
    f"# {spdx_file_copyright}: (C) 2026 Intel Corporation\n"
    f"# {spdx_license_identifier}: Apache-2.0\n"
    "#\n"
    "# Generated because Step 1 inputs were local video files instead of live RTSP\n"
    "# cameras. Loops each file through a local RTSP server (mediamtx) so the rest of\n"
    "# the deployment is unchanged from the live-camera path. docker compose\n"
    "# auto-merges this file with docker-compose.yml; no -f flag is needed.\n"
    "\n"
    "networks:\n"
    "  scenescape:\n"
    "\n"
    "services:\n"
    "  mediaserver:\n"
    "    image: bluenviron/mediamtx:1.18.1\n"
    "    networks:\n"
    "      scenescape:\n"
    "        aliases:\n"
    "          - mediaserver\n"
    "    restart: always\n"
    "\n"
    "  video-file-cams:\n"
    "    image: linuxserver/ffmpeg:version-8.1-cli\n"
    f"    command: {command}\n"
    "    volumes:\n"
    f"{volumes_block}\n"
    "    networks:\n"
    "      scenescape:\n"
    "    depends_on:\n"
    "      - mediaserver\n"
    "    restart: always\n",
    encoding="utf-8",
  )


def load_payload_for_bootstrap(
  deploy_dir: Path,
  inputs_file: Path | None,
  from_deploy_inputs: bool,
) -> dict | None:
  """Best-effort load of the full deploy-inputs.json payload (including source_type/
  video_paths for file-based deployments). Returns None when inputs were provided as
  bare --camera-ids/--streams args, which carry no video-file metadata."""
  if inputs_file is not None:
    return json.loads(inputs_file.read_text(encoding="utf-8"))
  if from_deploy_inputs:
    return load_inputs(deploy_dir)
  return None


def generate_secrets_and_env(
  deploy_dir: Path,
  skill_dir: Path,
  no_proxy_hosts: list[str],
) -> None:
  subprocess.run(
    ["bash", "generate_secrets.sh"],
    cwd=deploy_dir / "secrets",
    check=True,
  )

  # Always include internal service hostnames for proxy bypass
  internal_hosts = [
    "broker.scenescape.intel.com",
    ".scenescape.intel.com",
  ] + no_proxy_hosts

  cmd = [
    sys.executable,
    str(skill_dir / "scripts" / "write_deployment_env.py"),
    "--deploy-dir", str(deploy_dir),
  ]
  for host in internal_hosts:
    cmd.extend(["--append-no-proxy", host])

  subprocess.run(cmd, check=True)


def main() -> None:
  parser = argparse.ArgumentParser(description="Bootstrap SceneScape deployment files (steps 2–6)")
  parser.add_argument("--deploy-dir", required=True, type=Path)
  parser.add_argument("--skill-dir", required=True, type=Path)
  parser.add_argument("--inputs-file", type=Path, help="deploy-inputs.json from Step 1")
  parser.add_argument("--from-deploy-inputs", action="store_true", help="Read deploy-inputs.json in deploy-dir")
  parser.add_argument("--camera-ids", nargs="+", metavar="CAMERA_ID")
  parser.add_argument("--streams", nargs="+", metavar="RTSP_URL")
  args = parser.parse_args()

  deploy_dir = args.deploy_dir.resolve()
  skill_dir = skill_dir_from_arg(args.skill_dir)
  deploy_dir.mkdir(parents=True, exist_ok=True)

  if not args.inputs_file and not args.from_deploy_inputs and not (args.camera_ids and args.streams):
    raise SystemExit("provide --inputs-file, --from-deploy-inputs, or both --camera-ids and --streams")

  fetch_dlstreamer_assets(deploy_dir)
  copy_skill_assets(skill_dir, deploy_dir)
  copy_secrets_scripts(skill_dir, deploy_dir)
  copy_controller_configs(skill_dir, deploy_dir)
  generate_docker_compose(skill_dir, deploy_dir)

  payload = load_payload_for_bootstrap(deploy_dir, args.inputs_file, args.from_deploy_inputs)
  if payload is not None:
    generate_video_file_override(deploy_dir, payload)

  adapt_script = Path(__file__).resolve().parent / "adapt_pipeline_config.py"
  adapt_cmd = [
    sys.executable, str(adapt_script),
    "--deploy-dir", str(deploy_dir),
    "--from-deploy-inputs",
  ]
  if args.inputs_file:
    adapt_cmd = [
      sys.executable, str(adapt_script),
      "--deploy-dir", str(deploy_dir),
      "--inputs-file", str(args.inputs_file),
    ]
  elif args.camera_ids and args.streams:
    adapt_cmd = [
      sys.executable, str(adapt_script),
      "--deploy-dir", str(deploy_dir),
      "--camera-ids", *args.camera_ids,
      "--streams", *args.streams,
    ]

  adapt = subprocess.run(adapt_cmd, check=True, capture_output=True, text=True)
  no_proxy_hosts = []
  for line in adapt.stdout.splitlines():
    if line.startswith("no_proxy_hosts="):
      no_proxy_hosts = [h for h in line.split("=", 1)[1].split(",") if h]
  generate_secrets_and_env(deploy_dir, skill_dir, no_proxy_hosts)

  print(f"Bootstrap complete: {deploy_dir}")


if __name__ == "__main__":
  main()
