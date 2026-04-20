#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import random
from http import HTTPStatus

TEST_NAME = "NEX-T10429-API"

def test_object_crud_api(rest, result_recorder):
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

    res = rest.createAsset(asset_data)
    assert res.statusCode in (HTTPStatus.OK, HTTPStatus.CREATED), f"Failed to create asset: {res.errors}"
    asset_uid = res['uid']
    assert asset_uid, "Asset UID not returned"

    logging.info(f"Asset '{object_name}' created successfully.")

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

    res = rest.updateAsset(asset_uid, update_data)
    assert res.statusCode == HTTPStatus.OK, f"Failed to update asset: {res.errors}"
    logging.info(f"Asset '{object_name}' updated successfully.")

    # Verify update
    res = rest.getAsset(asset_uid)
    assert res.statusCode == HTTPStatus.OK, f"Failed to retrieve asset: {res.errors}"
    assert res['name'] == object_name_updated, "Asset name not updated correctly"
    assert res['tracking_radius'] == initial_loop_value, "Tracking radius mismatch"
    logging.info("Asset update verified.")

    # Remove 3D model if present
    if file_path:
      res = rest.updateAsset(asset_uid, {"map": None})
      assert res.statusCode == HTTPStatus.OK, f"Failed to remove 3D model: {res.errors}"
      logging.info("3D model removed successfully.")

    # Cleanup
    res = rest.deleteAsset(asset_uid)
    assert res.statusCode == HTTPStatus.OK, f"Failed to delete asset: {res.errors}"
    logging.info(f"Asset '{object_name_updated}' deleted successfully.\n")

  result_recorder.success()
