#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.functional import FunctionalTest
from http import HTTPStatus
from scene_common.rest_client import RESTClient

TEST_NAME = "NEX-T10428-API"

class AddDelete3DObjectTest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])


  def runTest(self):
    object_name = "3D Object"
    file_path = "/workspace/tests/ui/test_media/box.glb"

    # Create a 3d asset
    with open(file_path, "rb") as f:
      asset_data = {
        "name": object_name,
        "model_3d": f
      }
      res = self.rest.createAsset(asset_data)
      assert res.statusCode in (HTTPStatus.OK, HTTPStatus.CREATED), f"Failed to create asset: {res.errors}"
      asset_uid = res['uid']
      assert asset_uid, "Asset UID not returned"

    print("3D object (asset) created successfully.")

    # Delete the asset
    res = self.rest.deleteAsset(asset_uid)
    assert res.statusCode == HTTPStatus.OK, f"Failed to delete asset: {res.errors}"

    print("3D object (asset) deleted successfully.")
    return True


def test_add_delete_3d_object_api(request, record_xml_attribute):
  test = AddDelete3DObjectTest(TEST_NAME, request, record_xml_attribute)
  assert test.runTest()
  return
