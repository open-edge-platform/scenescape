# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import numpy as np
import random
from tests.functional import FunctionalTest
from controller.vdms_adapter import VDMSDatabase, vdms
from tests.utils.log import get_logger

log = get_logger(__name__)

class BackendFunctionalTest(FunctionalTest):
  def vdms_connect(self, use_tls=True):
    rootcert = self.params.get('rootcert', '/run/secrets/certs/scenescape-ca.pem')
    secrets_dir = os.path.dirname(os.path.dirname(rootcert))
    certs_dir = os.path.join(secrets_dir, 'certs')
    client_cert = os.path.join(certs_dir, 'scenescape-vdms-c.crt')
    client_key = os.path.join(certs_dir, 'scenescape-vdms-c.key')
    self.vdb = VDMSDatabase(
      ca_cert=rootcert,
      client_cert=client_cert,
      client_key=client_key,
    )
    if not use_tls:
      self.vdb.db = vdms.vdms(use_tls=False)
    self.vdb.connect()
    assert self.vdb.db.connected, "Failed to connect to VDMS. Is the VDMS service running?"
    return

  def generate_random_vector(self, floor=-1, ceiling=1, vsize=256):
    return [random.uniform(floor, ceiling) for _ in range(vsize)]

  def get_similarity_comparison(self, reid_vectors=1, set_name="reid_vector"):
    """! Get the similarity comparison based on the reid_vectors sent
    @param    reid_vectors            If is of type list, it will use those vectors to
                                      generate blobs.
                                      If is of type int, it will randomly generate that
                                      amount of vectors to be searched.

    @param    set_name                Name of the descriptor set to search against.

    @return   (response, res_arr)     The query response and the response array.
    """

    assert isinstance(reid_vectors, list) or isinstance(reid_vectors, int), \
      log.error("reid_vectors is neither a list nor an integer!")

    if type(reid_vectors) == int:
      iterations = reid_vectors
      reid_vectors = []
      for _ in range(iterations):
        values = [random.uniform(-1, 1) for _ in range(256)]
        reid_vectors.append(values)

    blob = [[np.array(reid_vector, dtype="float32").tobytes()] for reid_vector in reid_vectors]

    find = [{
      "FindDescriptor": {
        "set": set_name,
        "k_neighbors": 20,
        "results": {
          "list": ["_distance"],
          "blob": True
        }
      }
    }]

    query = find * len(reid_vectors)
    return self.vdb.sendQuery(query, blob)

  def delete_descriptors(self, set_name, run_id):
    """! Best-effort removal of descriptors created by a single test run.
    @param    set_name                Name of the descriptor set to clean.
    @param    run_id                  Per-run identifier stored on each descriptor.
    @return   None
    """
    query = [{
      "DeleteDescriptor": {
        "set": set_name,
        "constraints": {
          "run_id": ["==", run_id]
        }
      }
    }]
    try:
      response, _ = self.vdb.sendQuery(query)
      log.debug(f"delete_descriptors RESPONSE: {response}")
    except Exception as exc:
      log.warning(f"Failed to delete descriptors for run {run_id}: {exc}")
    return
