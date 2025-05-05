#!/usr/bin/env python3

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

import os

from percebro.detector import Detector

def main():
  infeng = Detector(asynchronous=True, distributed=False)
  infeng.setParameters("retail", "GPU", None, 0.8, 4, False)
  return

if __name__ == '__main__':
  os._exit(main() or 0)
