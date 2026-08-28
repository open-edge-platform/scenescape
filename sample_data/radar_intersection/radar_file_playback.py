#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Recorded-file GStreamer fragments for the radar-intersection demo.

Radar branch: multifilesrc → g3dlidarparse (point-features=7) →
g3dinference model-type=radarpillars → gvametaconvert → FIFO.

Camera branch mirrors the LiDAR demo (jpegdec → gvadetect).
"""

from __future__ import annotations

import os
import shlex


def radar_multifilesrc_parts(
  *,
  data_path: str,
  start_index: int,
  stop_index: int | None,
  loop: bool,
  frame_rate: int,
  model_config: str,
  device: str,
  score_threshold: float,
  add_tensor_data: str,
  fifo_path: str,
) -> list[str]:
  """GStreamer fragments for recorded RadarPillars ``.bin`` (7 float32/point)."""
  parts = [
    f"multifilesrc location={shlex.quote(data_path)} start-index={start_index}",
  ]
  if stop_index is not None:
    parts.append(f"stop-index={stop_index}")
  if loop:
    parts.append("loop=true")
  parts += [
    "caps=application/octet-stream",
    f"! g3dlidarparse stride=1 frame-rate={frame_rate} point-features=7",
    f"! g3dinference config={shlex.quote(model_config)}"
    f" model-type=radarpillars"
    f" device={shlex.quote(device)}"
    f" score-threshold={score_threshold}",
    f"! gvametaconvert add-tensor-data={add_tensor_data} format=json",
    f"! gvametapublish method=file file-format=json-lines file-path={shlex.quote(fifo_path)}",
    "! fakesink sync=false",
  ]
  return parts


def camera_multifilesrc_parts(
  *,
  data_path: str,
  start_index: int,
  stop_index: int | None,
  loop: bool,
  frame_rate: int,
  model: str,
  model_proc: str,
  device: str,
  score_threshold: float,
  fifo_path: str,
) -> list[str]:
  parts = [
    f"multifilesrc location={shlex.quote(data_path)} start-index={start_index}",
  ]
  if stop_index is not None:
    parts.append(f"stop-index={stop_index}")
  if loop:
    parts.append("loop=true")
  parts += [
    "caps=image/jpeg",
    "! jpegdec",
    "! videoconvert",
    "! video/x-raw,format=BGR",
    f"! gvafpsthrottle target-fps={frame_rate}",
    f"! gvadetect model={shlex.quote(model)}"
    f" model-proc={shlex.quote(model_proc)}"
    f" device={shlex.quote(device)}"
    f" threshold={score_threshold}",
    "! gvametaconvert add-tensor-data=false format=json",
    f"! gvametapublish method=file file-format=json-lines file-path={shlex.quote(fifo_path)}",
    "! fakesink sync=false",
  ]
  return parts


def ensure_parent_dir(path: str) -> None:
  parent = os.path.dirname(path)
  if parent:
    os.makedirs(parent, exist_ok=True)
