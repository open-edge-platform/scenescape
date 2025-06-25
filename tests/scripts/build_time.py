#!/usr/bin/env python3
#
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import subprocess
import time
import os

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
    if process.returncode != 0:
        print("Build failed with exit code:", process.returncode)
        print(TEST_NAME + ": FAIL")
        return 1
    
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