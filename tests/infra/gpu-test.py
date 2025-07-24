#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os

from percebro.detector import Detector

def main():
  infeng = Detector(asynchronous=True, distributed=False)
  infeng.setParameters("retail", "GPU", None, 0.8, 4, False)
  return

if __name__ == '__main__':
  os._exit(main() or 0)
