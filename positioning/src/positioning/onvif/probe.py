# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Onboarding probe: verify a camera's ONVIF PTZ endpoint with the production poller.

Prints device identity, the selected PTZ profile, advertised absolute pan/tilt
spaces and event topics, then polls through `PTZPoller` and reports achieved rate,
round-trip/uncertainty statistics, and position range. Credentials are read from
`--credentials-file` or ONVIF_USERNAME/ONVIF_PASSWORD, never from the command line.

  python3 -m positioning.onvif.probe --host <ip> --port 80 --credentials-file creds.json
"""

import argparse
import json
import logging
import statistics
import sys
import threading
import time

from google.protobuf.json_format import MessageToDict

from positioning.onvif import OnvifError, OnvifPtzDevice, load_credentials
from positioning.onvif.soap import credentials_from_env
from positioning.ptz_poller import MOVE_STATUS_MODES, MoveEventMonitor, PTZPoller
from positioning.v1 import ptz_pb2


class _CollectingSink:
  def __init__(self, echo):
    self.samples = []
    self._echo = echo

  def submit_ptz_sample(self, sample):
    self.samples.append(sample)
    if self._echo:
      print(json.dumps(MessageToDict(sample, preserving_proto_field_name=True)), flush=True)
    return ptz_pb2.PTZSampleAck(result=ptz_pb2.PTZ_SAMPLE_RESULT_ACCEPTED,
                                accepted_sequence=sample.sequence)


def _percentile(values, fraction):
  ordered = sorted(values)
  return ordered[min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))]


def summarize(samples, duration_s, overruns):
  if not samples:
    return {"samples": 0}
  uncertainty_ms = [sample.timestamp_uncertainty_ns / 1e6 for sample in samples]
  timestamps = [sample.measured_at.ToNanoseconds() / 1e9 for sample in samples]
  intervals = [later - earlier for earlier, later in zip(timestamps, timestamps[1:])]
  move_counts = {}
  for sample in samples:
    name = ptz_pb2.ReportedMoveStatus.Name(sample.reported_move_status)
    move_counts[name] = move_counts.get(name, 0) + 1
  position = samples[-1].position
  return {
    "samples": len(samples),
    "achieved_rate_hz": round(len(samples) / duration_s, 2),
    "overrun_ticks": overruns,
    "interval_s": {"median": round(statistics.median(intervals), 4),
                   "max": round(max(intervals), 4)} if intervals else None,
    "uncertainty_ms": {"median": round(statistics.median(uncertainty_ms), 2),
                       "p95": round(_percentile(uncertainty_ms, 0.95), 2),
                       "max": round(max(uncertainty_ms), 2)},
    "pan": [min(s.position.pan for s in samples), max(s.position.pan for s in samples)],
    "tilt": [min(s.position.tilt for s in samples), max(s.position.tilt for s in samples)],
    "position_space": {"uri": position.position_space_uri,
                       "pan": [position.pan_min, position.pan_max],
                       "tilt": [position.tilt_min, position.tilt_max]},
    "reported_move_status": move_counts,
    "adapter_instance_id": samples[-1].adapter_instance_id,
  }


def build_argparser():
  parser = argparse.ArgumentParser(description=__doc__,
                                   formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("--host", required=True)
  parser.add_argument("--port", type=int, default=80)
  parser.add_argument("--scheme", choices=("http", "https"), default="http")
  parser.add_argument("--profile-token", default=None)
  parser.add_argument("--credentials-file", default=None,
                      help='JSON file {"username": ..., "password": ...}')
  parser.add_argument("--timeout", type=float, default=1.0, help="per-request timeout (s)")
  parser.add_argument("--poll-interval", type=float, default=0.2, help="poll interval (s)")
  parser.add_argument("--duration", type=float, default=10.0, help="polling duration (s)")
  parser.add_argument("--move-status", choices=MOVE_STATUS_MODES, default="get_status")
  parser.add_argument("--move-event-topic", default=None,
                      help="event topic prefix without namespace prefixes, e.g. PTZController/Move")
  parser.add_argument("--move-event-data-item", default="is_moving")
  parser.add_argument("--list-topics", action="store_true", help="print advertised event topics")
  parser.add_argument("--samples", action="store_true", help="print every PTZSample as JSON")
  return parser


def main(argv=None):
  args = build_argparser().parse_args(argv)
  logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(message)s")
  credentials = load_credentials(args.credentials_file) if args.credentials_file \
    else credentials_from_env()
  if credentials is None:
    print("Provide --credentials-file or ONVIF_USERNAME/ONVIF_PASSWORD", file=sys.stderr)
    return 2
  if args.move_status == "event" and not args.move_event_topic:
    print("--move-status event requires --move-event-topic", file=sys.stderr)
    return 2

  def factory():
    return OnvifPtzDevice(args.host, args.port, credentials, scheme=args.scheme,
                          timeout_s=args.timeout, profile_token=args.profile_token)

  device = factory()
  try:
    device.connect()
    info = device.get_device_information()
    report = {
      "device": vars(info),
      "clock_offset_s": round(device.soap.clock_offset_s, 3),
      "services": sorted(device.xaddrs),
      "profile_token": device.profile_token,
      "node_token": device.node_token,
      "default_pan_tilt_space": device.default_space_uri,
      "absolute_pan_tilt_spaces": [vars(space) for space in device.position_spaces],
    }
    if args.list_topics:
      report["event_topics"] = device.get_event_topics()
    print(json.dumps(report, indent=2), file=sys.stderr)
  except OnvifError as error:
    print(f"ONVIF connect failed: {error}", file=sys.stderr)
    return 1
  finally:
    device.close()

  monitor = None
  if args.move_event_topic:
    monitor = MoveEventMonitor("probe", factory, args.move_event_topic, args.move_event_data_item)
  sink = _CollectingSink(args.samples)
  poller = PTZPoller("probe", factory, sink, args.poll_interval, args.move_status, monitor)
  stop = threading.Event()
  workers = [threading.Thread(target=poller.run, args=(stop,), daemon=True)]
  if monitor is not None:
    workers.append(threading.Thread(target=monitor.run, args=(stop,), daemon=True))
  for worker in workers:
    worker.start()
  start = time.monotonic()
  try:
    stop.wait(args.duration)
  except KeyboardInterrupt:
    pass
  stop.set()
  for worker in workers:
    worker.join(5.0)
  summary = summarize(sink.samples, time.monotonic() - start, poller.overruns)
  print(json.dumps(summary, indent=2), file=sys.stderr)
  return 0 if sink.samples else 1


if __name__ == "__main__":
  sys.exit(main())
