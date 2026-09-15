# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import uuid
import numpy as np
from tests.functional.backend_functional import BackendFunctionalTest
from tests.functional.reid_backend import REID_DATABASE, get_reid_profile_module
from tests.utils.log import get_logger

from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
import pytest
log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=get_reid_profile_module(),
  auth=AUTH_CONTROLLER,
)

TEST_NAME = "NEX-T10516"

class ReidSimilaritySearch(BackendFunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.thing_1 = self.generate_random_vector()
    self.thing_2 = self.generate_random_vector()
    self.thing_2_match = self.generate_random_vector()
    # Per-run identifiers keep this test isolated from descriptors left behind
    # by earlier runs sharing the same ReID backend instance.
    self.run_id = uuid.uuid4().hex
    self.set_name = f"reid_vector_{self.run_id[:8]}"

  def descriptor_set_reid(self):
    log.info("Add the descriptor set for RE-ID data")
    if REID_DATABASE == "QDRANT":
      from controller.qdrant_adapter import QdrantDatabase
      from tests.functional.reid_backend import connect_reid_database
      # Use a dedicated adapter bound to this run's collection and L2 metric so
      # ensureSchema initializes the custom set rather than the default IP schema.
      self.vdb = QdrantDatabase(set_name=self.set_name, similarity_metric="L2")
      connect_reid_database(self.vdb, use_tls=True)
      self.vdb.ensureSchema(256)
      return

    descriptor_set = {
      "AddDescriptorSet": {
        "name": self.set_name,
        "metric": "L2",
        "dimensions": 256
      }
    }
    all_queries = []
    all_queries.append(descriptor_set)

    response, res_arr = self.vdb.sendQuery(all_queries)
    log.debug(f"RESPONSE: {response}\nRES_ARR: {res_arr}")
    assert response[0]['status'] == 0, "The response status for the descriptor set should be 0!"
    return

  def descriptor_objects(self):
    log.info("Add descriptors for two distinct objects")
    if REID_DATABASE == "QDRANT":
      self.vdb.addEntry(
        "person-1",
        "track-1",
        "person",
        [self.thing_1],
        run_id=self.run_id)
      self.vdb.addEntry(
        "person-2",
        "track-2",
        "person",
        [self.thing_2],
        run_id=self.run_id)
      return

    blob_1 = np.array(self.thing_1, dtype="float32")
    blob_2 = np.array(self.thing_2, dtype="float32")

    descriptor_blob = []
    descriptor_blob.append(blob_1.tobytes())
    descriptor_blob.append(blob_2.tobytes())

    descriptor_1 = {
      "AddDescriptor": {
        "set": self.set_name,
        "label": "Person 1",
        "properties": {"run_id": self.run_id}
      }
    }

    descriptor_2 = {
      "AddDescriptor": {
        "set": self.set_name,
        "label": "Person 2",
        "properties": {"run_id": self.run_id}
      }
    }

    all_queries = []
    all_queries.append(descriptor_1)
    all_queries.append(descriptor_2)

    response, res_arr = self.vdb.sendQuery(all_queries, [descriptor_blob])

    log.debug(f"RESPONSE: {response}\nRES_ARR: {res_arr}")
    assert response[0]['status'] == 0 and response[1]['status'] == 0, \
      "The response status for both descriptors should be 0!"
    return

  def get_similarity(self):
    log.info("Pass a third RE-ID vector from one of the two initial objects and get a similarity search comparison. It should have low distance from one of the entries.")
    response, res_arr = self.get_similarity_comparison([self.thing_2_match], set_name=self.set_name)
    log.debug(f"RESPONSE: {response}\nRES_ARR: {res_arr}")
    if REID_DATABASE == "QDRANT":
      assert response[0]['returned'] >= 1, \
        "There should be at least one entity returned!"
      return
    assert response[0]['returned'] == 2, \
      "There should be only 2 entities returned!"
    return

@pytest.mark.test_name("NEX-T10516")
def test_reid_similarity_search(scenescape_env, request, record_xml_attribute):
  """! Verify similarity search with RE-ID vectors on the configured backend.
  @param    request                 Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """

  test = ReidSimilaritySearch(TEST_NAME, request, record_xml_attribute)
  try:
    test.reid_connect()
    test.descriptor_set_reid()
    test.descriptor_objects()
    test.get_similarity()
    test.exitCode = 0
  finally:
    test.delete_descriptors(test.set_name, test.run_id)
    test.recordTestResult()

  assert test.exitCode == 0
