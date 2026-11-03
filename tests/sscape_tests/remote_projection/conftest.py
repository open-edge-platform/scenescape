# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Generate the remote projection gRPC stubs (package scenescape_api) for these tests.

The controller image generates the same package at build time (controller/Dockerfile).
"""

import atexit
import shutil
import sys
import tempfile
from pathlib import Path

import grpc_tools
from grpc_tools import protoc

_API_DIR = Path(__file__).resolve().parents[3] / "api"


def _generate_stubs():
  out_dir = Path(tempfile.mkdtemp(prefix="scenescape-api-"))
  atexit.register(shutil.rmtree, out_dir, ignore_errors=True)
  well_known_protos = Path(grpc_tools.__file__).parent / "_proto"
  result = protoc.main([
    "grpc_tools.protoc",
    f"-Iscenescape_api={_API_DIR}",
    f"-I{well_known_protos}",
    f"--python_out={out_dir}",
    f"--grpc_python_out={out_dir}",
    "scenescape_api/projection/v1/projection.proto",
  ])
  if result != 0:
    raise RuntimeError(f"protoc failed for {_API_DIR / 'projection/v1/projection.proto'}")
  return out_dir


_stub_dir = str(_generate_stubs())
if _stub_dir not in sys.path:
  sys.path.insert(0, _stub_dir)
