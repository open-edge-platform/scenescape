#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json

import pytest

from tests.utils.ptz_shadow import parse_shadow_records, write_shadow_artifact


def _record(run_id="run-1", timestamp="2026-10-01T10:00:00.000000Z", profile="controller",
            **extra):
  return {"record_type": "ptz_shadow", "profile": profile, "run_id": run_id,
          "observation_timestamp": timestamp, **extra}


def _line(record, prefix="2026-10-26 11:00:00 "):
  return prefix + json.dumps(record, separators=(",", ":"))


class TestParse:
  def test_records_are_found_behind_a_log_prefix(self):
    text = "\n".join([
      "plain log line",
      _line(_record(sequence=1)),
      json.dumps(_record(sequence=2), separators=(",", ":")),
      "{\"record_type\":\"other\"}",
    ])
    assert [r["sequence"] for r in parse_shadow_records(text)] == [1, 2]

  def test_records_are_filtered_by_run_id(self):
    text = "\n".join([_line(_record("a", sequence=1)), _line(_record("b", sequence=2))])
    assert [r["sequence"] for r in parse_shadow_records(text, "b")] == [2]

  def test_a_truncated_record_is_ignored(self):
    text = _line(_record(sequence=1)) + "\n" + _line(_record(sequence=2))[:-5]
    assert [r["sequence"] for r in parse_shadow_records(text)] == [1]


class TestWrite:
  def test_artifact_joins_profiles_ordered_by_time(self, tmp_path):
    records = [
      _record(timestamp="2026-10-01T10:00:02.000000Z", profile="tracker", sequence=3),
      _record(timestamp="2026-10-01T10:00:01.000000Z", profile="controller", sequence=2),
      _record(timestamp="2026-10-01T10:00:01.000000Z", profile="tracker", sequence=1),
    ]
    path = write_shadow_artifact(records, "run-1", root=tmp_path)
    assert path == tmp_path / "run-1.jsonl"
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert [(r["profile"], r["sequence"]) for r in lines] == [
      ("controller", 2), ("tracker", 1), ("tracker", 3)]

  def test_artifact_is_immutable(self, tmp_path):
    write_shadow_artifact([_record()], "run-1", root=tmp_path)
    with pytest.raises(FileExistsError):
      write_shadow_artifact([_record()], "run-1", root=tmp_path)

  def test_records_of_another_run_are_rejected(self, tmp_path):
    with pytest.raises(ValueError, match="other runs"):
      write_shadow_artifact([_record("run-2")], "run-1", root=tmp_path)
    assert not (tmp_path / "run-1.jsonl").exists()

  def test_the_artifact_directory_is_created(self, tmp_path):
    path = write_shadow_artifact([_record()], "run-1", root=tmp_path / "nested" / "dir")
    assert path.exists()
