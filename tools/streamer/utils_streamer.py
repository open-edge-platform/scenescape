#!/usr/bin/python3

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os


def known_video_type(filepath):
  extensions = ['.mov', '.avi', '.mpg', '.mkv', '.mp4']
  length = len(extensions)
  i = 0
  while i < length:
    if filepath.lower().endswith(extensions[i]):
      return True
    i += 1
  return False

def find_videos(path):
  files = []

  list_files = os.listdir(path)

  for val in list_files:
    if known_video_type(val):
      files.append(os.path.join(path, val))

  return files

