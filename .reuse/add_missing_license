#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import json
import subprocess
import fileinput
import re
from pathlib import Path

def add_license_to_file(file_path):
  if Path(file_path).suffix == '':
    with open(file_path, 'r') as f:
      first_line = f.readline().strip()
      if first_line == "#!/usr/bin/env python3" or first_line == "#!/bin/bash":
        subprocess.run(["make", f"add-licensing", "FILE=" + file_path, "ADDITIONAL_LICENSING_ARGS=" + "\"--style=python\""])
      else:
        subprocess.run(["make", "add-licensing", "FILE=" + file_path])
  elif Path(file_path).suffix == '.template':
    subprocess.run(["make", f"add-licensing", "FILE=" + file_path, "ADDITIONAL_LICENSING_ARGS=" + "\"--style=python\""])
  elif "Dockerfile" in file_path or "Makefile" in file_path:
    subprocess.run(["make", "add-licensing", "FILE=" + file_path, "ADDITIONAL_LICENSING_ARGS=" + "\"--style=python\""])
  else:
    subprocess.run(["make", "add-licensing", "FILE=" + file_path])

REUSE_REPORT = subprocess.run(["reuse", "lint", "-j"], capture_output=True, text=True).stdout

data = json.loads(REUSE_REPORT)

for item in data.get("non_compliant").get("missing_licensing_info", []):
  if item in data.get("non_compliant").get("missing_copyright_info", []):
    add_license_to_file(item)
  else:
    for line in fileinput.input(item, inplace=True):
      if re.match(r'.*Copyright \(C\).*',line):
        print('{}'.format(line.replace("Copyright (C)","SPDX-FileCopyrightText: (C)")),end='')
      else:
        print('{}'.format(line),end='')
    add_license_to_file(item)
