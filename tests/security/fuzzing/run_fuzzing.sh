#!/bin/bash

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -e

cd /workspace
. .env

workspace_root="$(pwd)"
run_dir="${workspace_root}/service_runs/manager"
mode_dir="$(tr '[:lower:]' '[:upper:]' <<< "${restler_mode:0:1}")${restler_mode:1}"
result_dir="${workspace_root}/${mode_dir}/manager"

rm -rf "$run_dir" "$result_dir" "${workspace_root}/RestlerLogs/manager"
mkdir -p "$run_dir" "${workspace_root}/RestlerLogs/manager"
cp fuzzing_openapi.yaml custom_dict.json settings.json .env token "$run_dir"/
cd "$run_dir"

echo "$instance_ip web.scenescape.intel.com" >> /etc/hosts

cp token /tmp
auth_token=$(curl -s "https://web.scenescape.intel.com/api/v1/auth" \
  -d "username=$auth_username&password=$auth_password" | jq -r '.token')
sed -i "s/##TOKEN##/$auth_token/" /tmp/token

rm -rf Compile Fuzz Fuzz-lean RestlerLogs Test

# Create a dedicated "child" scene before RESTler runs so we have two distinct
# valid scene UUIDs for POST /child (parent != child is enforced by the API).
# Use a unique timestamped name so each run creates a fresh scene.
child_scene_name="fuzzing-child-$(date +%s)"
child_scene_uid=$(curl -s "https://web.scenescape.intel.com/api/v1/scene" \
  -H "Authorization: Token $auth_token" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$child_scene_name\"}" | jq -r '.uid // empty') || true
export FUZZING_CHILD_SCENE_UID="$child_scene_uid"

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

def get_endpoint_block(source: str, marker: str):
    if marker not in source:
        return None, None, None
    start = source.index(marker)
    end = source.find("# Endpoint:", start + 1)
    if end == -1:
        end = len(source)
    return start, end, source[start:end]

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

def patch_scene_and_points_in_post(marker: str):
    global text
    start, end, block = get_endpoint_block(text, marker)
    if block is None:
        return

    block = block.replace(
        'primitives.restler_static_string(""",\n    "scene":"""),\n    primitives.restler_custom_payload_uuid4_suffix("scene_name", quoted=True),',
        'primitives.restler_static_string(""",\n    "scene":"""),\n    primitives.restler_static_string(_scene_post_uid.reader(), quoted=True),'
    )

    block = block.replace(
        'primitives.restler_static_string(""",\n    "points":\n    [\n        [\n            """),\n    primitives.restler_fuzzable_number("1.23"),\n    primitives.restler_static_string("""\n        ]\n    ]}"""),',
        'primitives.restler_static_string(""",\n    "points":\n    [\n        [\n            """),\n    primitives.restler_fuzzable_number("1.23"),\n    primitives.restler_static_string(", "),\n    primitives.restler_fuzzable_number("4.56"),\n    primitives.restler_static_string("""\n        ]\n    ]}"""),'
    )

    text = text[:start] + block + text[end:]

def patch_string_field_dependency_in_post(marker: str, field_name: str, dependency_expr: str):
    global text
    start, end, block = get_endpoint_block(text, marker)
    if block is None:
        return

    pattern = re.compile(
        rf'(primitives\.restler_static_string\(""",\\n\s*"{field_name}":"""\),\n\s*)'
        r'primitives\.[^\n]+,'
    )
    block = pattern.sub(
        rf'\1primitives.restler_static_string({dependency_expr}, quoted=True),',
        block,
    )

    text = text[:start] + block + text[end:]

def patch_points_to_2d(marker: str):
    global text
    start, end, block = get_endpoint_block(text, marker)
    if block is None:
        return

    block = block.replace(
        'primitives.restler_static_string(""",\\n    "points":\\n    [\\n        [\\n            """),\\n    primitives.restler_fuzzable_number("1.23"),\\n    primitives.restler_static_string("""\\n        ]\\n    ]}"""),',
        'primitives.restler_static_string(""",\\n    "points":\\n    [\\n        [\\n            """),\\n    primitives.restler_fuzzable_number("1.23"),\\n    primitives.restler_static_string(", "),\\n    primitives.restler_fuzzable_number("4.56"),\\n    primitives.restler_static_string("""\\n        ]\\n    ]}"""),'
    )

    text = text[:start] + block + text[end:]

def patch_post_scene_uuid_dependency(marker: str):
    global text
    start, end, block = get_endpoint_block(text, marker)
    if block is None:
        return

    block = block.replace(
        'primitives.restler_fuzzable_uuid4("566048da-ed19-4cd3-8e0a-b7e0e1ec4d72", quoted=True),',
        'primitives.restler_static_string(_scene_post_uid.reader(), quoted=True),'
    )

    text = text[:start] + block + text[end:]

def patch_camera_sensor_dependency(marker: str):
    global text
    start, end, block = get_endpoint_block(text, marker)
    if block is None:
        return

    block = block.replace(
        'primitives.restler_static_string(""",\n    "sensor_id":"""),\n    primitives.restler_custom_payload_uuid4_suffix("scene_name", quoted=True),',
        'primitives.restler_static_string(""",\n    "sensor_id":"""),\n    primitives.restler_static_string(_sensor_post_sensor_id.reader(), quoted=True),'
    )

    text = text[:start] + block + text[end:]

patch_scene_and_points_in_post("# Endpoint: /region, method: Post")
patch_scene_and_points_in_post("# Endpoint: /tripwire, method: Post")
patch_string_field_dependency_in_post("# Endpoint: /sensor, method: Post", "scene", "_scene_post_uid.reader()")
patch_string_field_dependency_in_post("# Endpoint: /camera, method: Post", "scene", "_scene_post_uid.reader()")
patch_post_scene_uuid_dependency("# Endpoint: /sensor, method: Post")
patch_post_scene_uuid_dependency("# Endpoint: /camera, method: Post")
patch_post_scene_uuid_dependency("# Endpoint: /child, method: Post")
patch_post_scene_uuid_dependency("# Endpoint: /calibrationmarker, method: Post")
# Step 1: set child field to _scene_post_uid (different call than parent which
# patch_post_scene_uuid_dependency already handled via the first uuid4 match).
patch_string_field_dependency_in_post("# Endpoint: /child, method: Post", "child", "_scene_post_uid.reader()")

# Step 2: override the child field with a pre-created scene UID so parent != child.
# FUZZING_CHILD_SCENE_UID is exported in bash before RESTler starts.
import os
child_scene_uid = os.environ.get("FUZZING_CHILD_SCENE_UID", "")
if child_scene_uid:
    start, end, block = get_endpoint_block(text, "# Endpoint: /child, method: Post")
    if block is not None:
        block = block.replace(
            f'primitives.restler_static_string(_scene_post_uid.reader(), quoted=True),\n    primitives.restler_static_string(""",\n    "child_type":',
            f'primitives.restler_static_string("{child_scene_uid}", quoted=True),\n    primitives.restler_static_string(""",\n    "child_type":',
        )
        text = text[:start] + block + text[end:]
patch_points_to_2d("# Endpoint: /region/{uid}, method: Put")
patch_points_to_2d("# Endpoint: /tripwire/{uid}, method: Put")

# /video and /frame use the camera query param; wire it to the created camera ID.
def patch_camera_query_param(marker: str):
    global text
    start, end, block = get_endpoint_block(text, marker)
    if block is None:
        return

    block = block.replace(
        'primitives.restler_fuzzable_string("fuzzstring", quoted=False),\n    primitives.restler_static_string(" HTTP/1.1\\r\\n"),',
        'primitives.restler_static_string(_camera_post_sensor_id.reader(), quoted=False),\n    primitives.restler_static_string(" HTTP/1.1\\r\\n"),'
    )

    text = text[:start] + block + text[end:]

patch_camera_query_param("# Endpoint: /video, method: Get")
patch_camera_query_param("# Endpoint: /frame, method: Get")

# /save-geospatial-snapshot requires a trailing slash;
# RESTler strips trailing slashes during compilation so we patch the grammar.
# Step 1: add trailing slash
text = text.replace(
    'primitives.restler_static_string("save-geospatial-snapshot"),\n    primitives.restler_static_string(" HTTP/1.1\\r\\n"),',
    'primitives.restler_static_string("save-geospatial-snapshot/"),\n    primitives.restler_static_string(" HTTP/1.1\\r\\n"),'
)
# Step 2: inject Content-Type + body (runs on text already containing the trailing slash)
text = text.replace(
    'primitives.restler_static_string("save-geospatial-snapshot/"),\n    primitives.restler_static_string(" HTTP/1.1\\r\\n"),\n    primitives.restler_static_string("Accept: application/json\\r\\n"),\n    primitives.restler_static_string("Host: web.scenescape.intel.com\\r\\n"),\n    primitives.restler_refreshable_authentication_token("authentication_token_tag"),\n    primitives.restler_static_string("\\r\\n"),\n\n],',
    'primitives.restler_static_string("save-geospatial-snapshot/"),\n    primitives.restler_static_string(" HTTP/1.1\\r\\n"),\n    primitives.restler_static_string("Accept: application/json\\r\\n"),\n    primitives.restler_static_string("Host: web.scenescape.intel.com\\r\\n"),\n    primitives.restler_static_string("Content-Type: application/x-www-form-urlencoded\\r\\n"),\n    primitives.restler_refreshable_authentication_token("authentication_token_tag"),\n    primitives.restler_static_string("\\r\\n"),\n    primitives.restler_static_string("image_data=iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk%2BM9QDwADhgGAWjR9awAAAABJRU5ErkJggg%3D%3D"),\n    primitives.restler_static_string("\\r\\n"),\n\n],'
)


# /calculateintrinsics requires >=4 point correspondences; inject a static
# valid 4-point body so the API can actually process the request.
start, end, block = get_endpoint_block(text, "# Endpoint: /calculateintrinsics, method: Post")
if block is not None:
    import json
    valid_payload = {
        "mapPoints": [[0,0,0],[1,0,0],[1,1,0],[0,1,0]],
        "camPoints": [[320,240],[640,240],[640,480],[320,480]],
        "intrinsics": [[570,0,320],[0,570,240],[0,0,1]],
        "distortion": [0.0,0.0,0.0,0.0,0.0],
        "imageSize": [640,480]
    }
    body_str = json.dumps(valid_payload)
    escaped = body_str.replace("\\", "\\\\").replace('"', '\\"')
    replacement_line = f'    primitives.restler_static_string("{escaped}"),\n'
    brace_marker = '    primitives.restler_static_string("{"),\n'
    crlf_marker = '    primitives.restler_static_string("\\r\\n"),\n'
    bi = block.find(brace_marker)
    ci = block.rfind(crlf_marker, bi) if bi != -1 else -1
    if bi != -1 and ci != -1:
        block = block[:bi] + replacement_line + block[ci:]
    text = text[:start] + block + text[end:]

# Sensor/camera GET and DELETE use the PUT-written dependency by default, but PUT
# may not yet have run. Redirect them to use the POST-written variable instead so
# that GET and DELETE succeed as soon as POST does.
def patch_path_param_dependency(marker: str, old_var: str, new_var: str):
    global text
    start, end, block = get_endpoint_block(text, marker)
    if block is None:
        return
    block = block.replace(
        f'primitives.restler_static_string({old_var}.reader(), quoted=False),',
        f'primitives.restler_static_string({new_var}.reader(), quoted=False),'
    )
    text = text[:start] + block + text[end:]

patch_path_param_dependency("# Endpoint: /sensor/{sensor_id}, method: Get", "_sensor__sensor_id__put_name", "_sensor_post_sensor_id")
patch_path_param_dependency("# Endpoint: /sensor/{sensor_id}, method: Delete", "_sensor__sensor_id__put_name", "_sensor_post_sensor_id")
patch_path_param_dependency("# Endpoint: /camera/{sensor_id}, method: Get", "_camera__sensor_id__put_name", "_camera_post_sensor_id")
patch_path_param_dependency("# Endpoint: /camera/{sensor_id}, method: Delete", "_camera__sensor_id__put_name", "_camera_post_sensor_id")

# Camera POST response has sensor_id as writeOnly so it is absent from the body.
# The response includes uid which equals sensor_id. Fall back to uid so the
# parser can set _camera_post_sensor_id correctly.
text = text.replace(
    'temp_2060 = str(data["sensor_id"])',
    'temp_2060 = str(data.get("sensor_id") or data.get("uid"))'
)

grammar_path.write_text(text)
print("grammar.py patched successfully")
PY

/RESTler/restler/Restler $restler_mode \
  --time_budget $time_budget_hours \
  --grammar_file Compile/grammar.py \
  --dictionary_file Compile/dict.json \
  --settings settings.json

if [ -d "$mode_dir" ]; then
    mkdir -p "$(dirname "$result_dir")"
    rm -rf "$result_dir"
    mv "$mode_dir" "$result_dir"
fi

if [ -n "$USER_ID" ] && [ -n "$GROUP_ID" ]; then
    chown -R "$USER_ID":"$GROUP_ID" "$result_dir" /workspace/service_runs/manager /workspace/RestlerLogs/manager 2>/dev/null || true
fi

echo "RESTler fuzzing run completed"
