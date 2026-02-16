#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus
from scene_common.rest_client import RESTClient
from tests.common_test_utils import record_test_result

TEST_NAME = "NEX-T10428-API"

def test_add_delete_3d_object_api(params, record_xml_attribute):
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1

  rest = RESTClient(params['resturl'], rootcert=params['rootcert'])
  assert rest.authenticate(params['user'], params['password'])

  object_name = "3D Object"
  file_path = "/workspace/tests/ui/test_media/box.glb"

  try:
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

    print("3D object (asset) created successfully.")

    # Delete the asset
    res = rest.deleteAsset(asset_uid)
    assert res.statusCode == HTTPStatus.OK, f"Failed to delete asset: {res.errors}"
    print("3D object (asset) deleted successfully.")
    exit_code = 0
  finally:
    record_test_result(TEST_NAME, exit_code)