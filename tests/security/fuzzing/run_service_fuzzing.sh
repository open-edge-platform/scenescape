#!/usr/bin/env bash

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

cd /workspace

if [[ -f .env ]]; then
  # Reuse the same configuration as the manager fuzzing runner.
  . .env
fi

service_name="${SERVICE_NAME:?SERVICE_NAME must be set}"
spec_source="${SPEC_SOURCE:?SPEC_SOURCE must be set}"
server_url="${SERVER_URL:?SERVER_URL must be set}"
instance_ip="${INSTANCE_IP:-${instance_ip:-}}"
restler_mode="${RESTLER_MODE:-${restler_mode:-test}}"
time_budget_hours="${TIME_BUDGET_HOURS:-${time_budget_hours:-2}}"

: "${instance_ip:?instance_ip or INSTANCE_IP must be set}"

if [[ "$service_name" == "autocalibration" ]]; then
  resolved_camera_id="${AUTOCAL_CAMERA_ID:-${autocal_camera_id:-}}"
  if [[ -z "$resolved_camera_id" ]]; then
    echo "Set autocal_camera_id in .env or pass AUTOCAL_CAMERA_ID with docker run -e" >&2
    exit 1
  fi
  camera_id_pattern='^[[:alnum:]_.-]{1,64}$'
  if [[ ! "$resolved_camera_id" =~ $camera_id_pattern ]]; then
    echo "Auto Calibration camera ID must be 1-64 letters, digits, dots," \
      "underscores or hyphens" >&2
    exit 1
  fi

  resolved_scene_id="${AUTOCAL_SCENE_ID:-${autocal_scene_id:-}}"
  if [[ -z "$resolved_scene_id" ]]; then
    camera_status_url="https://web.scenescape.intel.com/api/v1/autocalibration"
    camera_status_url+="/cameras/${resolved_camera_id}/calibration"
    if ! camera_status="$(curl --fail --silent --show-error \
      --resolve "web.scenescape.intel.com:443:${instance_ip}" "$camera_status_url")"; then
      printf 'Could not query camera %s status; verify it exists and supports calibration\n' \
        "$resolved_camera_id" >&2
      exit 1
    fi
    if ! resolved_scene_id="$(jq -er --arg camera_id "$resolved_camera_id" \
      'select(.cameraId == $camera_id) | .sceneId | strings | select(length > 0)' \
      <<< "$camera_status")"; then
      printf 'No scene ID for %s; set AUTOCAL_SCENE_ID to override\n' \
        "$resolved_camera_id" >&2
      exit 1
    fi
  fi
  scene_id_pattern='^[[:xdigit:]]{8}-[[:xdigit:]]{4}-'
  scene_id_pattern+='[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{12}$'
  if [[ ! "$resolved_scene_id" =~ $scene_id_pattern ]]; then
    echo "Auto Calibration scene ID must be a UUID" >&2
    exit 1
  fi
  printf 'Auto Calibration camera: %s; scene: %s\n' \
    "$resolved_camera_id" "$resolved_scene_id"
fi

spec_file="${service_name}_openapi.yaml"
mode_dir="$(tr '[:lower:]' '[:upper:]' <<< "${restler_mode:0:1}")${restler_mode:1}"
result_dir="/workspace/${mode_dir}/${service_name}"
run_dir="/workspace/.restler-runs/${service_name}"
restler_work_dir="/workspace/.restler-logs/${service_name}"
restler_logs_dir="${restler_work_dir}/${mode_dir}"

rm -rf "$result_dir" "$run_dir" "$restler_work_dir"
mkdir -p "$run_dir" "$restler_work_dir"
cp /workspace/settings.json "$run_dir"/
cd "$run_dir"
cp "$spec_source" "$spec_file"
# These service specs do not define token authentication; Manager's settings
# file points at /tmp/token and would prevent RESTler from starting.
printf '{}\n' > settings.json
sed -i "0,/^  - url:/s#^  - url:.*#  - url: \"$server_url\"#" "$spec_file"

/RESTler/restler/Restler compile --api_spec "$spec_file"

if [[ "$service_name" == "autocalibration" ]]; then
  python3 - "$resolved_scene_id" "$resolved_camera_id" <<'PY'
from pathlib import Path
import re
import sys

grammar_path = Path("Compile/grammar.py")
text = grammar_path.read_text()
scene_id, camera_id = sys.argv[1:]

def replace_block(marker, replacements):
  global text
  start = text.find(marker)
  if start == -1:
    return
  end = text.find("# Endpoint:", start + len(marker))
  if end == -1:
    end = len(text)
  block = text[start:end]
  for old, new in replacements:
    block = block.replace(old, new)
  text = text[:start] + block + text[end:]

scene_primitive = 'primitives.restler_static_string("{}", quoted=False),'.format(scene_id)
camera_primitive = 'primitives.restler_static_string("{}", quoted=False),'.format(camera_id)

for method in ("Post", "Get", "Patch"):
  replace_block(
    f"# Endpoint: /scenes/{{sceneId}}/registration, method: {method}",
    [('primitives.restler_fuzzable_string("fuzzstring", quoted=False),', scene_primitive)],
  )

for method in ("Post", "Get"):
  replace_block(
    f"# Endpoint: /cameras/{{cameraId}}/calibration, method: {method}",
    [('primitives.restler_fuzzable_string("fuzzstring", quoted=False),', camera_primitive)],
  )

localization_marker = "# Endpoint: /perceptual-sensors/{sensorId}/localization, method: Post"
start, end, block = text.find(localization_marker), -1, None
if start != -1:
  end = text.find("# Endpoint:", start + len(localization_marker))
  if end == -1:
    end = len(text)
  block = text[start:end]
if block is None:
  raise RuntimeError(f"Unable to find {localization_marker}")
block = block.replace(
  'primitives.restler_fuzzable_string("fuzzstring", quoted=False),',
  camera_primitive,
  1,
)
scene_uuid_pattern = re.compile(
  r'primitives\.restler_fuzzable_uuid4\("[^"]+", quoted=True'
  r'(?:, examples=\[[^\]]*\])?\),'
)
block, scene_uuid_count = scene_uuid_pattern.subn(
  'primitives.restler_static_string("{}", quoted=True),'.format(scene_id),
  block,
  count=1,
)
if scene_uuid_count != 1:
  raise RuntimeError(f"Expected one sceneId UUID in {localization_marker}")
text = text[:start] + block + text[end:]

grammar_path.write_text(text)
PY
fi
if [[ "$service_name" == "mapping" ]]; then
  # Status records exist for rejected jobs, so this ID reaches the 200 response path.
  seed_request_id="$(python3 /workspace/mapping_upload_fuzzing.py seed --target-ip "$instance_ip")"
  spec_example_id="a3f1c2d4e5b6a7f8c9d0e1f2a3b4c5d6"
  grep -q "$spec_example_id" Compile/grammar.py \
    || { echo "Mapping spec example request_id not found in grammar" >&2; exit 1; }
  sed -i "s/$spec_example_id/$seed_request_id/" Compile/grammar.py
fi
set +e
/RESTler/restler/Restler \
  --workingDirPath "$restler_work_dir" \
  "$restler_mode" \
  --time_budget "$time_budget_hours" \
  --grammar_file Compile/grammar.py \
  --dictionary_file Compile/dict.json \
  --settings settings.json \
  --target_ip "$instance_ip" \
  --host web.scenescape.intel.com
restler_status=$?
set -e

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

upload_status=0
if [[ "$service_name" == "mapping" ]]; then
  # RESTler cannot generate multipart bodies, so uploads are fuzzed separately.
  upload_args=()
  if [[ "${MAPPING_UPLOAD_SKIP_LARGE:-0}" == "1" ]]; then
    upload_args+=(--skip-large)
  fi
  python3 /workspace/mapping_upload_fuzzing.py fuzz --target-ip "$instance_ip" \
    --output-dir "$result_dir/UploadFuzzing" "${upload_args[@]}" || upload_status=$?
fi

echo "RESTler ${service_name} fuzzing run completed"
if (( restler_status != 0 )); then
  exit "$restler_status"
fi
exit "$upload_status"
