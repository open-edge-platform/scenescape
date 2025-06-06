#!/usr/bin/env python3

# Copyright (C) 2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import os
import numpy as np
from tests.functional.backend_functional import BackendFunctionalTest
from scene_common import log

TEST_NAME = "NEX-T10516"

class VDMSSimilaritySearch(BackendFunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.thing_1 = self.generate_random_vector()
    self.thing_2 = self.generate_random_vector()
    self.thing_2_match = self.generate_random_vector()

  def descriptor_set_reid(self):
    log.info("Add the descriptor set for RE-ID data")
    descriptor_set = {
      "AddDescriptorSet": {
        "name": "reid_vectors",
        "metric": "L2",
        "dimensions": 256
      }
    }
    all_queries = []
    all_queries.append(descriptor_set)

    response, res_arr = self.vdb.db.query(all_queries)
    log.debug(f"RESPONSE: {response}\nRES_ARR: {res_arr}")
    assert response[0]['AddDescriptorSet']['status'] == 0, "The response status for the descriptor set should be 0!"
    return

  def descriptor_objects(self):
    log.info("Add descriptors for two distinct objects")
    blob_1 = np.array(self.thing_1, dtype="float32")
    blob_2 = np.array(self.thing_2, dtype="float32")

    descriptor_blob = []
    descriptor_blob.append(blob_1.tobytes())
    descriptor_blob.append(blob_2.tobytes())

    descriptor_1 = {
      "AddDescriptor": {
        "set": "reid_vector",
        "label": "Person 1"
      }
    }

    descriptor_2 = {
      "AddDescriptor": {
        "set": "reid_vector",
        "label": "Person 2"
      }
    }

    all_queries = []
    all_queries.append(descriptor_1)
    all_queries.append(descriptor_2)

    response, res_arr = self.vdb.db.query(all_queries, [descriptor_blob])

    log.debug(f"RESPONSE: {response}\nRES_ARR: {res_arr}")
    assert response[0]['AddDescriptor']['status'] == 0 and response[1]['AddDescriptor']['status'] == 0, \
      "The response status for both descriptors should be 0!"
    return

  def get_similarity(self):
    log.info("Pass a third RE-ID vector from one of the two initial objects and get a similarity search comparison. It should have low distance from one of the entries.")
    response, res_arr = self.get_similarity_comparison([self.thing_2_match])
    log.debug(f"RESPONSE: {response}\nRES_ARR: {res_arr}")
    assert response[0]['FindDescriptor']['returned'] == 2, \
      "There should be only 2 entities returned!"
    return

def test_vdms_similarity_search(request, record_xml_attribute):
  """! Verify similarity search with RE-ID vectors using VDMS.
  @param    request                 Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """

  test = VDMSSimilaritySearch(TEST_NAME, request, record_xml_attribute)
  try:
    test.vdms_connect()
    test.descriptor_set_reid()
    test.descriptor_objects()
    test.get_similarity()
    test.exitCode = 0
  finally:
    test.recordTestResult()

  assert test.exitCode == 0
  return test.exitCode

def main():
  return test_vdms_similarity_search(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
