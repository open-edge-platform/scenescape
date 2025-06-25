#!/usr/bin/env python3
#
# Copyright (C) 2022-2025 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import subprocess
import time
import os
import sys

TEST_NAME = "NEX-T12520"
TIME_LIMIT_SECONDS = 600

def main():

    print("Starting build process... ")
    start_time = time.time()

    process = subprocess.Popen(
        ['make', 'FOLDERS=autocalibration broker controller manager model_installer'],
        cwd=os.getcwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    for line in process.stdout:
        print(line, end='')

    process.wait()
    duration = time.time() - start_time
    print(f"Build completed in {duration:.2f} seconds.")

    if duration < TIME_LIMIT_SECONDS:
        print(TEST_NAME + ": PASS")
        return 0
    else:
        print(f"Build took too long: {duration:.2f} seconds (limit is {TIME_LIMIT_SECONDS} seconds)")
        print(TEST_NAME + ": FAIL")
        return 1

if __name__ == '__main__':
  exit(main() or 0)
