#!/usr/bin/python3

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import re
import sys
import time
from argparse import ArgumentParser
from shutil import which
from socket import getfqdn
from subprocess import DEVNULL, PIPE, STDOUT, Popen

import utils_streamer as my_utils

from scene_common.timestamp import get_epoch_time


def check_if_available(command):
  if which(command) is not None:
    return True
  return False

def build_argparser():
  parser = ArgumentParser()
  parser.add_argument("path", nargs="+", help="Path for video files to use")
  parser.add_argument("--verbose", "-v", action="store_true",  help="Get output from RTSP server started by the program")
  parser.add_argument("--size", "-s", default=None,
                      help="Frame size to be streamed (WxH)")
  parser.add_argument("--encoder", "-c", default='copy',
                      help="Output video encoder to use for streaming. (See ffmpeg -codecs)")
  parser.add_argument("--base_name", default=None,
                      help="Stream basename to use. Each stream will get a suffix id. By default will use the filename (without extension).")
  parser.add_argument("--server", default=None,
                      help="External RTSP server. If not specified, the program will start RTSP server")
  parser.add_argument("--start_id", default=1, type=int,
                      help="Camera id to start streaming at. Useful for when you already have another instance streaming and just want to add some more streams.")
  parser.add_argument("--extra", help="Extra parameters to pass to the transcoding session", default=None )

  return parser

streamer_procs = []
def stream_videos(videos, start_idx=1, size=None, out_encoder='copy', rtsp_server_name='127.0.0.1', extra_args=None, base_name=None):
  commands = []
  rtspAddressBase=8554

  stream_names = []
  for vid in videos:

    cur_stream_name = ''
    if base_name is not None:
      cur_stream_name = base_name + str(start_idx)
      start_idx += 1
    else:
      _, tail = os.path.split(vid)
      fname, ext  = os.path.splitext(tail)

      test_name = fname
      while test_name in stream_names:
        test_name = fname + str(start_idx)
        start_idx += 1
      cur_stream_name = test_name

    stream_names.append( cur_stream_name )

    detected_fps = stream_get_fps( vid )
    rtsp_cmd = 'rtsp://' + rtsp_server_name + ':' + str(rtspAddressBase) + '/' + cur_stream_name

    print( "Video {} at URI: {} at {} fps".format( vid, rtsp_cmd, detected_fps ))

    command_extract = ['ffmpeg', '-stream_loop', '-1', '-i', vid, '-fflags', '+genpts', '-r', str(detected_fps), '-c:v', 'copy', '-an', '-f', 'mpegts', 'pipe:1'  ]
    command_stream  = ['ffmpeg', '-re', '-f', 'mpegts', '-i', 'pipe:0' , '-fflags', '+genpts', '-r', str(detected_fps), '-c:v', out_encoder ]

    if size is not None:
      command_stream.extend(['-s', size])

    command_extract.extend(['-loglevel', 'error'])
    command_stream.extend(['-loglevel', 'error'])

    if extra_args is not None:
      extras_arr = extra_args.split(' ')
      for i in extras_arr:
        command_stream.append(i)

    command_stream.extend(['-f', 'rtsp', '-rtsp_transport', 'tcp', rtsp_cmd ])

    commands.append([command_extract, command_stream])

  for extract, stream  in commands:
    extract_process = Popen(extract, stdout=PIPE)
    streamer_process = Popen(stream, stdin=extract_process.stdout)
    extract_process.stdout.close()
    streamer_procs.append([extract_process, streamer_process])


def run_command(command, wait=True):
  cmd_proc = Popen(command, stdout=PIPE, stderr=STDOUT, universal_newlines=True)
  cmd_out  = cmd_proc.communicate()[0]
  cmd_proc.stdout.close()
  cmd_proc.wait()
  return cmd_out

def wait_for_streamers():
  for extract, stream in streamer_procs:
    extract.wait()
    stream.wait()

def wait_for_command( command, expected=None, not_expected=None, max_time=10 ):
  command_success = False
  start = get_epoch_time()
  while command_success == False:
    output = run_command(command)

    if expected is not None and expected in output:
      command_success = True
      break

    if not_expected is not None and not_expected not in output:
      command_success = True
      break

    now = get_epoch_time()
    if now - start > max_time:
      break
    else:
      time.sleep(1)

  return command_success

rtsp_container_name = 'rtsp-streamer-server'
def start_rtsp(verbose=False):
  server_name = None
  image_name = 'aler9/rtsp-simple-server'
  command = ['docker', 'pull', image_name]
  run_command(command)

  command = ['docker', 'run', '--rm', '--network=host', '--name', rtsp_container_name, image_name ]

  if verbose:
    Popen(command)
  else:
    Popen(command, stderr=DEVNULL, stdout=DEVNULL)

  rtsp_server_ok = wait_for_command( ['docker','logs',rtsp_container_name], expected='listener opened on :8554', max_time=10 )

  if rtsp_server_ok:
    server_name = getfqdn() or '127.0.0.1'

  return server_name

def stop_rtsp(forced=False):
  #Sometimes the rtsp container catches the Ctrl+C, so it could be dead already
  rtsp_killed = wait_for_command(['docker','ps'], not_expected=rtsp_container_name, max_time=2 )

  if not rtsp_killed:
    command = ['docker', 'kill', rtsp_container_name ]
    Popen(command, stderr=None, stdout=None).wait()

def stop_streamers():
  for extract,stream in streamer_procs:
    extract.stdout.close()
    extract.kill()
    stream.kill()

def stream_get_fps(stream_file):
  stream_fps = 30
  stream_info_out = run_command( ['ffmpeg', '-i', stream_file ] )

  stream_info_out = stream_info_out.split('\n')
  for line in stream_info_out:
    if 'fps' in line:

      matchstr = re.search(r", (\d*\.*\d+) fps,", line )
      if matchstr is not None:
        stream_fps = float(matchstr.group(1))

  return stream_fps

def main(argv, arc):
  args = build_argparser().parse_args()
  server_started = False

  if check_if_available("ffmpeg") == False:
    print("RTSP Server requires ffmpeg to be installed locally.")
    return 1

  if args.path is None:
    print("RTSP Server requires path to video files or folder.")
    return 1

  videos = []

  for i in args.path:
    if os.path.exists(i):
      if os.path.isdir(i):
        dir_videos = my_utils.find_videos(i)
        for video_file in dir_videos:
          videos.append(video_file)
      elif my_utils.known_video_type(i):
        videos.append(i)

    else:
      print("Invalid path {} specified".format(i))

  if len(videos) == 0:
    print("No video with valid extensions could be found in the provided path")
    return 1

  print( "Video file list: {}".format(videos))

  try:
    rtsp_server_name = args.server

    if rtsp_server_name is None:
      rtsp_server_name = start_rtsp(args.verbose)
      server_started = (rtsp_server_name is not None)
      if not server_started:
        print( "Failed opening RTSP server!" )
        return 1

    stream_videos(videos, start_idx=args.start_id, rtsp_server_name=rtsp_server_name, size=args.size, out_encoder=args.encoder, extra_args=args.extra, base_name=args.base_name)
    wait_for_streamers()
  except Exception as e:
    print("Error raised: ", e)
    return 1
  finally:
    print( "Exiting" )
    #Some bad commands to ffmpeg cause streamers to exit, so ensuring to take down the rtsp server.
    if server_started:
      stop_rtsp()
    stop_streamers()

  return 0

if __name__ == '__main__':
  main(sys.argv, len(sys.argv))
