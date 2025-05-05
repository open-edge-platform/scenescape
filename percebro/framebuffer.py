# Copyright (C) 2023-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

from threading import Lock

class FrameBuffer:
  def __init__(self):
    self.buffer = [None]*2
    self.next_idx = 0
    self.last_idx = 1
    self.lock = Lock()
    return

  def addFrame(self, frame):
    with self.lock:
      self.buffer[self.next_idx] = frame
      # Swap the indices
      self.next_idx, self.last_idx = self.last_idx, self.next_idx
    return

  def getFrame(self):
    with self.lock:
      return self.buffer[self.last_idx]
