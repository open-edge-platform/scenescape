#!/usr/bin/python3

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import sys
from subprocess import Popen

import utils_streamer as my_utils


def stream_videos(video_count):
  commands = []
  current_cmd = 0
  rtspAddressBase = 8554

  while current_cmd < video_count:
    rtsp_cmd = 'rtsp://127.0.0.1:' + str(rtspAddressBase) + '/cam' + str(current_cmd)
    command = ['vlc', '--no-embedded-video', '--width', '640', '--height', '480', rtsp_cmd]
    commands.append(command)
    current_cmd += 1
    rtspAddressBase += 2

  procs = [ Popen(i) for i in commands ]
  for p in procs:
    p.wait()


def main(argv, arc):
  if arc != 2:
    print("Full absolute path to video  folder should be provided")
  else:
    videos = my_utils.find_videos(argv[1])
    if len(videos) == 0:
      print("No video with valid extentions could be found in the provided directory")
    else:
      stream_videos(len(videos))

if __name__ == '__main__':
  main(sys.argv, len(sys.argv))
