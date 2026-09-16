#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Download the detection model used by this skill's pipeline via the Model Download
microservice (https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.2.0/microservices/model-download).

Scoped to the single OMZ model (`person-detection-retail-0013`) this skill's generated pipeline
config references, so the skill can run standalone without a full repo checkout or a
`model_download/` folder on disk.

Usage: download_model.py [deploy_dir]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from urllib import error, request

MODEL_NAME = "person-detection-retail-0013"
MODEL_HUB = "omz"
MODEL_XML = f"{MODEL_HUB}/{MODEL_NAME}/FP32/{MODEL_NAME}.xml"

# Pin the same image/tag used by model_download/Makefile's MODEL_DOWNLOADER_IMAGE.
DOWNLOADER_IMAGE = "intel/model-download:2026.2.0-ww32"
CONTAINER_PORT = 8000
API_READY_TIMEOUT_S = 120
JOB_POLL_INTERVAL_S = 5.0
PROXY_ENV_VARS = ("http_proxy", "https_proxy", "no_proxy", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY")


def compose_project_name(deploy_dir: str) -> str:
  out = subprocess.check_output(
    ["docker", "compose", "config", "--format", "json"],
    cwd=deploy_dir,
    text=True,
  )
  return json.loads(out).get("name", "scenescape")


def model_present(models_volume: str) -> bool:
  result = subprocess.run(
    [
      "docker", "container", "run", "--rm",
      "-v", f"{models_volume}:/models",
      "alpine:3.23",
      "test", "-f", f"/models/{MODEL_XML}",
    ],
    check=False,
  )
  return result.returncode == 0


def ensure_volume(models_volume: str) -> None:
  exists = subprocess.run(
    ["docker", "volume", "inspect", models_volume],
    check=False,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
  ).returncode == 0
  if not exists:
    subprocess.run(["docker", "volume", "create", models_volume], check=True, stdout=subprocess.DEVNULL)
  subprocess.run(
    [
      "docker", "run", "--rm",
      "-v", f"{models_volume}:/dest",
      "alpine:3.23",
      "chown", "-R", f"{os.getuid()}:{os.getgid()}", "/dest",
    ],
    check=True,
  )


def start_downloader(container_name: str, models_volume: str, host_port: int) -> None:
  subprocess.run(
    ["docker", "rm", "-f", container_name],
    check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
  )
  env_args: list[str] = []
  for var in PROXY_ENV_VARS:
    value = os.environ.get(var)
    if value:
      env_args += ["-e", f"{var}={value}"]
  subprocess.run(
    [
      "docker", "run", "-d",
      "--name", container_name,
      "-p", f"{host_port}:{CONTAINER_PORT}",
      "-v", f"{models_volume}:/opt/models",
      *env_args,
      DOWNLOADER_IMAGE, "--plugins", MODEL_HUB,
    ],
    check=True,
    stdout=subprocess.DEVNULL,
  )


def stop_downloader(container_name: str) -> None:
  subprocess.run(
    ["docker", "rm", "-f", container_name],
    check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
  )


def wait_for_api(api_url: str, timeout_s: float = API_READY_TIMEOUT_S) -> None:
  req = request.Request(f"{api_url}/api/v1/jobs", method="GET")
  deadline = time.time() + timeout_s
  while time.time() < deadline:
    try:
      with request.urlopen(req, timeout=5):
        return
    except (error.URLError, ConnectionResetError, TimeoutError):
      time.sleep(2)
  raise TimeoutError(f"model-download API did not become ready at {api_url}")


def request_download(api_url: str) -> list[str]:
  endpoint = f"{api_url.rstrip('/')}/api/v1/models/download?download_path=."
  payload = json.dumps({
    "models": [{"name": MODEL_NAME, "hub": MODEL_HUB}],
    "parallel_downloads": False,
  }).encode("utf-8")
  req = request.Request(
    endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST",
  )
  try:
    with request.urlopen(req, timeout=1800) as response:
      body = json.loads(response.read().decode("utf-8", errors="replace"))
  except error.HTTPError as exc:
    detail = exc.read().decode("utf-8", errors="replace")
    raise RuntimeError(f"model download request failed: HTTP {exc.code} - {detail}") from exc
  job_ids = body.get("job_ids", [])
  if not isinstance(job_ids, list) or not job_ids:
    raise RuntimeError("model-download API did not return any job ids")
  return job_ids


def wait_for_jobs(api_url: str, job_ids: list[str], timeout_s: float) -> None:
  endpoint = f"{api_url.rstrip('/')}/api/v1/jobs"
  req = request.Request(endpoint, method="GET")
  deadline = time.time() + timeout_s
  tracked = set(job_ids)

  while time.time() < deadline:
    with request.urlopen(req, timeout=30) as response:
      data = json.loads(response.read().decode("utf-8", errors="replace"))
    jobs_by_id = {
      job["id"]: job for job in data.get("jobs", [])
      if isinstance(job, dict) and isinstance(job.get("id"), str)
    }

    pending = []
    for job_id in tracked:
      job = jobs_by_id.get(job_id)
      if job is None:
        pending.append(job_id)
        continue
      status = str(job.get("status", "")).strip().lower()
      result = job.get("result") if isinstance(job.get("result"), dict) else {}
      success = result.get("success")
      if status in ("failed", "canceled") or success is False:
        raise RuntimeError(f"model download job {job_id} failed: {job}")
      if status != "completed":
        pending.append(job_id)

    if not pending:
      return
    time.sleep(min(JOB_POLL_INTERVAL_S, max(0.0, deadline - time.time())))

  raise TimeoutError(f"timed out waiting for model download job(s): {sorted(tracked)}")


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("deploy_dir", nargs="?", default=".")
  parser.add_argument(
    "--host-port", type=int,
    default=int(os.environ.get("MODEL_DOWNLOADER_HOST_PORT", "8200")),
  )
  parser.add_argument(
    "--wait-timeout", type=float,
    default=float(os.environ.get("MODEL_DOWNLOADER_WAIT_TIMEOUT", "720")),
  )
  args = parser.parse_args()

  project_name = compose_project_name(args.deploy_dir)
  models_volume = f"{project_name}_vol-models"
  container_name = f"{project_name}-model-download"
  api_url = f"http://127.0.0.1:{args.host_port}"

  if model_present(models_volume):
    print(f"Detection models already present in {models_volume}.")
    return 0

  ensure_volume(models_volume)
  print(f"Starting model-download service ({DOWNLOADER_IMAGE})...")
  start_downloader(container_name, models_volume, args.host_port)
  try:
    wait_for_api(api_url)
    print(f"Requesting {MODEL_NAME} ({MODEL_HUB}) download...")
    job_ids = request_download(api_url)
    wait_for_jobs(api_url, job_ids, args.wait_timeout)
  finally:
    stop_downloader(container_name)

  if not model_present(models_volume):
    print(f"FAIL: {MODEL_XML} missing after model-download job completed", file=sys.stderr)
    return 1

  print(f"Detection models ready in {models_volume}.")
  return 0


if __name__ == "__main__":
  sys.exit(main())
