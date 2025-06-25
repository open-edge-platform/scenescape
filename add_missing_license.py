# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import json
import subprocess
import pprint
import fileinput
import re
from pathlib import Path

json_file = 'reuse_lint.json'  # Change this to your JSON file path

with open(json_file, 'r') as f:
    data = json.load(f)

pprint.pp(data)

for item in data.get("non_compliant").get("missing_licensing_info", []):
    if item in data.get("non_compliant").get("missing_copyright_info", []):
        print(f"Adding license to {item}")
        add_license_to_file(item)
    else:
        for line in fileinput.input(item, inplace=True):
            if re.match(r'.*Copyright \(C\).*',line):
                print('{}'.format(line.replace("Copyright (C)","SPDX-FileCopyrightText: (C)")),end='') # for Python 3
            else:
                print('{}'.format(line),end='')
        add_license_to_file(item)

def add_license_to_file(file_path):

    if Path(file_path).suffix == '':
        print(f"File without extension: {file_path}")
        with open(file_path, 'a') as f:
            if f.readline() == "#!/usr/bin/env python3":
                subprocess.run(["make", "add-licensing", "FILE=" + item, "TEMPLATE=", "template-python"])
        # Assuming the file is a source code file, we can run the make command
        # to add licensing information.
    subprocess.run(["make", "add-licensing", "FILE=" + item])