# Copyright (C) 2021-2023 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

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
