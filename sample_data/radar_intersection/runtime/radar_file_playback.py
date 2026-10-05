#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Recorded-file GStreamer fragments for the radar-intersection demo.

Radar (custom g3d path)::

  multifilesrc → g3dlidarparse → g3dinference → gvametaconvert → FIFO

Cameras use the **same** SceneScape object-detection chain as retail/queuing
file replay (``queuing-config-no-rtsp.json`` / ``retail-config-no-rtsp.json``)::

  multifilesrc → decodebin → videoconvert → BGR
    → sscape_timestamp_capture → gvadetect → gvametaconvert
    → sscape_post_inference_data_publish → fakesink

Live-view ``getimage`` and MQTT detections are handled inside
``sscape_post_inference_data_publish`` (same buffer — no custom annotate).
"""

from __future__ import annotations

import glob
import os
import shlex
import subprocess
import time


def radar_multifilesrc_parts(
  *,
  data_path: str,
  start_index: int,
  stop_index: int | None,
  loop: bool,
  frame_rate: int,
  model_config: str,
  model_type: str,
  point_features: int,
  device: str,
  score_threshold: float,
  add_tensor_data: str,
  fifo_path: str,
  accumulate_past: int = 0,
) -> list[str]:
  """GStreamer fragments for recorded radar bins + g3dinference."""
  del frame_rate  # paced by publisher (g3dlidarparse frame-rate=0)
  parts = [
    f"multifilesrc location={shlex.quote(data_path)} start-index={start_index}",
  ]
  if stop_index is not None:
    parts.append(f"stop-index={stop_index}")
  if loop:
    parts.append("loop=true")
  infer = (
    f"! g3dinference config={shlex.quote(model_config)}"
    f" model-type={shlex.quote(model_type)}"
    f" device={shlex.quote(device)}"
    f" score-threshold={score_threshold}"
  )
  if accumulate_past and int(accumulate_past) > 0:
    infer += f" accumulate-past={int(accumulate_past)}"
  parts += [
    "caps=application/octet-stream",
    "! queue max-size-buffers=2",
    f"! g3dlidarparse stride=1 frame-rate=0 point-features={int(point_features)}",
    infer,
    "! queue max-size-buffers=1",
    f"! gvametaconvert add-tensor-data={add_tensor_data} format=json",
    f"! gvametapublish method=file file-format=json-lines file-path={shlex.quote(fifo_path)}",
    "! fakesink sync=false",
  ]
  return parts


def camera_clip_path(
  data_root: str,
  sensor_id: str,
  start_index: int,
  stop_index: int | None,
  frame_rate: int,
) -> str:
  """Stable MPEG-TS path for a camera JPEG slice."""
  stop = "end" if stop_index is None else str(int(stop_index))
  return (
    f"{data_root.rstrip('/')}/{sensor_id}"
    f"/clip_{int(start_index)}_{stop}_{int(frame_rate)}fps.ts"
  )


def _resolve_stop_index(jpeg_dir: str, start_index: int, stop_index: int | None) -> int:
  if stop_index is not None:
    return int(stop_index)
  last = start_index
  for path in glob.glob(os.path.join(jpeg_dir, "*.jpg")):
    try:
      last = max(last, int(os.path.splitext(os.path.basename(path))[0]))
    except ValueError:
      continue
  return last


def ensure_camera_mpegts(
  *,
  jpeg_pattern: str,
  start_index: int,
  stop_index: int | None,
  frame_rate: int,
  out_path: str,
) -> str:
  """Fuse numbered JPEGs into an MPEG-TS clip at ``frame_rate`` (cached)."""
  jpeg_dir = os.path.dirname(jpeg_pattern) or "."
  stop = _resolve_stop_index(jpeg_dir, start_index, stop_index)
  first = jpeg_pattern % start_index
  if not os.path.isfile(first):
    raise FileNotFoundError(f"camera JPEG missing: {first}")
  parent = os.path.dirname(out_path)
  if parent:
    os.makedirs(parent, exist_ok=True)
  if os.path.isfile(out_path) and os.path.getmtime(out_path) >= os.path.getmtime(first):
    last = jpeg_pattern % stop
    if not os.path.isfile(last) or os.path.getmtime(out_path) >= os.path.getmtime(last):
      print(f"[radar-camera] reusing clip {out_path}", flush=True)
      return out_path

  n_frames = stop - start_index + 1
  print(
    f"[radar-camera] encoding {n_frames} JPEGs → {out_path} @ {frame_rate} fps",
    flush=True,
  )
  t0 = time.monotonic()
  tmp_path = out_path + ".partial"
  if os.path.exists(tmp_path):
    os.remove(tmp_path)

  from shutil import which  # pylint: disable=import-outside-toplevel
  ffmpeg = which("ffmpeg")
  if ffmpeg:
    cmd = [
      ffmpeg, "-y",
      "-framerate", str(int(frame_rate)),
      "-start_number", str(int(start_index)),
      "-i", jpeg_pattern,
      "-frames:v", str(int(n_frames)),
      "-c:v", "libx264",
      "-preset", "veryfast",
      "-crf", "28",
      "-x264opts", "keyint=10:min-keyint=10:scenecut=0",
      "-forced-idr", "1",
      "-pix_fmt", "yuv420p",
      "-an",
      "-f", "mpegts",
      tmp_path,
    ]
  else:
    cmd = [
      "gst-launch-1.0", "-q",
      "multifilesrc", f"location={jpeg_pattern}",
      f"start-index={int(start_index)}", f"stop-index={int(stop)}",
      "caps=image/jpeg",
      "!", "jpegdec",
      "!", "videoconvert",
      "!", "video/x-raw,format=I420",
      "!", "x264enc", "tune=zerolatency", "key-int-max=10",
      "speed-preset=veryfast",
      "!", "mpegtsmux",
      "!", "filesink", f"location={tmp_path}",
    ]

  proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
  if proc.returncode != 0 or not os.path.isfile(tmp_path):
    err = (proc.stderr or proc.stdout or "").strip()[-800:]
    if os.path.exists(tmp_path):
      os.remove(tmp_path)
    raise RuntimeError(f"camera clip encode failed ({proc.returncode}): {err}")
  os.replace(tmp_path, out_path)
  print(
    f"[radar-camera] wrote {out_path} in {time.monotonic() - t0:.1f}s",
    flush=True,
  )
  return out_path


def camera_sscape_parts(
  *,
  video_path: str,
  sensor_id: str,
  loop: bool,
  model: str,
  model_proc: str | None,
  device: str,
  score_threshold: float,
  detection_labels: str,
  ntp_server: str = "ntpserv",
) -> list[str]:
  """Established SceneScape camera chain (file → detect → MQTT + getimage).

  Mirrors ``queuing-config-no-rtsp.json`` / ``retail-config-no-rtsp.json``:
  ``sscape_post_inference_data_publish`` owns detection MQTT and annotated
  ``getimage`` replies from the same Gst buffer.
  """
  parts = [
    f"multifilesrc location={shlex.quote(video_path)}",
  ]
  if loop:
    parts.append("loop=true")
  safe = "".join(c if c.isalnum() else "_" for c in sensor_id)
  detect = (
    f"! gvadetect model={shlex.quote(model)} device={shlex.quote(device)}"
    f" threshold={score_threshold}"
  )
  if model_proc and str(model_proc).strip():
    detect += f" model-proc={shlex.quote(str(model_proc).strip())}"
  labels = (detection_labels or "").strip()
  publish = (
    f"! sscape_post_inference_data_publish name=datapublisher_{safe}"
    f" cameraid={shlex.quote(sensor_id)}"
    f" metadatagenpolicy=detectionPolicy"
    f" source=camera"
  )
  if labels:
    publish += f" detection-labels={shlex.quote(labels)}"
  parts += [
    f"name=source_{safe}",
    "! decodebin",
    "! videoconvert",
    "! video/x-raw,format=BGR",
    f"! sscape_timestamp_capture name=timesync_{safe}"
    f" ntp-server={shlex.quote(ntp_server)}"
    " use-frame-ntp-timestamp=false",
    detect,
    "! gvametaconvert add-tensor-data=true"
    f" name=metaconvert_{safe}",
    publish,
    "! gvametapublish name=destination_"
    f"{safe} method=file file-path=/dev/null",
    # DLSPS drains an appsink; bare gst-launch does not, so an appsink here
    # queues raw BGR frames without bound (~70 MB/s/cam) and OOMs the host.
    # sync=true keeps real-time pacing from the clip's 10 fps timestamps.
    "! fakesink sync=true",
  ]
  return parts
