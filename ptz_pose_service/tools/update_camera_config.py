#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Edit one camera's entry in ptz_pose_service/config/cameras.json.

Runs on the host (plain Python, no dependencies). Used by tune_ptz_camera.sh
to write measured values back to the config:

    update_camera_config.py config/cameras.json --camera-uid atag-ptzcam4 \\
        --set onvif_host='"192.168.0.94"' --merge /tmp/fit_result.json:config \\
        --unset pan_curve

``--set`` values are JSON. ``--merge FILE[:KEY]`` merges a JSON object from
FILE (or its KEY member). The entry is created if missing. Other entries and
their key order are kept.
"""

import argparse
import json
import sys


def build_argparser():
  parser = argparse.ArgumentParser(description=__doc__,
                                   formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("config")
  parser.add_argument("--camera-uid", required=True)
  parser.add_argument("--set", action="append", default=[], metavar="KEY=JSON")
  parser.add_argument("--merge", action="append", default=[], metavar="FILE[:KEY]")
  parser.add_argument("--unset", action="append", default=[], metavar="KEY")
  parser.add_argument("--get", metavar="KEY", help="print one value as JSON and exit")
  return parser


def dump(data):
  """Indented cameras list, with each field's value kept on one line."""
  cameras = []
  for entry in data["cameras"]:
    fields = ",\n".join(f"      {json.dumps(k)}: {json.dumps(v)}" for k, v in entry.items())
    cameras.append("    {\n" + fields + "\n    }")
  return '{\n  "cameras": [\n' + ",\n".join(cameras) + "\n  ]\n}\n"


def main():
  args = build_argparser().parse_args()
  with open(args.config, encoding="utf-8") as handle:
    data = json.load(handle)
  entry = next((c for c in data["cameras"] if c.get("scene_camera_uid") == args.camera_uid), None)

  if args.get:
    print(json.dumps(entry.get(args.get) if entry else None))
    return 0

  if entry is None:
    entry = {"scene_camera_uid": args.camera_uid}
    data["cameras"].append(entry)
  for item in args.set:
    key, _, value = item.partition("=")
    entry[key] = json.loads(value)
  for item in args.merge:
    path, _, key = item.partition(":")
    with open(path, encoding="utf-8") as handle:
      values = json.load(handle)
    entry.update(values[key] if key else values)
  for key in args.unset:
    entry.pop(key, None)

  with open(args.config, "w", encoding="utf-8") as handle:
    handle.write(dump(data))
  return 0


if __name__ == "__main__":
  sys.exit(main())
