# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Controller configuration for consuming PTZ PoseContexts.

Two independent, default-off modes: enforcing (`CONTROLLER_PTZ_ENABLED`) gates
PTZ detections with the dwell contract and projects them with the per-frame pose;
shadow (`CONTROLLER_PTZ_SHADOW_MODE`) only observes and records. The numeric
consumer values and the assignment manifest are read only when a mode is on.
"""

import argparse
import json
import os
import re
from dataclasses import dataclass
from typing import Mapping, Optional

from scene_common.positioning_assignments import load_assignments
from scene_common.positioning_config import (
  ConsumerPositioningConfig, PositioningConfigError, load_consumer_config)

PTZ_ENABLED_ENV_VAR = 'CONTROLLER_PTZ_ENABLED'
PTZ_SHADOW_ENV_VAR = 'CONTROLLER_PTZ_SHADOW_MODE'

MODE_ENFORCE = "enforce"
MODE_SHADOW = "shadow"

DEFAULT_SHADOW_RUN_ID = "unspecified"
DEFAULT_SHADOW_SAMPLE_EVERY_N = 10

_TRUE_VALUES = ('1', 'true', 'yes', 'on')
_RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,128}")


class PTZConfigError(PositioningConfigError):
  """Raised when the PTZ consumer configuration is unusable; the Controller must not start."""


def env_flag(name: str) -> bool:
  value = os.getenv(name)
  return value is not None and value.strip().lower() in _TRUE_VALUES


@dataclass(frozen=True)
class PTZSettings:
  mode: str
  consumer: ConsumerPositioningConfig
  assignments: Mapping[str, str]
  run_id: str = DEFAULT_SHADOW_RUN_ID
  shadow_sample_every_n: int = DEFAULT_SHADOW_SAMPLE_EVERY_N

  @property
  def enforcing(self) -> bool:
    return self.mode == MODE_ENFORCE

  @property
  def shadow(self) -> bool:
    return self.mode == MODE_SHADOW


def load_ptz_settings(enabled: bool, shadow: bool, config_file: Optional[str],
                      assignments_file: Optional[str], rewrite_all_time: bool,
                      rewrite_bad_time: bool, ntp_server: Optional[str]) -> Optional[PTZSettings]:
  """Validate the PTZ configuration; None when both modes are off.

  @raises PTZConfigError when the combination or any value is invalid
  """
  if not enabled and not shadow:
    return None
  if enabled and shadow:
    raise PTZConfigError(
      f"{PTZ_ENABLED_ENV_VAR} and {PTZ_SHADOW_ENV_VAR} are mutually exclusive")
  if rewrite_all_time or rewrite_bad_time:
    raise PTZConfigError(
      "PTZ pose consumption cannot be combined with --rewriteAllTime or --rewriteBadTime: "
      "replacing acquisition timestamps invalidates pose matching")
  if not ntp_server:
    raise PTZConfigError("PTZ pose consumption requires an NTP server (--ntp)")
  if not config_file:
    raise PTZConfigError("PTZ pose consumption requires --ptz_config_file")
  if not assignments_file:
    raise PTZConfigError("PTZ pose consumption requires --positioning_assignments_file")

  values = _read_json_object(config_file)
  try:
    consumer = load_consumer_config(values)
  except PositioningConfigError as error:
    raise PTZConfigError(f"{config_file}: {error}") from error
  run_id, sample_every_n = _shadow_settings(values.get("shadow"))
  return PTZSettings(
    mode=MODE_SHADOW if shadow else MODE_ENFORCE,
    consumer=consumer,
    assignments=load_assignments(assignments_file),
    run_id=run_id,
    shadow_sample_every_n=sample_every_n,
  )


def add_ptz_arguments(parser: argparse.ArgumentParser, default_dir: str) -> None:
  """Register the PTZ options; flag defaults come from the environment, off when unset."""
  parser.add_argument("--ptz", action=argparse.BooleanOptionalAction,
                      default=env_flag(PTZ_ENABLED_ENV_VAR),
                      help="Gate PTZ camera detections with PoseContexts and project them "
                           "with the per-frame pose.")
  parser.add_argument("--ptz-shadow", dest="ptz_shadow", action=argparse.BooleanOptionalAction,
                      default=env_flag(PTZ_SHADOW_ENV_VAR),
                      help="Observe PTZ PoseContexts and emit shadow records without changing "
                           "tracking. Cannot be combined with --ptz.")
  parser.add_argument("--ptz_config_file",
                      help="JSON file with the PTZ consumer values and shadow settings",
                      default=os.path.join(default_dir, "ptz-consumer-config.json"))
  parser.add_argument("--positioning_assignments_file",
                      help="JSON manifest mapping PTZ source_id to its Positioning resolver_id",
                      default=os.path.join(default_dir, "positioning-assignments.json"))


def ptz_settings_from_args(args: argparse.Namespace) -> Optional[PTZSettings]:
  """@raises PTZConfigError / PositioningConfigError when the configuration is unusable"""
  return load_ptz_settings(args.ptz, args.ptz_shadow, args.ptz_config_file,
                           args.positioning_assignments_file, args.rewriteAllTime,
                           args.rewriteBadTime, args.ntp)


def _read_json_object(path: str) -> dict:
  try:
    with open(path, "r", encoding="utf-8") as config_file:
      values = json.load(config_file)
  except (OSError, ValueError) as error:
    raise PTZConfigError(f"Cannot read PTZ consumer configuration {path}: {error}") from error
  if not isinstance(values, dict):
    raise PTZConfigError(f"PTZ consumer configuration {path} must be a JSON object")
  return values


def _shadow_settings(shadow):
  if shadow is None:
    return DEFAULT_SHADOW_RUN_ID, DEFAULT_SHADOW_SAMPLE_EVERY_N
  if not isinstance(shadow, dict):
    raise PTZConfigError("'shadow' must be an object")
  run_id = shadow.get("run_id", DEFAULT_SHADOW_RUN_ID)
  if not isinstance(run_id, str) or not _RUN_ID_PATTERN.fullmatch(run_id):
    raise PTZConfigError("shadow.run_id must be 1-128 characters of [A-Za-z0-9._-]")
  every_n = shadow.get("sample_every_n", DEFAULT_SHADOW_SAMPLE_EVERY_N)
  if isinstance(every_n, bool) or not isinstance(every_n, int) or every_n < 1:
    raise PTZConfigError("shadow.sample_every_n must be an integer >= 1")
  return run_id, every_n
