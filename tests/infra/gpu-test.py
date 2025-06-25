#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os

from percebro.detector import Detector

def main():
  infeng = Detector(asynchronous=True, distributed=False)
  infeng.setParameters("retail", "GPU", None, 0.8, 4, False)
  return

if __name__ == '__main__':
  os._exit(main() or 0)
