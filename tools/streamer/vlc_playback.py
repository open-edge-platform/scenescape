#!/usr/bin/python3
# Copyright (C) 2021 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

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
