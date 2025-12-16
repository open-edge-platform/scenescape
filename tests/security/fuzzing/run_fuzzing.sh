#!/bin/bash

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -e

cd /workspace
. .env

echo "$instance_ip web.scenescape.intel.com" >> /etc/hosts

cp token /tmp
auth_token=$(curl -s "https://web.scenescape.intel.com/api/v1/auth" \
  -d "username=$auth_username&password=$auth_password" | jq -r '.token')
sed -i "s/##TOKEN##/$auth_token/" /tmp/token

rm -rf Compile Fuzz RestlerLogs

/RESTler/restler/Restler compile --api_spec fuzzing_openapi.yaml

python3 - <<'PY'
import json
from pathlib import Path

compiled_path = Path("Compile/dict.json")
custom_path   = Path("custom_dict.json")

compiled = json.loads(compiled_path.read_text())
custom   = json.loads(custom_path.read_text())

compiled.update(custom)

compiled_path.write_text(json.dumps(compiled, indent=2) + "\n")
print("dictionary merged")
PY

python3 - <<'PY'
from pathlib import Path
import re

grammar_path = Path("Compile/grammar.py")
text = grammar_path.read_text()

def fix_three_number_array(section: str) -> str:
    """
    Replace:
        [
            primitives.restler_fuzzable_number(...)
    With:
        [
            fuzz1, fuzz2, fuzz3
    """
    # We match the array opening and first fuzzable number
    pattern = re.compile(
        r'"mesh_(rotation|scale)"\s*:\s*\[\s*"""\),\s*primitives\.restler_fuzzable_number\(.*?\)',
        re.DOTALL
    )

    def repl(match):
        field = f'mesh_{match.group(1)}'
        return f'''
    "{field}":
    [
        """),
    primitives.restler_fuzzable_number("1.0"),
    primitives.restler_static_string(", "),
    primitives.restler_fuzzable_number("2.0"),
    primitives.restler_static_string(", "),
    primitives.restler_fuzzable_number("3.0")
'''

    return pattern.sub(repl, section)

text = text.replace(
    'primitives.restler_fuzzable_string("fuzzstring", quoted=True)',
    'primitives.restler_custom_payload_uuid4_suffix("scene_name", quoted=True)'
)

# Patch POST
post_marker = "# Endpoint: /scene, method: Post"
if post_marker in text:
    start = text.index(post_marker)
    end = text.find("# Endpoint:", start + 1)
    if end == -1:
        end = len(text)
    block = text[start:end]
    fixed = fix_three_number_array(block)
    text = text[:start] + fixed + text[end:]

# Patch PUT
put_marker = "# Endpoint: /scene/{uid}, method: Put"
if put_marker in text:
    start = text.index(put_marker)
    end = text.find("# Endpoint:", start + 1)
    if end == -1:
        end = len(text)
    block = text[start:end]
    fixed = fix_three_number_array(block)
    text = text[:start] + fixed + text[end:]

text = text.replace(
    'primitives.restler_custom_payload_uuid4_suffix("scene_uid", quoted=True)',
    'primitives.restler_static_string(_scene_post_uid.reader(), quoted=True)',
    1
)

grammar_path.write_text(text)
print("grammar.py patched successfully")
PY

/RESTler/restler/Restler $restler_mode \
  --time_budget $time_budget_hours \
  --grammar_file Compile/grammar.py \
  --dictionary_file Compile/dict.json \
  --settings settings.json

if [ -n "$USER_ID" ] && [ -n "$GROUP_ID" ]; then
    chown -R $USER_ID:$GROUP_ID /workspace/Compile /workspace/Fuzz /workspace/RestlerLogs 2>/dev/null || true
fi

echo "RESTler fuzzing run completed"
