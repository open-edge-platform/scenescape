# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Collects PTZ shadow JSONL records from service logs into an immutable run artifact.

Controller and Tracker emit sampled decision records to stdout only. The acceptance
harness joins them by `run_id` into `tests/artifacts/ptz/shadow/<run_id>.jsonl`.
"""

import json
from pathlib import Path
from typing import Iterable, List, Optional

RECORD_TYPE = "ptz_shadow"
RECORD_MARKER = f'{{"record_type":"{RECORD_TYPE}"'
ARTIFACT_ROOT = Path(__file__).resolve().parents[1] / "artifacts" / "ptz" / "shadow"


def parse_shadow_records(log_text: str, run_id: Optional[str] = None) -> List[dict]:
  """Shadow records in `log_text`, optionally only those of `run_id`; other lines are ignored."""
  records = []
  for line in log_text.splitlines():
    start = line.find(RECORD_MARKER)
    if start < 0:
      continue
    try:
      record = json.loads(line[start:])
    except ValueError:
      continue
    if run_id is None or record.get("run_id") == run_id:
      records.append(record)
  return records


def write_shadow_artifact(records: Iterable[dict], run_id: str,
                          root: Path = ARTIFACT_ROOT) -> Path:
  """Write `<root>/<run_id>.jsonl`, ordered by observation time then profile.

  @raises FileExistsError when the artifact exists: published artifacts are immutable
  """
  ordered = sorted(records, key=lambda r: (r.get("observation_timestamp") or "",
                                           r.get("profile") or ""))
  mismatched = {r.get("run_id") for r in ordered} - {run_id}
  if mismatched:
    raise ValueError(f"Records of other runs cannot join {run_id}: {sorted(mismatched, key=str)}")
  root.mkdir(parents=True, exist_ok=True)
  path = root / f"{run_id}.jsonl"
  with open(path, "x", encoding="utf-8") as artifact:
    for record in ordered:
      artifact.write(json.dumps(record, separators=(",", ":")) + "\n")
  return path
