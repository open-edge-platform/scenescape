#!/usr/bin/env bash

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -e

cd /workspace
. .env

workspace_root="$(pwd)"
mode_dir="$(tr '[:lower:]' '[:upper:]' <<< "${restler_mode:0:1}")${restler_mode:1}"
result_dir="${workspace_root}/${mode_dir}/manager"
run_dir="${workspace_root}/.restler-runs/manager"
restler_work_dir="${workspace_root}/.restler-logs/manager"
restler_logs_dir="${restler_work_dir}/${mode_dir}"

rm -rf "$result_dir" "$run_dir" "$restler_work_dir"
mkdir -p "$run_dir" "$restler_work_dir"
cp fuzzing_openapi.yaml custom_dict.json settings.json .env token "$run_dir"/
cd "$run_dir"

echo "$instance_ip web.scenescape.intel.com" >> /etc/hosts

cp token /tmp
auth_token=$(curl -s "https://web.scenescape.intel.com/api/v1/auth" \
  -d "username=$auth_username&password=$auth_password" | jq -r '.token')
sed -i "s/##TOKEN##/$auth_token/" /tmp/token

rm -rf Compile Fuzz Fuzz-lean Test

/RESTler/restler/Restler compile --api_spec fuzzing_openapi.yaml

python3 - <<'PY'
import json
from pathlib import Path

compiled_path = Path("Compile/dict.json")
custom_path   = Path("custom_dict.json")

compiled = json.loads(compiled_path.read_text())
custom   = json.loads(custom_path.read_text())

compiled.update(custom)
compiled.setdefault("restler_custom_payload_uuid4_suffix", {})["child_scene_name"] = "child_scene_"

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

def patch_string_field_dependency_in_post(
    marker: str, field_name: str, dependency_expr: str, required: bool = False
):
    global text
    start, end, block = get_endpoint_block(text, marker)
    if block is None:
        if required:
            raise RuntimeError(f"Unable to find {marker} for required {field_name} dependency")
        return

    # The first field starts with a newline; subsequent fields start with a
    # comma and newline inside the generated triple-quoted static string.
    pattern = re.compile(
        rf'(primitives\.restler_static_string\(""",?\n\s*"{re.escape(field_name)}":\s*"""\),\n\s*)'
        r'primitives\.[^\n]+,'
    )
    block, replacement_count = pattern.subn(
        rf'\1primitives.restler_static_string({dependency_expr}, quoted=True),',
        block,
    )
    if required and replacement_count != 1:
        raise RuntimeError(
            f"Expected one {field_name} dependency in {marker}; found {replacement_count}"
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

patch_scene_and_points_in_post("# Endpoint: /region, method: Post")
patch_scene_and_points_in_post("# Endpoint: /tripwire, method: Post")
patch_string_field_dependency_in_post("# Endpoint: /sensor, method: Post", "scene", "_scene_post_uid.reader()")
patch_string_field_dependency_in_post("# Endpoint: /camera, method: Post", "scene", "_scene_post_uid.reader()")
patch_post_scene_uuid_dependency("# Endpoint: /sensor, method: Post")
patch_post_scene_uuid_dependency("# Endpoint: /camera, method: Post")
patch_post_scene_uuid_dependency("# Endpoint: /calibrationmarker, method: Post")
# Bind each relationship field explicitly; a blanket UUID replacement would
# give parent and child the same scene ID.
patch_string_field_dependency_in_post(
    "# Endpoint: /child, method: Post", "parent", "_scene_post_uid.reader()", required=True
)
patch_string_field_dependency_in_post(
    "# Endpoint: /child, method: Post", "child", "_child_scene_post_uid.reader()", required=True
)
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

text, camera_parser_count = re.subn(
    r'(def parse_camerapost\(.*?)(?=\ndef |\n# Endpoint:|\Z)',
    lambda match: match.group(0).replace(
        'data["sensor_id"]', 'data["uid"]'
    ),
    text,
    flags=re.DOTALL,
)
if camera_parser_count != 1:
    raise RuntimeError("Unable to find the POST /camera response parser")

# Add a separate POST /scene producer and matching DELETE for RESTler GC.
# Only request identities differ: the HTTP routes remain /scene and /scene/{uid}.
scene_parser = re.search(
    r'def parse_scenepost\(.*?(?=\ndef |\n# Endpoint:|\Z)', text, re.DOTALL
)
if scene_parser is None:
    raise RuntimeError("Unable to find the POST /scene response parser")
child_scene_parser = scene_parser.group(0).replace(
    "parse_scenepost", "parse_child_scenepost"
).replace("_scene_post_uid", "_child_scene_post_uid")
scene_ordering_variable = "__ordering____scene_post_child_scene_post"
text = text[:scene_parser.start()] + (
    '_child_scene_post_uid = dependencies.DynamicVariable("_child_scene_post_uid")\n\n'
    f'{scene_ordering_variable} = dependencies.DynamicVariable("{scene_ordering_variable}")\n\n'
    + child_scene_parser + "\n\n"
) + text[scene_parser.start():]

for method, request_id in (("Post", "/scene"), ("Delete", "/scene/{uid}")):
    marker = f"# Endpoint: {request_id}, method: {method}"
    start, end, block = get_endpoint_block(text, marker)
    if block is None:
        raise RuntimeError(f"Unable to find {marker}")
    original = block
    clone = block.replace("_scene_post_uid", "_child_scene_post_uid")
    clone = clone.replace("parse_scenepost", "parse_child_scenepost")
    # Separate identities prevent RESTler's sequence cache merging producers.
    clone = clone.replace(f'requestId="{request_id}"', f'requestId="{request_id}#child-scene"')
    clone = clone.replace(marker, marker + " (child-scene variant)", 1)
    if method == "Post":
        # Linearize the prerequisites: parent scene -> child scene -> link.
        # Independent producers form a diamond that RESTler's coverage reporter
        # incorrectly treats as a chain when reconstructing prefix rendering IDs.
        # Native ordering metadata enforces this without adding HTTP data: the
        # parent producer writes the token and the child producer reads it.
        writer = "_scene_post_uid.writer()"
        if original.count(writer) != 1:
            raise RuntimeError("Unable to add ordering writer to the POST /scene producer")
        original = original.replace(
            writer, f"{writer},\n                {scene_ordering_variable}.writer()"
        )
        clone, ordering_count = re.subn(
            r"(?m)^(\s*)'post_send':",
            lambda match: (
                f"{match.group(1)}'pre_send': {{'dependencies': [{scene_ordering_variable}.reader()]}},\n"
                f"{match.group(1)}'post_send':"
            ),
            clone,
        )
        if ordering_count != 1:
            raise RuntimeError("Unable to order child scene creation after parent scene creation")
        # A distinct prefix also prevents name collisions when values are reused.
        clone = clone.replace(
            'primitives.restler_custom_payload_uuid4_suffix("scene_name", quoted=True)',
            'primitives.restler_custom_payload_uuid4_suffix("child_scene_name", quoted=True)',
            1,
        )
    text = text[:start] + original + clone + text[end:]

child_blocks = []
for method in ("Get", "Put", "Delete"):
    marker = f"# Endpoint: /child/{{uid}}, method: {method}"
    start, end, block = get_endpoint_block(text, marker)
    if block is None:
        raise RuntimeError(f"Unable to find {marker}")
    child_blocks.append(block if block.endswith("\n") else block + "\n")
    text = text[:start] + text[end:]
first_endpoint = text.index("# Endpoint:")
text = text[:first_endpoint] + "".join(child_blocks) + text[first_endpoint:]

grammar_path.write_text(text)
print("grammar.py patched successfully")
PY

/RESTler/restler/Restler \
    --workingDirPath "$restler_work_dir" \
    "$restler_mode" \
    --time_budget "$time_budget_hours" \
  --grammar_file Compile/grammar.py \
  --dictionary_file Compile/dict.json \
  --settings settings.json

mkdir -p "$result_dir/RestlerLogs"
shopt -s dotglob nullglob
run_files=("$run_dir"/*)
if (( ${#run_files[@]} )); then
    mv "${run_files[@]}" "$result_dir"/
fi

if [[ -d "$mode_dir" ]]; then
    mode_files=("$mode_dir"/*)
    if (( ${#mode_files[@]} )); then
        mv "${mode_files[@]}" "$result_dir"/
    fi
    rmdir "$mode_dir"
fi

log_files=("$restler_logs_dir"/*)
if (( ${#log_files[@]} )); then
    for log_file in "${log_files[@]}"; do
        if [[ "$(basename "$log_file")" == "$mode_dir" ]]; then
            mode_log_files=("$log_file"/*)
            if (( ${#mode_log_files[@]} )); then
                mv "${mode_log_files[@]}" "$result_dir/RestlerLogs"/
            fi
            rmdir "$log_file"
        else
            mv "$log_file" "$result_dir/RestlerLogs"/
        fi
    done
fi
shopt -u dotglob nullglob
rm -rf "$run_dir" "$restler_work_dir"

if [[ -n "${USER_ID:-}" ]] && [[ -n "${GROUP_ID:-}" ]]; then
  chown -R "$USER_ID":"$GROUP_ID" "$result_dir" 2>/dev/null || true
fi

echo "RESTler fuzzing run completed"
