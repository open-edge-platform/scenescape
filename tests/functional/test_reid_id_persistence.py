#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import threading
import time

import pytest

import tests.common_test_utils as common
from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from tests.functional.reid_backend import get_reid_profile_module
from tests.utils.log import get_logger
from tests.utils.spec import FuncTestSpec

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=get_reid_profile_module(),
)

# The queuing sample videos are 54s long and loop, so people repeatedly leave
# and re-enter view. Collect several loops so every person gets multiple
# exit/return cycles to be re-identified across.
COLLECT_TIME = 240
# Number of people in the queuing scene.
EXPECTED_PERSONS = 3

class SceneIdentityCollector:
  """! Collects the resolved-identity counter published for a scene.

  The per-object ids and reid states are collected alongside it so a failure can
  explain which identities the counter is made of, rather than only reporting
  that the total is wrong.
  """

  def __init__(self, scene_uid):
    self.scene_uid = scene_uid
    self.topic = PubSub.formatTopic(
      PubSub.DATA_SCENE, scene_id=scene_uid, thing_type="person")
    self.counts = []
    self.frames = []
    self._lock = threading.Lock()
    return

  def on_connect(self, mqttc, userdata, flags, rc):
    """! Subscribe once the broker connection is established."""
    log.info("Connected to MQTT Broker")
    mqttc.subscribe(self.topic, 0)
    log.info(f"Subscribed to the topic {self.topic}")
    return

  def on_message(self, mqttc, userdata, msg):
    json_data = json.loads(msg.payload.decode("utf-8"))
    if json_data.get("id") != self.scene_uid:
      return

    count = json_data.get("max_resolved_identities")
    if count is None:
      return

    people = {}
    for obj in json_data.get("objects", []):
      if obj.get("category") != "person" or not obj.get("id"):
        continue
      people[obj["id"]] = {
        "reid_state": obj.get("reid_state"),
        "previous_ids_chain": obj.get("previous_ids_chain") or [],
      }

    with self._lock:
      self.counts.append(count)
      self.frames.append(people)
    return

  def snapshot(self):
    with self._lock:
      return list(self.counts), list(self.frames)

def describe_identities(counts, frames):
  """! Log what the resolved-identity total is actually made of.

  @param    counts    List of max_resolved_identities values, in order.
  @param    frames    List of per-frame dicts of person ID -> record.
  """
  published_ids = {obj_id for people in frames for obj_id in people}
  superseded = set()
  for people in frames:
    for record in people.values():
      for entry in record["previous_ids_chain"]:
        if isinstance(entry, dict) and entry.get("id"):
          superseded.add(entry["id"])

  states = {}
  for people in frames:
    for obj_id, record in people.items():
      states.setdefault(obj_id, record["reid_state"])

  peak = max((len(people) for people in frames), default=0)

  log.info(
    f"Counter reached {counts[-1]} across {len(counts)} messages; "
    f"{len(published_ids)} distinct ids were published, {len(superseded)} of "
    f"them were later superseded, peak {peak} people on screen at once")

  for obj_id in sorted(published_ids):
    seen = sum(1 for people in frames if obj_id in people)
    marker = " (superseded)" if obj_id in superseded else ""
    log.info(
      f"  {obj_id} seen in {seen} messages, reid_state "
      f"{states.get(obj_id)}{marker}")

  return

def collect_counts(collector):
  """! Collect the published identity data for the configured duration.
  @param    collector   SceneIdentityCollector instance.
  @return   tuple       (counts list, frames list).
  """
  interval = 10
  start_time = time.time()

  while time.time() - start_time < COLLECT_TIME:
    time.sleep(interval)
    counts, _ = collector.snapshot()
    latest = counts[-1] if counts else "none"
    log.info(
      f"Status after {int(time.time() - start_time)} / {COLLECT_TIME} sec: "
      f"{len(counts)} messages, max_resolved_identities={latest}")

  return collector.snapshot()

@pytest.mark.test_name("NEX-T29218")
def test_reid_id_persistence(params, result_recorder):
  """! Verify that tracked persons keep a single identity across the run.

  The scene publishes max_resolved_identities, the number of distinct identities
  ReID has resolved since the scene started. People in the looping video
  repeatedly leave and re-enter view, so the counter only stays at the number of
  people in the scene when each of them is re-identified on return. A person who
  comes back as a stranger resolves a brand new identity and pushes it higher.

  @param    params            Dict of test parameters.
  @param    result_recorder   Fixture recording the pass/fail result.
  """
  log.info(
    f"Test that ReID resolves exactly {EXPECTED_PERSONS} identities for the "
    "Queuing scene.")

  client = None
  try:
    rest = RESTClient(params['resturl'], rootcert=params['rootcert'])
    res = rest.authenticate(params['user'], params['password'])
    assert res, (res.errors)

    scene_uid = common.get_scene_uid(params, "Queuing")
    collector = SceneIdentityCollector(scene_uid)

    client = PubSub(params["auth"], None, params["rootcert"], params["broker_url"],
                    port=int(params["broker_port"]))
    client.onConnect = collector.on_connect
    client.addCallback(collector.topic, collector.on_message)
    client.connect()
    client.loopStart()

    counts, frames = collect_counts(collector)
    assert counts, (
      "No scene messages carrying max_resolved_identities were received; "
      "cannot verify ID persistence.")

    resolved = counts[-1]
    describe_identities(counts, frames)

    # The count dips while a track is between identities, so only the settled
    # value is meaningful. A sustained excess is the real failure signal.
    peak = max(counts)
    assert peak <= EXPECTED_PERSONS, (
      f"max_resolved_identities peaked at {peak}, above the {EXPECTED_PERSONS} "
      "people the Queuing scene holds; identities are being created for people "
      "who are already tracked.")

    assert resolved == EXPECTED_PERSONS, (
      f"ReID resolved {resolved} identities, but the Queuing scene only holds "
      f"{EXPECTED_PERSONS} people; persons leaving and re-entering view are not "
      "being re-identified.")

    result_recorder.success()

  finally:
    if client is not None:
      client.loopStop()

  return
