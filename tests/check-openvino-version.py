#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import re
import subprocess

import common_test_utils as common

TEST_NAME = "NEX-T10407"

def main():
  print("Executing:", TEST_NAME)

  exit_code = 1
  try:
    package_name = "openvino"
    proc = subprocess.Popen(["pip index versions " + package_name], stdout=subprocess.PIPE, shell=True)
    (proc_output, err) = proc.communicate()

    proc_output = proc_output.decode()
    pattern = r"^\s\s([A-Z]+):\s+(\d\d\d\d.\d.\d)$"
    matches = re.findall(pattern, proc_output, re.MULTILINE)

    label_1 = matches[0][0]
    label_1_value = matches[0][1]
    label_2 = matches[1][0]
    label_2_value = matches[1][1]

    print()
    output_str = "{label} {package} version: {value}"
    print(output_str.format(label=label_1, package=package_name, value=label_1_value))
    print(output_str.format(label=label_2, package=package_name, value=label_2_value))

    assert len(matches) == 2
    assert label_1 == "INSTALLED"
    assert label_2 == "LATEST"
    assert label_1_value == label_2_value
    exit_code = 0

  finally:
    common.record_test_result(TEST_NAME, exit_code)

  return exit_code

if __name__ == '__main__':
  exit(main() or 0)
