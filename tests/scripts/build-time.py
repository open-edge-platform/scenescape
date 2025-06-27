#!/usr/bin/env python3
#
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import argparse
import os
import subprocess
import time

def run_command(command, description, timed=False):
    print(f"Running {description} command: {command}")
    start_time = time.time() if timed else None
    
    process = subprocess.Popen(
        command,
        cwd=os.getcwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        shell=True # this is needed to run clean-cmd
    )
    
    for line in process.stdout:
        print(line, end='')
        
    process.wait()
    
    if process.returncode != 0:
        print(f"{description} command failed with exit code: {process.returncode}")
        return False, 0.0
    
    duration = time.time() - start_time if timed else 0.0
    
    return True, duration

def main():
    parser = argparse.ArgumentParser(description="Clean environment and measure build time.")
    parser.add_argument("--time-limit", type=int, required=True, help="Time limit in seconds")
    parser.add_argument("--clean-cmd", default="make clean-all", help="Clean command to run before build")
    parser.add_argument("--build-cmd", default="make build-all", help="Build command to measure")
    parser.add_argument("--test-name", required=True, help="Name of the test")
    
    args = parser.parse_args()
    
    # runs clean commands, not timed
    success, _ = run_command(args.clean_cmd, "clean", timed=False)
    if not success:
        print(f"{args.test_name}: FAIL")
        return 1
    
    # runs build command, timed
    success, duration = run_command(args.build_cmd, "build", timed=True)
    if not success:
        print(f"{args.test_name}: FAIL")
        return 1
    
    print(f"Build completed in {duration:.2f} seconds.")

    if duration < args.time_limit:
        print(args.test_name + ": PASS")
        return 0
    else:
        print(f"Build took too long: {duration:.2f} seconds (limit is {args.time_limit} seconds)")
        print(args.test_name + ": FAIL")
        return 1

if __name__ == '__main__':
  exit(main() or 0)
  