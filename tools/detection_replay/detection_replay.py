#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Inference-less camera pipelines: replay videos with recorded detections.

Runs one GStreamer pipeline with a branch per camera. Each branch decodes a
video file, attaches the camera's recorded detections to every frame
(sscape_detection_replay) and publishes them with the same SceneScape
elements as a detection-only DL Streamer Pipeline Server pipeline
(sscape_timestamp_capture, gvametaconvert, sscape_post_inference_data_publish).
SceneScape sees the usual camera data and Live View image topics.

All branches share the pipeline clock, so frame N of every camera is
published at the same time, and the files loop together until stopped.
Run it in the DL Streamer Pipeline Server image, which has GStreamer,
the GVA elements and gst-python.
"""

import argparse
import os
import shlex
import signal
import sys

SYNC_MODES = ("time", "frame")
# Same variable as DL Streamer Pipeline Server's run.sh: extra plugin
# directories, each holding Python elements in a "python" subdirectory.
PLUGIN_PATH_ENV = "ADDITIONAL_GST_PLUGIN_PATH"


def parse_args(argv=None):
  parser = argparse.ArgumentParser(
    description="Replay videos with recorded detections as SceneScape camera pipelines.")
  parser.add_argument(
    "--camera", nargs=3, action="append", required=True,
    metavar=("CAMERA_ID", "VIDEO", "METADATA"),
    help="Camera ID, its video file and its detection metadata (JSON Lines). Repeat per camera.")
  parser.add_argument(
    "--sync", choices=SYNC_MODES, default="time",
    help="Match frames to records by stream time (default) or by frame index.")
  parser.add_argument(
    "--detection-labels", default="",
    help="Comma-separated categories to publish; empty publishes all.")
  parser.add_argument(
    "--ntp-server", default="ntpserv",
    help="NTP server for frame timestamps; empty uses the system clock.")
  parser.add_argument("--mqtt-host", default=os.environ.get("MQTT_HOST", "broker.scenescape.intel.com"))
  parser.add_argument("--mqtt-port", type=int, default=int(os.environ.get("MQTT_PORT", "1883")))
  parser.add_argument(
    "--no-loop", dest="loop", action="store_false",
    help="Stop at the end of the videos instead of looping.")
  parser.add_argument(
    "--print-pipeline", action="store_true",
    help="Print the pipeline description and exit.")
  return parser.parse_args(argv)


def camera_branch(camera_id, video, metadata, args):
  """gst-launch description of one camera's branch."""
  quote = shlex.quote
  publisher = [
    "sscape_post_inference_data_publish",
    f"cameraid={quote(camera_id)}",
    "metadatagenpolicy=detectionPolicy",
    f"mqtt-host={quote(args.mqtt_host)}",
    f"mqtt-port={args.mqtt_port}",
  ]
  if args.detection_labels:
    publisher.append(f"detection-labels={quote(args.detection_labels)}")
  timestamp = ["sscape_timestamp_capture"]
  if args.ntp_server:
    timestamp.append(f"ntp-server={quote(args.ntp_server)}")
  return " ! ".join([
    f"filesrc location={quote(video)}",
    "decodebin",
    "videoconvert",
    "video/x-raw,format=BGR",
    # Release each frame at its presentation time, like a live camera, and
    # timestamp it right after.
    "identity sync=true",
    " ".join(timestamp),
    f"sscape_detection_replay metadata={quote(metadata)} sync-mode={args.sync}",
    "gvametaconvert add-tensor-data=true",
    " ".join(publisher),
    "fakesink sync=false async=false",
  ])


def pipeline_description(args):
  camera_ids = [camera_id for camera_id, _, _ in args.camera]
  if len(set(camera_ids)) != len(camera_ids):
    raise ValueError("Camera IDs must be unique")
  return " ".join(camera_branch(camera_id, video, metadata, args)
                  for camera_id, video, metadata in args.camera)


def _append_env_path(name, entries):
  current = os.environ.get(name)
  os.environ[name] = ":".join(([current] if current else []) + entries)


def extend_plugin_path():
  extra = [entry for entry in os.environ.get(PLUGIN_PATH_ENV, "").split(":") if entry]
  if not extra:
    return
  _append_env_path("GST_PLUGIN_PATH", extra)
  # The gst-python loader puts only one plugin "python" directory on sys.path,
  # so elements in the others could not import their helper modules. Python
  # in this process and in gst-plugin-scanner sees them all via PYTHONPATH.
  python_dirs = [os.path.join(entry, "python") for entry in extra]
  _append_env_path("PYTHONPATH", python_dirs)
  sys.path.extend(python_dirs)


def run(description, loop_videos):
  extend_plugin_path()
  import gi  # pylint: disable=import-outside-toplevel
  gi.require_version("Gst", "1.0")
  from gi.repository import GLib, Gst  # pylint: disable=import-outside-toplevel,no-name-in-module

  Gst.init(None)
  pipeline = Gst.parse_launch(description)
  main_loop = GLib.MainLoop()
  status = {"code": 0}

  def restart():
    # The sinks do not preroll (async=false), so the pipeline only takes a new
    # base time on PAUSED -> PLAYING; a flushing seek alone would replay the
    # next loop as fast as it decodes.
    pipeline.set_state(Gst.State.PAUSED)
    if not pipeline.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, 0):
      print("Failed to rewind the videos", file=sys.stderr)
      status["code"] = 1
      main_loop.quit()
      return GLib.SOURCE_REMOVE
    pipeline.set_state(Gst.State.PLAYING)
    return GLib.SOURCE_REMOVE

  def until_end_ms():
    # EOS follows the last frame's presentation time; the next loop starts
    # when that frame's duration has elapsed, keeping the frame interval.
    found, duration = pipeline.query_duration(Gst.Format.TIME)
    clock = pipeline.get_clock()
    if not found or clock is None:
      return 0
    running_time = clock.get_time() - pipeline.get_base_time()
    return max(0, (duration - running_time) // Gst.MSECOND)

  def on_message(_bus, message):
    if message.type == Gst.MessageType.EOS:
      if loop_videos:
        GLib.timeout_add(until_end_ms(), restart)
      else:
        main_loop.quit()
    elif message.type == Gst.MessageType.ERROR:
      error, debug = message.parse_error()
      print(f"Pipeline error from {message.src.get_name()}: {error.message}\n{debug}", file=sys.stderr)
      status["code"] = 1
      main_loop.quit()

  def on_signal():
    main_loop.quit()
    return GLib.SOURCE_REMOVE

  bus = pipeline.get_bus()
  bus.add_signal_watch()
  bus.connect("message", on_message)
  for signum in (signal.SIGINT, signal.SIGTERM):
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signum, on_signal)

  if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
    print("Failed to start the pipeline", file=sys.stderr)
    pipeline.set_state(Gst.State.NULL)
    return 1
  try:
    main_loop.run()
  finally:
    pipeline.set_state(Gst.State.NULL)
  return status["code"]


def main(argv=None):
  args = parse_args(argv)
  try:
    description = pipeline_description(args)
  except ValueError as error:
    print(error, file=sys.stderr)
    return 2
  if args.print_pipeline:
    print(description)
    return 0
  for _, video, metadata in args.camera:
    for path in (video, metadata):
      if not os.path.isfile(path):
        print(f"File not found: {path}", file=sys.stderr)
        return 2
  return run(description, args.loop)


if __name__ == "__main__":
  sys.exit(main())
