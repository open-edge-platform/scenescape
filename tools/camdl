#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import argparse
import os
from urllib.parse import quote as percent_encode

import requests
from requests.auth import HTTPDigestAuth

from scene_common.timestamp import get_epoch_time, get_iso_time


def build_argparser():
  parser = argparse.ArgumentParser()
  parser.add_argument("camera", help="IP/hostname of camera")
  parser.add_argument("--auth", default="admin:admin123", help="user:pass to authenticate as")
  parser.add_argument("--flag", action="store_true", help="flag to do something")
  return parser

def main():
  args = build_argparser().parse_args()

  idx = args.auth.find(':')
  if idx < 0:
    print("Need both user and password separated by a colon for authentication")
    exit(1)

  user = args.auth[:idx]
  password = args.auth[idx+1:]

  auth = HTTPDigestAuth(user, password)
  cmd = "http://" + args.camera + "/cgi-bin/mediaFileFind.cgi?action=factory.create"
  factory = requests.get(cmd, auth=auth)
  factory = factory.text.split("=")[1].strip()

  now = get_epoch_time()
  start = now - 24 * 60 * 60
  ts_start = get_iso_time(start)
  ts_end = get_iso_time(now)

  cmd = "http://" + args.camera + "/cgi-bin/mediaFileFind.cgi" \
        "?action=findFile&object=%s&condition.Channel=0" \
        "&condition.StartTime=%s" \
        "&condition.EndTime=%s" % (factory, percent_encode(ts_start), percent_encode(ts_end))
  res = requests.get(cmd, auth=auth)

  cookies = {"DhWebClientSessionID": str(factory)}

  files = requests.get("http://" + args.camera + "/cgi-bin/mediaFileFind.cgi"
                       "?action=findNextFile&object=%s&count=99" % (factory),
                       auth=auth)

  for line in files.iter_lines():
    line = line.decode()
    if "FilePath" in line:
      path = line.split("=")[1].strip()
      cmd = "http://" + args.camera + "/RPC_Loadfile" + path
      print("Downloading [" + cmd + "]")
      resp = requests.get(cmd, auth=auth, cookies=cookies)
      with open("-".join(cmd.split(os.path.sep)[-6:]), "wb") as out:
        out.write(resp.content)

  cmd = "http://" + args.camera + "/cgi-bin/mediaFileFind.cgi" \
        "?action=close&object=%s" % (factory)
  ok = requests.get(cmd, auth=auth)

  return

if __name__ == "__main__":
  exit(main() or 0)

