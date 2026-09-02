#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Download and install the hash-pinned Open3D cp314 wheel. Not on PyPI;
# published on the Open3D main-devel GitHub release. Used by Docker builds
# and test venv setup. pip --hash alone would require hashing all transitive
# deps, so the hash is verified manually before install.

set -euo pipefail

url="${1:?Open3D wheel URL required}"
hash="${2:?Open3D wheel sha256 required}"
PIP="${3:-pip3}"

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
