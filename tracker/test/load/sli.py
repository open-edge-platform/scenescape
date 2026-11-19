# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Intel Corporation

"""Dropped-message SLI computation shared by the load tests and their summary.

tracker.mqtt.messages counts accepted messages only. Messages rejected on
arrival (parse, schema, unknown camera, lag) are counted only in
tracker.mqtt.dropped, with a ``rejected_*`` reason, so they are added to the
received total. Messages dropped later (``dropped_*``, e.g. queue full) were
already counted as accepted.
"""

REJECTED_REASON_PREFIX = "rejected_"


def message_counts(accepted: float, drop_reasons: dict[str, float]) -> dict[str, int]:
  """Return received, accepted, rejected and dropped message counts."""
  rejected = sum(count for reason, count in drop_reasons.items()
                 if reason.startswith(REJECTED_REASON_PREFIX))
  dropped = sum(drop_reasons.values())
  return {
    "received": int(accepted + rejected),
    "accepted": int(accepted),
    "rejected": int(rejected),
    "dropped": int(dropped),
  }


def drop_gate(dropped: float, received: float, max_ratio: float) -> tuple[float, bool]:
  """Return the dropped/received ratio and whether the gate passes.

  A run in which the tracker received no messages fails: nothing was measured.
  """
  if received <= 0:
    return 0.0, False
  ratio = dropped / received
  return ratio, ratio < max_ratio


def drop_summary(summary: dict, max_ratio: float) -> tuple[str, str]:
  """Return the summary table's ``Actual`` and ``Result`` cells for the gate."""
  if "received" not in summary:
    return "n/a", "n/a"
  ratio, passed = drop_gate(summary.get("dropped", 0), summary["received"], max_ratio)
  actual = f"{ratio:.4%}" if summary["received"] > 0 else "n/a"
  return actual, "PASS" if passed else "FAIL"
