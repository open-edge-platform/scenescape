# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import socket
import threading

import numpy as np
import vdms

from controller.reid import ReIDDatabase
from scene_common import log

DEFAULT_HOSTNAME = os.getenv("VDMS_HOSTNAME", "vdms.scenescape.intel.com")
DIMENSIONS = 256
K_NEIGHBORS = 1
SCHEMA_NAME = "reid_vector"
SIMILARITY_METRIC = "L2"

class VDMSDatabase(ReIDDatabase):
  def __init__(self, set_name=SCHEMA_NAME,
               similarity_metric=SIMILARITY_METRIC, dimensions=DIMENSIONS):
    self.db = vdms.vdms(
      use_tls=True,
      ca_cert_file="/run/secrets/certs/scenescape-ca.pem",
      client_cert_file="/run/secrets/certs/scenescape-vdms-c.crt",
      client_key_file="/run/secrets/certs/scenescape-vdms-c.key"
    )
    self.set_name = set_name
    self.similarity_metric = similarity_metric
    self.dimensions = dimensions
    self.lock = threading.Lock()
    return

  def sendQuery(self, query, blob=None):
    """
    Helper function for handling the responses from sending queries to VDMS. There are three
    possible responses from VDMS when sending the query.
      - "NOT CONNECTED", if the database connection is not active
      - None, if the response fails to receive a packet
      - (response, res_arr), if query gets a response from VDMS

    @param   query      The list of queries to send to VDMS
    @param   blob       Blobs of data to send with queries (optional)
    @return  responses  The response dict from VDMS
    """
    responses = []
    response_blob = []
    with self.lock:
      if blob:
        query_response = self.db.query(query, blob)
      else:
        query_response = self.db.query(query)
    if query_response and query_response != "NOT CONNECTED":
      response_blob = query_response[1]
      for (item, response) in zip(query, query_response[0]):
        query_type = next(iter(item))
        response_data = response.get(query_type, {})
        responses.append(response_data)
    else:
      log.warn(f"Failed to send query to VDMS container: {query}")
    return responses, response_blob

  def connect(self, hostname=DEFAULT_HOSTNAME):
    try:
      self.db.connect(hostname)
      if not self.findSchema(self.set_name):
        self.addSchema(self.set_name, self.similarity_metric, self.dimensions)
      log.info(f"VDMS connection ready")
    except socket.error as e:
      log.warn(f"Failed to connect to VDMS container: {e}")
    return

  def addSchema(self, set_name, similarity_metric, dimensions):
    query = [{
      "AddDescriptorSet": {
        "name": f"{set_name}",
        "metric": f"{similarity_metric}",
        "dimensions": dimensions
      }
    }]
    response, _ = self.sendQuery(query)
    if response and response[0].get('status') != 0:
      log.warn(
        f"Failed to add the descriptor set to the database. Recieved response {response[0]}")
    return

  def addEntry(self, uuid, rvid, object_type, reid_vectors, set_name=SCHEMA_NAME):
    query = {
      "AddDescriptor": {
        "set": f"{set_name}",
        "properties": {
          "uuid": f"{uuid}",
          "rvid": f"{rvid}",
          "type": f"{object_type}"
        }
      }
    }
    blob = [[np.array(reid_vector, dtype="float32").tobytes()] for reid_vector in reid_vectors]
    add_query = [query] * len(reid_vectors)
    response, _ = self.sendQuery(add_query, blob)
    if response:
      for item in response:
        if item.get('status') != 0:
          log.warn(
            f"Failed to add the descriptor to the database. Received response {item}")
    return

  def findSchema(self, set_name):
    query = [{
      "FindDescriptorSet": {
        "set": f"{set_name}"
      }
    }]
    response, _ = self.sendQuery(query)
    if response and response[0].get('status') == 0 and response[0].get('returned') > 0:
      return True
    return False

  def findSimilarityScores(self, object_type, reid_vectors, set_name=SCHEMA_NAME,
                           k_neighbors=K_NEIGHBORS):
    find_query = {
      "FindDescriptor": {
        "set": f"{set_name}",
        "constraints": {
          "type": ["==", f"{object_type}"],
        },
        "k_neighbors": k_neighbors,
        "results": {
          "list": [
            "uuid",
            "rvid",
            "_distance",
          ],
          "blob": False
        }
      }
    }
    blob = [[np.array(reid_vector, dtype="float32").tobytes()] for reid_vector in reid_vectors]
    query = [find_query] * len(reid_vectors)
    response, _ = self.sendQuery(query, blob)
    if response:
      result = [
        item.get('entities')
        for item in response
        if (item.get('status') == 0 and item.get('returned') > 0)
      ]
      return result
    return None
