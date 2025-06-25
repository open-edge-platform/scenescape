# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import json
import subprocess
import pprint
import fileinput
import re

json_file = 'reuse_lint.json'  # Change this to your JSON file path

with open(json_file, 'r') as f:
    data = json.load(f)

pprint.pp(data)

for item in data.get("non_compliant").get("missing_licensing_info", []):
    if item in data.get("non_compliant").get("missing_copyright_info", []):
        print(f"Adding license to {item}")
        subprocess.run(["make", "add-licensing", "FILE=" + item])
    else:
        for line in fileinput.input(item, inplace=True):
            if re.match(r'.*Copyright \(C\).*',line):
                print('{}'.format(line.replace("Copyright (C)","SPDX-FileCopyrightText: (C)")),end='') # for Python 3
            else:
                print('{}'.format(line),end='')
        subprocess.run(["make", "add-licensing", "FILE=" + item])