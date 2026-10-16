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

A no-match leaves the id unchanged (reid-service reuses the track id as the
gid), so only matches change what downstream consumers see.
"""

import json
import time

from scene_common import log
from scene_common.mqtt import PubSub

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

  def __len__(self):
    return len(self._decisions)

  def update(self, payload):
    """Record one decision message (bytes, str or dict). Returns True if stored."""
    try:
      decision = json.loads(payload) if isinstance(payload, (bytes, bytearray, str)) else payload
      key = (str(decision["scene_id"]), str(decision["category"]), str(decision["track_id"]))
      gid = str(decision["gid"])
    except (ValueError, TypeError, KeyError) as err:
      log.warning(f"Ignoring malformed ReID decision: {err}")
      return False
    self._decisions[key] = {
      "gid": gid,
      "matched": bool(decision.get("matched")),
      "similarity": decision.get("similarity"),
      "decided_at": decision.get("decided_at") or decision.get("timestamp"),
    }
    self._last_seen[key] = self.clock()
    return True

  def apply(self, scene_id, category, objects):
    """
    Rewrite matched objects in place. Call before analytics consumes them.

    @param   scene_id  scene the objects belong to
    @param   category  thing_type from the topic (used when an object omits it)
    @param   objects   list of scene-data object dicts
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
        continue
      self._last_seen[key] = now
      if not decision["matched"]:
        obj.setdefault("reid_state", "query_no_match")
        if decision["gid"] != track_id:
          obj["id"] = decision["gid"]
          rewritten += 1
        continue
      if decision["gid"] == track_id:
        continue
      obj["id"] = decision["gid"]
      obj["reid_state"] = "matched"
      obj["similarity"] = decision["similarity"]
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
