#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Download and install the hash-pinned Open3D cp314 wheel from
# requirements-open3d-cpu.txt. Used by Docker builds and test venv setup.

set -euo pipefail

REQ_FILE="${1:?requirements-open3d-cpu.txt path required}"
PIP="${2:-pip3}"

url=$(
  grep -E '^https://' "$REQ_FILE" \
    | sed 's/\\//g; s/[[:space:]]*$//; s/[[:space:]]\\$//'
)
hash=$(
  grep -oE 'sha256:[a-f0-9]{64}' "$REQ_FILE" | head -1 | cut -d: -f2
)

if [[ -z "$url" || -z "$hash" ]]; then
  echo "Could not parse wheel URL/hash from $REQ_FILE" >&2
  exit 1
fi

wheel=/tmp/open3d_cpu-0.19.0+cf1516a-cp314-cp314-manylinux_2_35_x86_64.whl
cleanup() { rm -f "$wheel"; }
trap cleanup EXIT

curl -fsSL -o "$wheel" "$url"
echo "${hash}  ${wheel}" | sha256sum -c -

if [[ "$PIP" == *"/.venv/"* ]]; then
  "$PIP" install --no-cache-dir "$wheel"
else
  "$PIP" install --break-system-packages --ignore-installed --no-cache-dir "$wheel"
fi
