#!/bin/bash

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

cd /workspace

. .env

echo "$instance_ip web.scenescape.intel.com" >> /etc/hosts

cp token /tmp
auth_token=$(curl "https://web.scenescape.intel.com/api/v1/auth" -d "username=$auth_username&password=$auth_password" | jq -r '.token')
sed -i "s/##TOKEN##/$auth_token/" /tmp/token

# Clean up old compilation
rm -rf Compile Fuzz RestlerLogs

/RESTler/restler/Restler compile --api_spec fuzzing_openapi.yaml

# Merge custom dictionary with compiled dictionary
python3 - <<'PY'
import json
from pathlib import Path

compiled_path = Path('Compile/dict.json')
custom_path = Path('custom_dict.json')

compiled = json.loads(compiled_path.read_text())
custom = json.loads(custom_path.read_text())

compiled.update(custom)

compiled_path.write_text(json.dumps(compiled, indent=2) + '\n')
PY

# Patch generated grammar so scene identifiers use UUID suffix payloads
python3 - <<'PY'
from pathlib import Path

grammar_path = Path('Compile/grammar.py')
text = grammar_path.read_text()

replacements = {
  '    "uid":"""),\n    primitives.restler_fuzzable_string("fuzzstring", quoted=True),':
    '    "uid":"""),\n    primitives.restler_custom_payload_uuid4_suffix("scene_uid", quoted=True),',
  '    "name":"""),\n    primitives.restler_fuzzable_string("fuzzstring", quoted=True),':
    '    "name":"""),\n    primitives.restler_custom_payload_uuid4_suffix("scene_name", quoted=True),',
}

updated = text
for source, target in replacements.items():
  if source in updated:
    updated = updated.replace(source, target)

put_marker = '# Endpoint: /scene/{uid}, method: Put'
if put_marker in updated:
  marker_index = updated.index(put_marker)
  put_section = updated[marker_index:]
  replacement = 'primitives.restler_custom_payload_uuid4_suffix("scene_uid", quoted=True)'
  new_put_section = put_section.replace(
    replacement,
    'primitives.restler_static_string(_scene_post_uid.reader(), quoted=True)',
    1,
  )
  updated = updated[:marker_index] + new_put_section

if updated != text:
  grammar_path.write_text(updated)
PY

/RESTler/restler/Restler $restler_mode --time_budget $time_budget_hours \
  --grammar_file Compile/grammar.py --dictionary_file Compile/dict.json --settings settings.json

if [ -n "$USER_ID" ] && [ -n "$GROUP_ID" ]; then
    chown -R $USER_ID:$GROUP_ID /workspace/Compile /workspace/Fuzz /workspace/RestlerLogs 2>/dev/null || true
fi
