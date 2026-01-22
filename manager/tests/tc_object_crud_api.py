#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import random
from tests.functional import FunctionalTest
from http import HTTPStatus
from scene_common.rest_client import RESTClient

TEST_NAME = "NEX-T10429-API"

class ObjectCRUDTest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])

  def runTest(self):
    file_paths = ["/workspace/tests/ui/test_media/box.glb", None]

    for file_path in file_paths:
      object_name = "Test 3D Object"
      object_name_updated = "Test 3D Object-2"
      initial_loop_value = round(random.uniform(0.1, 10), 1)

      if file_path:
        asset_data = {
          "name": object_name,
          "map": file_path
        }
      else:
        asset_data = {
          "name": object_name
        }

      res = self.rest.createAsset(asset_data)
      assert res.statusCode in (HTTPStatus.OK, HTTPStatus.CREATED), f"Failed to create asset: {res.errors}"
      asset_uid = res['uid']
      assert asset_uid, "Asset UID not returned"

      print(f"Asset '{object_name}' created successfully.")

      # Update object
      update_data = {
        "name": object_name_updated,
        "tracking_radius": initial_loop_value,
        "x_size": initial_loop_value + 1,
        "y_size": initial_loop_value + 2,
        "z_size": initial_loop_value + 3,
        "project_to_map": True,
        "rotation_from_velocity": True
      }

      res = self.rest.updateAsset(asset_uid, update_data)
      assert res.statusCode == HTTPStatus.OK, f"Failed to update asset: {res.errors}"
      print(f"Asset '{object_name}' updated successfully.")

      # Verify update
      res = self.rest.getAsset(asset_uid)
      assert res.statusCode == HTTPStatus.OK, f"Failed to retrieve asset: {res.errors}"
      assert res['name'] == object_name_updated, "Asset name not updated correctly"
      assert res['tracking_radius'] == initial_loop_value, "Tracking radius mismatch"
      print("Asset update verified.")

      # Remove 3D model if present
      if file_path:
        res = self.rest.updateAsset(asset_uid, {"map": None})
        assert res.statusCode == HTTPStatus.OK, f"Failed to remove 3D model: {res.errors}"
        print("3D model removed successfully.")

      # Cleanup
      res = self.rest.deleteAsset(asset_uid)
      assert res.statusCode == HTTPStatus.OK, f"Failed to delete asset: {res.errors}"
      print(f"Asset '{object_name_updated}' deleted successfully.\n")

    return True

def test_object_crud_api(request, record_xml_attribute):
  test = ObjectCRUDTest(TEST_NAME, request, record_xml_attribute)
  assert test.runTest()
  return
