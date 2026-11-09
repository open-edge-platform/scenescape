#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Regenerate the committed Python protobuf/gRPC stubs for Observation Processor.
# Requires grpcio-tools==1.71.2 (see tests/requirements.txt).
#
# Usage: make -C observation_processor proto
#        (PYTHON overrides the interpreter)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly REPO_ROOT
readonly PROTO_ROOT="observation_processor/proto"
readonly PYTHON="${PYTHON:-python3}"
readonly OUT_DIR="${REPO_ROOT}/observation_processor/src/observation_processor/grpc_api"
readonly YEAR="2026"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

cd "${REPO_ROOT}"
"${PYTHON}" -m grpc_tools.protoc \
  -I "${PROTO_ROOT}" \
  --python_out="${tmp_dir}" \
  --grpc_python_out="${tmp_dir}" \
  --pyi_out="${tmp_dir}" \
  "${PROTO_ROOT}/observation_processor.proto"

sed -i 's/^import observation_processor_pb2 as/from . import observation_processor_pb2 as/' \
  "${tmp_dir}/observation_processor_pb2_grpc.py"

# Header strings written into generated files; not this file's license.
# REUSE-IgnoreStart
mkdir -p "${OUT_DIR}"
for generated in "${tmp_dir}"/observation_processor_pb2*; do
  {
    printf '%s\n' \
      "# SPDX-FileCopyrightText: (C) ${YEAR} Intel Corporation" \
      "# SPDX-License-Identifier: Apache-2.0" \
      "# Generated from ${PROTO_ROOT}/observation_processor.proto - do not edit." \
      "# pylint: skip-file" \
      "# flake8: noqa"
    if [[ "${generated}" == *.py ]]; then
      "${PYTHON}" tests/scripts/reindent < "${generated}"
    else
      cat "${generated}"
    fi
  } > "${OUT_DIR}/$(basename "${generated}")"
done
# REUSE-IgnoreEnd

echo "Generated stubs in ${OUT_DIR}"