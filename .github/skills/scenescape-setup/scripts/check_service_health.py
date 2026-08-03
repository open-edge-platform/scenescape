#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Generic service health checker for SceneScape setup orchestration.

This checker supports two gates in one polling loop:
1) Docker Compose service state (running and optional healthy)
2) Optional HTTP JSON endpoint assertions
"""

from __future__ import annotations

import argparse
import json
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any


def run_cmd(cmd: list[str]) -> str:
  proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
  if proc.returncode != 0:
    return ""
  return proc.stdout.strip()


def compose_state(deploy_dir: str, service: str) -> tuple[bool, str, str]:
  status = run_cmd([
    "docker",
    "compose",
    "-f",
    f"{deploy_dir}/docker-compose.yml",
    "ps",
    service,
    "--format",
    "{{.Status}}",
  ])
  health = run_cmd([
    "docker",
    "compose",
    "-f",
    f"{deploy_dir}/docker-compose.yml",
    "ps",
    service,
    "--format",
    "{{.Health}}",
  ])
  running = "Up" in status
  return running, status, health


def read_url(url: str, insecure: bool, timeout: float = 5.0) -> tuple[int, str]:
  context: ssl.SSLContext | None = None
  if insecure:
    context = ssl._create_unverified_context()  # noqa: SLF001
  req = urllib.request.Request(url, method="GET")
  with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
    code = resp.getcode()
    body = resp.read().decode("utf-8", errors="replace")
  return code, body


def parse_bool(value: str) -> bool:
  lowered = value.strip().lower()
  if lowered in {"1", "true", "yes", "on"}:
    return True
  if lowered in {"0", "false", "no", "off"}:
    return False
  raise ValueError(f"invalid boolean value: {value}")


def dict_get_path(payload: dict[str, Any], key_path: str) -> Any:
  current: Any = payload
  for part in key_path.split("."):
    if not isinstance(current, dict) or part not in current:
      raise KeyError(key_path)
    current = current[part]
  return current


def check_http(
  url: str,
  insecure: bool,
  expect_status: str | None,
  expect_ready: bool | None,
  expect_bools: list[tuple[str, bool]],
) -> tuple[bool, str]:
  try:
    code, body = read_url(url, insecure=insecure)
  except (urllib.error.URLError, TimeoutError, ValueError) as exc:
    return False, f"http_error={exc}"

  if code < 200 or code >= 300:
    return False, f"http_code={code}"

  if not any([expect_status is not None, expect_ready is not None, expect_bools]):
    return True, f"http_code={code}"

  try:
    payload = json.loads(body)
  except json.JSONDecodeError as exc:
    return False, f"invalid_json={exc.msg}"

  if expect_status is not None:
    status_val = payload.get("status")
    if status_val != expect_status:
      return False, f"status={status_val!r} expected={expect_status!r}"

  if expect_ready is not None:
    ready_val = payload.get("ready")
    if ready_val is not expect_ready:
      return False, f"ready={ready_val!r} expected={expect_ready!r}"

  for key_path, expected in expect_bools:
    try:
      actual = dict_get_path(payload, key_path)
    except KeyError:
      return False, f"missing_key={key_path}"
    if actual is not expected:
      return False, f"{key_path}={actual!r} expected={expected!r}"

  return True, f"http_code={code}"


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description="SceneScape generic health checker")
  parser.add_argument("--deploy-dir", default=".", help="Deployment directory")
  parser.add_argument("--service", required=True, help="Docker compose service name")
  parser.add_argument("--max-attempts", type=int, default=30)
  parser.add_argument("--interval", type=float, default=5.0)
  parser.add_argument("--require-healthy", action="store_true")
  parser.add_argument("--url", help="Optional HTTP endpoint to validate")
  parser.add_argument("--insecure", action="store_true", help="Skip TLS verify for URL checks")
  parser.add_argument("--expect-status", help="Expected JSON field: status")
  parser.add_argument(
    "--expect-ready",
    choices=["true", "false"],
    help="Expected JSON field: ready",
  )
  parser.add_argument(
    "--expect-bool",
    action="append",
    default=[],
    help="Expected JSON boolean key path in the form key.path=true|false",
  )
  return parser.parse_args()


def main() -> int:
  args = parse_args()

  if args.max_attempts < 1:
    print("FAIL: --max-attempts must be >= 1")
    return 2

  expect_ready: bool | None = None
  if args.expect_ready is not None:
    expect_ready = parse_bool(args.expect_ready)

  expect_bools: list[tuple[str, bool]] = []
  for item in args.expect_bool:
    if "=" not in item:
      print(f"FAIL: invalid --expect-bool value: {item}")
      return 2
    key_path, raw_val = item.split("=", 1)
    if not key_path.strip():
      print(f"FAIL: invalid --expect-bool key path: {item}")
      return 2
    try:
      bool_val = parse_bool(raw_val)
    except ValueError as exc:
      print(f"FAIL: {exc}")
      return 2
    expect_bools.append((key_path.strip(), bool_val))

  for attempt in range(1, args.max_attempts + 1):
    running, status, health = compose_state(args.deploy_dir, args.service)
    compose_ok = running and (not args.require_healthy or health == "healthy")

    http_ok = True
    http_summary = "http=skipped"
    if args.url:
      http_ok, http_summary = check_http(
        url=args.url,
        insecure=args.insecure,
        expect_status=args.expect_status,
        expect_ready=expect_ready,
        expect_bools=expect_bools,
      )

    print(
      f"[{attempt}/{args.max_attempts}] service={args.service} "
      f"status={status or 'unknown'} health={health or 'n/a'} {http_summary}"
    )

    if compose_ok and http_ok:
      print(f"PASS: {args.service} is ready")
      return 0

    time.sleep(args.interval)

  if args.require_healthy:
    reason = "service not healthy"
  else:
    reason = "service not running"

  if args.url:
    reason = f"{reason} or endpoint check failed"

  print(f"FAIL: {args.service} not ready after {args.max_attempts} attempts ({reason})")
  return 1


if __name__ == "__main__":
  sys.exit(main())
