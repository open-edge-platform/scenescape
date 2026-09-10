#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from scene_common.rest_client import RESTClient


def record_test_result(name: str, error: int):
  print(f"\n{name}:", "FAIL" if error else "PASS")
  print("-----------------------------\n")
  return


def get_scene_uid(params, name):
  """Looks up the uid of the scene called *name* on the running stack.

  Replaces the old fixed EXAMPLEDB/testdb/calibrationdb uuids: scenes are
  now uploaded through the REST API with fresh server-assigned uids, so
  callers that need a specific scene by name (e.g. "Retail", "Queuing")
  resolve it at test time instead of hardcoding it.

  @param    params    dict with 'resturl' and 'rootcert' (the `params` fixture)
  @param    name      name of the scene to look up
  @return             the scene's uid
  """
  rest = RESTClient(params['resturl'], rootcert=params['rootcert'])
  assert rest.authenticate(params['user'], params['password'])
  results = rest.getScenes({"name": name}).get("results", [])
  assert results, f"Scene '{name}' not found"
  return results[0]["uid"]
