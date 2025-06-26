# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import numpy as np
import random
from tests.functional import FunctionalTest
from scene_common import log
from controller.vdms_adapter import VDMSDatabase, vdms

class BackendFunctionalTest(FunctionalTest):
  def vdms_connect(self, use_tls=True):
    self.vdb = VDMSDatabase()
    if not use_tls:
      self.vdb.db = vdms.vdms(use_tls=False)
    self.vdb.connect()
    return

  def generate_random_vector(self, floor=-1, ceiling=1, vsize=256):
    return [random.uniform(floor, ceiling) for _ in range(vsize)]

  def get_similarity_comparison(self, reid_vectors=1):
    """! Get the similarity comparison based on the reid_vectors sent
    @param    reid_vectors            If is of type list, it will use those vectors to
                                      generate blobs.
                                      If is of type int, it will randomly generate that
                                      amount of vectors to be searched.
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
        "set": "reid_vector",
        "k_neighbors": 20,
        "results": {
          "list": ["_distance"],
          "blob": True
        }
      }
    }]

    query = find * len(reid_vectors)
    response, res_arr = self.vdb.db.query(query, blob)
    return (response, res_arr)
