#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus
from tests.utils.log import get_logger
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK
import pytest

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

TEST_NAME = "NEX-T10428-API"

@pytest.mark.test_name("NEX-T10428")
def test_add_delete_3d_object_api(rest, result_recorder, repo_root):
  object_name = "3D Object"
  file_path = f"{repo_root}/tests/ui/test_media/box.glb"

  # Create a 3d asset
  with open(file_path, "rb") as f:
    asset_data = {
      "name": object_name,
      "model_3d": f
    }
    res = rest.createAsset(asset_data)
    assert res.statusCode in (HTTPStatus.OK, HTTPStatus.CREATED), f"Failed to create asset: {res.errors}"
    asset_uid = res['uid']
    assert asset_uid, "Asset UID not returned"

  log.info("3D object (asset) created successfully.")

  # Delete the asset
  res = rest.deleteAsset(asset_uid)
  assert res.statusCode == HTTPStatus.OK, f"Failed to delete asset: {res.errors}"
  log.info("3D object (asset) deleted successfully.")

  result_recorder.success()
