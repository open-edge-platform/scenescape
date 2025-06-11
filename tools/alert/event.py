# Copyright (C) 2020-2023 Intel Corporation
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

class Event:
  def __init__(self, info):
    self.counts = info['counts']
    self.region = info['region_name']
    self.objects = info['objects']
    self.timestamp = info['timestamp']
    self.when = get_epoch_time(self.timestamp)
    return

  def priority(self, config):
    pri = None
    p_region = self.region
    if p_region not in config['regions']:
      p_region = 'default'
    if p_region in config['regions'] and 'priority' in config['regions'][p_region]:
      priorities = config['regions'][p_region]['priority']
      for otype in priorities:
        opri = config['regions'][p_region]['priority'][otype]
        if otype in self.counts:
          count = self.counts[otype]
          if count > 0 and (pri is None or opri > pri):
            pri = opri
    return pri

  def tone(self, config):
    tone = None
    if self.region in config['regions']:
      tone = config['regions'][self.region]['sound']
    elif 'default' in config['regions']:
      tone = config['regions']['default']['sound']
    return tone

  def __repr__(self):
    return "%s: counts: %s  region: %s  objects: %s  timestamp: %s  when: %s" % \
      (self.__class__.__name__, self.counts, self.region, self.objects,
       self.timestamp, self.when)
