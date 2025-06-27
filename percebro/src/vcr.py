# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import sys
import tempfile
import _thread
import pty
import subprocess

from scene_common import log

# Video Clip Recorder
class VCR:
  def __init__(self, url):
    self.url = url
    return

  def startCapture(self):
    # FIXME - is it a USB camera?
    self.recording = tempfile.NamedTemporaryFile(suffix=".mp4")
    cmd = ["ffmpeg", "-y", "-an", "-i", self.url, self.recording.name]
    log.debug("STARTING", cmd)
    _thread.start_new_thread(self.runCommand, (cmd, ))

    # FIXME - set a timer to stop automatically after a few minutes to prevent filling disk
    return

  def stopCapture(self):
    if getattr(self, 'controllingTTY', None) is not None:
      os.write(self.controllingTTY, b"q")
      log.debug("STOPPED", self.recording.name)
    return

  def runCommand(self, cmd):
    err = None
    self.controllingTTY, worker = pty.openpty()
    log.info(" ".join(cmd))
    with subprocess.Popen(cmd, stdin=worker, stdout=worker, stderr=worker,
                          close_fds=True) as p:
      m = os.fdopen(self.controllingTTY, "rb")
      os.close(worker)

      try:
        while True:
          c = list(m.read(1))[0]
          if c > 127:
            continue
          sys.stdout.write(chr(c))
          sys.stdout.flush()
      except OSError:
        pass

      os.close(self.controllingTTY)
      p.wait()
      err = p.returncode
      self.controllingTTY = None
    return err

  def publishVideo(self, pubsub, topic):
    if getattr(self, 'controllingTTY', None) is not None \
       or not hasattr(self, 'recording'):
      return

    pubsub.sendFile(topic, self.recording)
    return

  def publishVideoInNewThread(self, pubsub, topic):
    _thread.start_new_thread(self.publishVideo, (pubsub, topic, ))
    return
