# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from scene_common.timestamp import get_epoch_time

class Region:
  def __init__(self, info, rname):
    self.region = rname
    self.objects = info['objects']
    for obj in self.objects:
      for rname in obj['regions']:
        r = obj['regions'][rname]
        r['entered_epoch'] = get_epoch_time(r['entered'])
    self.timestamp = info['timestamp']
    self.when = get_epoch_time(self.timestamp)
    return
