# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

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
