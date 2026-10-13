#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Regenerate the committed Python protobuf/gRPC stubs for scenescape.ptz.v1.
# Requires grpcio-tools==1.71.2 (see tests/requirements.txt).
#
# Usage: docs/user-guide/api-docs/positioning/v1/generate.sh
#        (PYTHON overrides the interpreter)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../.." && pwd)"
readonly REPO_ROOT
readonly API_ROOT="docs/user-guide/api-docs"
readonly PYTHON="${PYTHON:-python3}"
readonly OUT_DIR="${REPO_ROOT}/positioning/src/positioning/v1"
readonly YEAR="2026"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

cd "${REPO_ROOT}"
"${PYTHON}" -m grpc_tools.protoc \
  -I "${API_ROOT}" \
  --python_out="${tmp_dir}" \
  --grpc_python_out="${tmp_dir}" \
  --pyi_out="${tmp_dir}" \
  "${API_ROOT}/positioning/v1/ptz.proto"

# Header strings written into generated files; not this file's license.
# REUSE-IgnoreStart
mkdir -p "${OUT_DIR}"
if [[ ! -f "${OUT_DIR}/__init__.py" ]]; then
  printf '%s\n' \
    "# SPDX-FileCopyrightText: (C) ${YEAR} Intel Corporation" \
    "# SPDX-License-Identifier: Apache-2.0" > "${OUT_DIR}/__init__.py"
fi

for generated in "${tmp_dir}"/positioning/v1/ptz_pb2*; do
  {
    printf '%s\n' \
      "# SPDX-FileCopyrightText: (C) ${YEAR} Intel Corporation" \
      "# SPDX-License-Identifier: Apache-2.0" \
      "# Generated from ${API_ROOT}/positioning/v1/ptz.proto - do not edit." \
      "# pylint: skip-file" \
      "# flake8: noqa"
    if [[ "${generated}" == *.py ]]; then
      # Repository indent policy is 2 spaces (make indent-check).
      "${PYTHON}" tests/scripts/reindent < "${generated}"
    else
      cat "${generated}"
    fi
  } > "${OUT_DIR}/$(basename "${generated}")"
done
# REUSE-IgnoreEnd

echo "Generated stubs in ${OUT_DIR}"
