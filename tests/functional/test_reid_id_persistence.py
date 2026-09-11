#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import math
import threading
import time

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
# Frames within which a newly minted ID is considered a possible continuation of
# a track that just vanished.
HANDOFF_FRAME_TOLERANCE = 3
# Scene-space distance (metres) within which a replacement ID is close enough to
# the vanished track to be the same person.
HANDOFF_DISTANCE_M = 1.5
# A track must be seen at least this many frames to count as an established
# identity rather than a short-lived provisional one.
# TODO: COULD BE TOO STRICT???
ESTABLISHED_TRACK_FRAMES = 60
# ReID is allowed to publish a person under a provisional ID for this long while
# the similarity query resolves. Observed settle time is 22-34 frames.
MAX_PROVISIONAL_FRAMES = 60

class ScenePersonCollector:
  """! Collects the tracked person records seen in each scene frame."""

  def __init__(self, scene_uid):
    self.scene_uid = scene_uid
    self.topic = PubSub.formatTopic(
      PubSub.DATA_SCENE, scene_id=scene_uid, thing_type="person")
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

    people = {}
    for obj in json_data.get("objects", []):
      if obj.get("category") != "person" or not obj.get("id"):
        continue
      people[obj["id"]] = {
        "translation": obj.get("translation"),
        "reid_state": obj.get("reid_state"),
        "previous_ids_chain": obj.get("previous_ids_chain") or [],
      }

    with self._lock:
      self.frames.append(people)
    return

  def snapshot(self):
    with self._lock:
      return list(self.frames)

def distance_between(first, second):
  """! Planar distance between two scene-space translations.
  @param    first     Translation list, or None.
  @param    second    Translation list, or None.
  @return   float     Distance in metres, or None when either is unusable.
  """
  if not first or not second or len(first) < 2 or len(second) < 2:
    return None
  return math.dist(first[:2], second[:2])

def build_tracks(frames):
  """! Locate the first and last frame each ID appears in.
  @param    frames    List of per-frame dicts of person ID -> record.
  @return   tracks    Dict of ID -> {first, last, seen}.
  """
  tracks = {}
  for index, people in enumerate(frames):
    for obj_id in people:
      track = tracks.setdefault(obj_id, {"first": index, "last": index, "seen": 0})
      track["last"] = index
      track["seen"] += 1
  return tracks

def find_identity_links(frames, tracks):
  """! Find IDs that continue an earlier track, i.e. the same person appearing
  under a new identity.

  ReID's own previous_ids_chain is authoritative. It is published on the object
  that survives the swap, which may be an ID that has been seen before, so the
  chain has to be read across every frame rather than only where a new ID first
  appears. Spatial proximity is used as a secondary signal for handoffs the
  chain does not record.

  @param    frames    List of per-frame dicts of person ID -> record.
  @param    tracks    Output of build_tracks().
  @return   links     List of dicts describing each link.
  """
  links = []
  seen_pairs = set()

  for index, people in enumerate(frames):
    for obj_id, record in people.items():
      for entry in record["previous_ids_chain"]:
        if not isinstance(entry, dict):
          continue
        old_id = entry.get("id")
        if old_id == obj_id or old_id not in tracks:
          continue
        pair = (old_id, obj_id)
        if pair in seen_pairs:
          continue
        seen_pairs.add(pair)
        links.append({
          "old_id": old_id,
          "new_id": obj_id,
          "frame": index,
          "via": "previous_ids_chain",
          "distance": None,
        })

  chained = {new_id for _, new_id in seen_pairs}

  for new_id, new_track in tracks.items():
    start = new_track["first"]
    if start == 0 or new_id in chained:
      continue

    for old_id, old_track in tracks.items():
      if old_id == new_id or old_track["last"] >= len(frames) - 1:
        continue
      if abs(start - old_track["last"]) > HANDOFF_FRAME_TOLERANCE:
        continue
      gap = distance_between(
        frames[old_track["last"]][old_id]["translation"],
        frames[start][new_id]["translation"])
      if gap is not None and gap <= HANDOFF_DISTANCE_M:
        links.append({
          "old_id": old_id,
          "new_id": new_id,
          "frame": start,
          "via": "proximity",
          "distance": gap,
        })
        break

  return links

def peak_concurrent_persons(frames):
  """! Largest number of person objects published in any single frame.

  The scene never holds more than EXPECTED_PERSONS people at once, so a frame
  carrying more than that is an over-detection regardless of how the IDs are
  later grouped.

  @param    frames    List of per-frame dicts of person ID -> record.
  @return   tuple     (peak count, index of the first frame reaching it).
  """
  peak = 0
  peak_frame = None
  for index, people in enumerate(frames):
    if len(people) > peak:
      peak = len(people)
      peak_frame = index
  return peak, peak_frame

def find_conflicting_links(frames, links):
  """! Find links that claim one person for two simultaneously visible IDs.

  One person cannot be two objects at once, so if the superseded ID and its replacement
  are published in the same frames for longer than a handoff, the link joins
  two different people and the grouping below it cannot be trusted.

  @param    frames        List of per-frame dicts of person ID -> record.
  @param    links         Output of find_identity_links().
  @return   conflicts     List of links annotated with their overlap length.
  """
  conflicts = []
  for link in links:
    overlap = sum(1 for people in frames
                  if link["old_id"] in people and link["new_id"] in people)
    if overlap > HANDOFF_FRAME_TOLERANCE:
      conflicts.append({**link, "overlap": overlap})
  return conflicts

def established_identities(tracks):
  """! IDs held long enough to count as a lasting identity.
  @param    tracks    Output of build_tracks().
  @return   set       IDs seen at least ESTABLISHED_TRACK_FRAMES frames.
  """
  return {obj_id for obj_id, track in tracks.items()
          if track["seen"] >= ESTABLISHED_TRACK_FRAMES}

def group_identities(tracks, links):
  """! Merge linked IDs into one cluster per real person.
  @param    tracks    Output of build_tracks().
  @param    links     Output of find_identity_links().
  @return   clusters  List of sets of IDs, one per person.
  """
  parent = {obj_id: obj_id for obj_id in tracks}

  def find(obj_id):
    while parent[obj_id] != obj_id:
      parent[obj_id] = parent[parent[obj_id]]
      obj_id = parent[obj_id]
    return obj_id

  for link in links:
    left, right = find(link["old_id"]), find(link["new_id"])
    if left != right:
      parent[left] = right

  clusters = {}
  for obj_id in tracks:
    clusters.setdefault(find(obj_id), set()).add(obj_id)
  return list(clusters.values())

def report_unlinked_clusters(frames, tracks, clusters):
  """! Explain every cluster that never resolved to an established identity.

  A short-lived track that ReID never linked to anyone is either a genuine extra
  person, a duplicate detection of somebody already tracked, or a re-entry that
  failed to be re-identified. These are distinguished by checking which
  established identities were on screen at the same time, and how far away the
  nearest of them was.

  @param    frames      List of per-frame dicts of person ID -> record.
  @param    tracks      Output of build_tracks().
  @param    clusters    Output of group_identities().
  """
  established_ids = established_identities(tracks)

  for cluster in clusters:
    if any(obj_id in established_ids for obj_id in cluster):
      continue

    for obj_id in sorted(cluster, key=lambda i: tracks[i]["first"]):
      track = tracks[obj_id]
      present = set()
      absent = set(established_ids)
      nearest = None

      for index in range(track["first"], track["last"] + 1):
        people = frames[index]
        if obj_id not in people:
          continue
        for other in established_ids:
          if other not in people:
            continue
          present.add(other)
          absent.discard(other)
          gap = distance_between(
            people[obj_id]["translation"], people[other]["translation"])
          if gap is not None and (nearest is None or gap < nearest[1]):
            nearest = (other, gap)

      log.info(
        f"Unlinked track {obj_id} frames {track['first']}-{track['last']} "
        f"({track['seen']} seen), reid_state "
        f"{frames[track['first']][obj_id]['reid_state']}")
      log.info(
        f"  {len(present)} of {len(established_ids)} established identities on "
        f"screen at the same time; absent: {sorted(absent) or 'none'}")
      if nearest is not None:
        log.info(
          f"  nearest established identity {nearest[0]} at {nearest[1]:.2f}m")

      for other in sorted(absent):
        other_track = tracks[other]
        log.info(
          f"  {other} was absent; its own span is "
          f"{other_track['first']}-{other_track['last']}")

  return

def check_identity_stability(tracks, links, clusters):
  """! Verify each person resolves to a single lasting identity.

  ReID publishes a person under a provisional ID for a short while
  after they enter, until the similarity query resolves and restores their
  enrolled identity. What must not happen is a person ending up with two
  different established identities, which means they were not recognised on
  return.

  @param    tracks      Output of build_tracks().
  @param    links       Output of find_identity_links().
  @param    clusters    Output of group_identities().
  @return   reasons     List of failure descriptions; empty when all is well.
  """
  reasons = []
  superseded = {link["old_id"] for link in links}

  for index, ids in enumerate(sorted(clusters, key=len, reverse=True)):
    established = sorted(
      (obj_id for obj_id in ids
       if tracks[obj_id]["seen"] >= ESTABLISHED_TRACK_FRAMES),
      key=lambda obj_id: tracks[obj_id]["first"])
    provisional = sorted(
      (obj_id for obj_id in ids if obj_id not in established),
      key=lambda obj_id: tracks[obj_id]["first"])

    log.info(
      f"Person {index}: {len(ids)} IDs total, {len(established)} established, "
      f"{len(provisional)} provisional")
    for obj_id in established:
      track = tracks[obj_id]
      log.info(
        f"  established {obj_id} seen {track['seen']} frames "
        f"(frames {track['first']}-{track['last']})")
    for obj_id in provisional:
      track = tracks[obj_id]
      log.info(
        f"  provisional {obj_id} seen {track['seen']} frames "
        f"(frames {track['first']}-{track['last']})")

    if len(established) > 1:
      reasons.append(
        f"person {index} ended up with {len(established)} established "
        f"identities {established}; they were not re-identified on return")

    if not established:
      spans = ", ".join(
        f"{obj_id} frames {tracks[obj_id]['first']}-{tracks[obj_id]['last']}"
        for obj_id in provisional)
      reasons.append(
        f"person {index} was published as {len(provisional)} provisional "
        f"ID(s) that ReID never resolved to a lasting identity ({spans})")

    for obj_id in provisional:
      if obj_id not in superseded:
        continue
      if tracks[obj_id]["seen"] > MAX_PROVISIONAL_FRAMES:
        reasons.append(
          f"person {index} was published under provisional ID {obj_id} for "
          f"{tracks[obj_id]['seen']} frames, exceeding the "
          f"{MAX_PROVISIONAL_FRAMES} frame budget for ReID to resolve")

  for reason in reasons:
    log.error(reason[0].upper() + reason[1:] + ".")

  return reasons

def collect_frames(collector):
  """! Collect scene frames for the configured duration.
  @param    collector   ScenePersonCollector instance.
  @return   frames      List of per-frame dicts of person ID -> record.
  """
  interval = 10
  start_time = time.time()

  while time.time() - start_time < COLLECT_TIME:
    time.sleep(interval)
    frames = collector.snapshot()
    distinct = len({obj_id for people in frames for obj_id in people})
    log.info(
      f"Status after {int(time.time() - start_time)} / {COLLECT_TIME} sec: "
      f"{len(frames)} frames, {distinct} distinct IDs so far")

  return collector.snapshot()

def test_reid_id_persistence(params, record_xml_attribute):
  """! Verify that tracked persons keep a single identity across the run.

  The unique-count tests only observe the aggregate counter, which stays valid
  even when the tracker swaps IDs between people. This test follows every
  tracked person through the looping video, groups the IDs they were published
  under using ReID's own previous_ids_chain, and fails when a person ends up
  with more than one lasting identity or spends too long under a provisional
  one.

  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  """
  TEST_NAME = "NEX-XXXXXX"
  record_xml_attribute("name", TEST_NAME)
  log.info("Executing: " + TEST_NAME)
  log.info(
    f"Test that {EXPECTED_PERSONS} tracked persons each keep a single identity "
    "when RE-ID is enabled.")

  exit_code = 1
  client = None
  try:
    rest = RESTClient(params['resturl'], rootcert=params['rootcert'])
    res = rest.authenticate(params['user'], params['password'])
    assert res, (res.errors)

    scene_uid = common.get_scene_uid(params, "Queuing")
    collector = ScenePersonCollector(scene_uid)

    client = PubSub(params["auth"], None, params["rootcert"], params["broker_url"],
                    port=int(params["broker_port"]))
    client.onConnect = collector.on_connect
    client.addCallback(collector.topic, collector.on_message)
    client.connect()
    client.loopStart()

    frames = collect_frames(collector)
    assert frames, "No scene messages received; cannot verify ID persistence."

    tracks = build_tracks(frames)
    links = find_identity_links(frames, tracks)
    clusters = group_identities(tracks, links)
    resolved = established_identities(tracks)
    peak, peak_frame = peak_concurrent_persons(frames)
    conflicts = find_conflicting_links(frames, links)

    log.info(
      f"Collected {len(frames)} frames, {len(tracks)} distinct IDs, "
      f"{len(links)} identity links, {len(clusters)} persons, "
      f"{len(resolved)} established identities, peak {peak} concurrent")
    for link in links:
      distance = link["distance"]
      distance_text = "n/a" if distance is None else f"{distance:.2f}m"
      log.info(
        f"  {link['old_id']} -> {link['new_id']} at frame {link['frame']} "
        f"(via {link['via']}, distance {distance_text})")

    assert clusters, "No tracked persons observed; cannot verify ID persistence."
    instability = check_identity_stability(tracks, links, clusters)
    report_unlinked_clusters(frames, tracks, clusters)

    for conflict in conflicts:
      log.error(
        f"Link {conflict['old_id']} -> {conflict['new_id']} (via "
        f"{conflict['via']}) claims one person, but both IDs were published "
        f"together in {conflict['overlap']} frames.")

    # Checked before the grouping results, because a conflicting link merges two
    # people into one cluster and would otherwise mask the identity counts.
    assert not conflicts, (
      f"{len(conflicts)} identity link(s) joined IDs that were on screen at the "
      "same time; ReID linked two different people.")

    assert peak <= EXPECTED_PERSONS, (
      f"Frame {peak_frame} published {peak} people at once, but the scene never "
      f"holds more than {EXPECTED_PERSONS}.")

    assert not instability, (
      f"{len(instability)} identity problem(s): " + "; ".join(instability) + ".")

    assert len(resolved) == EXPECTED_PERSONS, (
      f"Expected {EXPECTED_PERSONS} established identities, found "
      f"{len(resolved)}: {sorted(resolved)}.")

    assert len(clusters) == EXPECTED_PERSONS, (
      f"Expected {EXPECTED_PERSONS} distinct persons, resolved {len(clusters)}; "
      "identities are being created or merged incorrectly.")

    exit_code = 0

  finally:
    if client is not None:
      client.loopStop()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return
