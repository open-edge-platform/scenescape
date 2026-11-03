# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Apply reid-service identity decisions to Tracker scene objects.

reid-service publishes one message per decision on
``scenescape/data/reid/{scene_id}/{category}``:

  {"track_id": ..., "gid": ..., "matched": bool, "similarity": float|None,
   "timestamp": ..., "decided_at": ...}

Before analytics processes a scene message, each object whose Tracker id has a
*matched* decision gets that gid as its ``id``, plus the ``reid_state``,
``similarity`` and ``previous_ids_chain`` fields the Controller used to emit.
Regions, tripwires, events and the regulated topic then all see the
re-identified id, exactly as with Controller-produced scene data.

A no-match normally reuses the track id, but may assign a fresh gid to avoid
a live identity collision. Honor that gid while retaining the no-match state.
"""

import json
import time

from scene_common import log
from scene_common.mqtt import PubSub
from scene_common.reid_constants import REID_STATES

REID_DECISION_TOPIC = PubSub.formatTopic(PubSub.DATA_REID, scene_id="+", thing_type="+")
# Forget a decision once its track has not appeared in scene data for this long.
DEFAULT_IDENTITY_TTL_SECS = 30.0


class ReidIdentityMap:
  """(scene_id, category, track_id) -> latest reid-service decision."""

  def __init__(self, ttl_secs=DEFAULT_IDENTITY_TTL_SECS, clock=time.time):
    self.ttl_secs = ttl_secs
    self.clock = clock
    self._decisions = {}
    self._last_seen = {}
    self._unique_counts = {}

  def __len__(self):
    return len(self._decisions)

  def update(self, payload):
    """Record one decision message (bytes, str or dict). Returns True if stored."""
    try:
      decision = json.loads(payload) if isinstance(payload, (bytes, bytearray, str)) else payload
      key = (str(decision["scene_id"]), str(decision["category"]), str(decision["track_id"]))
      gid = str(decision["gid"])
      reid_state = decision.get("reid_state", "matched" if decision.get("matched") else "query_no_match")
      if reid_state not in REID_STATES:
        raise ValueError("Unknown ReID state")
      unique_count = decision.get("unique_id_count")
      if unique_count is not None and (type(unique_count) is not int or unique_count < 0):
        raise ValueError("Invalid unique identity count")
    except (ValueError, TypeError, KeyError) as err:
      log.warning(f"Ignoring malformed ReID decision: {err}")
      return False
    self._decisions[key] = {
      "gid": gid,
      "matched": bool(decision.get("matched")),
      "reid_state": reid_state,
      "similarity": decision.get("similarity"),
      "decided_at": decision.get("decided_at") or decision.get("timestamp"),
    }
    self._last_seen[key] = self.clock()
    if unique_count is not None:
      self._unique_counts[key[:2]] = unique_count
    return True

  def uniqueDetectionCount(self, scene_id, category):
    """Return the matcher-owned cumulative count, independent of active object states."""
    return self._unique_counts.get((str(scene_id), str(category)))

  def apply(self, scene_id, category, objects, rename_object=None):
    """
    Apply assigned identities in place. Call before analytics consumes them.

    @param   scene_id  scene the objects belong to
    @param   category  thing_type from the topic (used when an object omits it)
    @param   objects   list of scene-data object dicts
    @param   rename_object  optional (category, old_id, new_id) cache migration;
                returning False defers a conflicting rename
    @return  number of objects whose id was replaced
    """
    now = self.clock()
    rewritten = 0
    for obj in objects or []:
      track_id = obj.get("id")
      if track_id is None:
        continue
      key = (str(scene_id), str(obj.get("category") or category), str(track_id))
      decision = self._decisions.get(key)
      if decision is None:
        obj.setdefault("reid_state", "pending_collection")
        continue
      self._last_seen[key] = now
      if decision["gid"] != track_id and rename_object is not None:
        if rename_object(key[1], track_id, decision["gid"]) is False:
          continue
      obj["reid_state"] = decision["reid_state"]
      if decision["reid_state"] != "matched":
        if decision["gid"] != track_id:
          obj["id"] = decision["gid"]
          rewritten += 1
        continue
      obj["similarity"] = decision["similarity"]
      if decision["gid"] == track_id:
        continue
      obj["id"] = decision["gid"]
      obj["previous_ids_chain"] = [{
        "id": track_id,
        "timestamp": decision["decided_at"],
        "similarity_score": decision["similarity"],
      }]
      rewritten += 1
    self._prune(now)
    return rewritten

  def _prune(self, now):
    stale = [key for key, seen in self._last_seen.items() if now - seen > self.ttl_secs]
    for key in stale:
      self._last_seen.pop(key, None)
      self._decisions.pop(key, None)
