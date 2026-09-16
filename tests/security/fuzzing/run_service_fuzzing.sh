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
  AUTOCAL_SCENE_ID="${AUTOCAL_SCENE_ID:?AUTOCAL_SCENE_ID must be set}"
  AUTOCAL_CAMERA_ID="${AUTOCAL_CAMERA_ID:?AUTOCAL_CAMERA_ID must be set}"
  python3 - "$AUTOCAL_SCENE_ID" "$AUTOCAL_CAMERA_ID" <<'PY'
from pathlib import Path
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

replace_block(
  "# Endpoint: /perceptual-sensors/{sensorId}/localization, method: Post",
  [('primitives.restler_fuzzable_string("fuzzstring", quoted=False),', camera_primitive),
   ('primitives.restler_fuzzable_uuid4("566048da-ed19-4cd3-8e0a-b7e0e1ec4d72", quoted=True, examples=["302cf49a-97ec-402d-a324-c5077b280b7b"]),',
    'primitives.restler_static_string("{}", quoted=True),'.format(scene_id))],
)

grammar_path.write_text(text)
PY
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

echo "RESTler ${service_name} fuzzing run completed"
exit "$restler_status"
