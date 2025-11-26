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
import sys
from pathlib import Path

grammar_path = Path('Compile/grammar.py')
text = grammar_path.read_text()

replacements = {
  '    "uid":"""),\n    primitives.restler_fuzzable_string("fuzzstring", quoted=True),':
    '    "uid":"""),\n    primitives.restler_custom_payload_uuid4_suffix("scene_uid", quoted=True),',
  '    "name":"""),\n    primitives.restler_fuzzable_string("fuzzstring", quoted=True),':
    '    "name":"""),\n    primitives.restler_custom_payload_uuid4_suffix("scene_name", quoted=True),',
}

# Track successful replacements for validation
updated = text
replacements_made = 0
for source, target in replacements.items():
  if source in updated:
    updated = updated.replace(source, target)
    replacements_made += 1

# Validate that all expected replacements were made
if replacements_made < len(replacements):
  print(f"Warning: Only {replacements_made}/{len(replacements)} expected POST/uid replacements were made in grammar.py", file=sys.stderr)
  print("This may indicate RESTler's grammar format has changed.", file=sys.stderr)

# Handle PUT endpoint: replace first uid reference to use POST response value
# Only the first occurrence is replaced because the PUT endpoint should reuse
# the UID from the POST response. Additional uid references (if any) remain as custom payloads.
put_marker = '# Endpoint: /scene/{uid}, method: Put'
put_replacement_made = False
if put_marker in updated:
  marker_index = updated.index(put_marker)
  put_section = updated[marker_index:]
  replacement = 'primitives.restler_custom_payload_uuid4_suffix("scene_uid", quoted=True)'
  new_put_section = put_section.replace(
    replacement,
    'primitives.restler_static_string(_scene_post_uid.reader(), quoted=True)',
    1,  # Only replace first occurrence - PUT should use the UID from POST response
  )
  if new_put_section != put_section:
    updated = updated[:marker_index] + new_put_section
    put_replacement_made = True

if not put_replacement_made:
  print(f"Warning: PUT endpoint marker or uid replacement not found in grammar.py", file=sys.stderr)

# Only write if changes were made
if updated != text:
  grammar_path.write_text(updated)
  print(f"Grammar patching completed: {replacements_made} POST replacements, PUT replacement: {put_replacement_made}", file=sys.stderr)
else:
  print("Warning: No grammar replacements were made. Check if RESTler format has changed.", file=sys.stderr)
PY

/RESTler/restler/Restler $restler_mode --time_budget $time_budget_hours \
  --grammar_file Compile/grammar.py --dictionary_file Compile/dict.json --settings settings.json

# Set ownership of output directories to match host user (if running in Docker)
if [ -n "$USER_ID" ] && [ -n "$GROUP_ID" ]; then
    if ! chown -R $USER_ID:$GROUP_ID /workspace/Compile /workspace/Fuzz /workspace/RestlerLogs 2>/dev/null; then
        echo "Warning: Failed to change ownership of output directories to $USER_ID:$GROUP_ID" >&2
    fi
fi
