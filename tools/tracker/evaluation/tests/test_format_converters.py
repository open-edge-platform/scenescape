# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for format conversion utilities."""

import sys
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.format_converters import (
  convert_canonical_to_motchallenge_csv,
  convert_json_to_json,
  convert_json_to_csv,
  read_csv_to_dataframe,
  read_json,
  write_json,
  write_jsonl,
  stream_jsonl
)


class TestJSONToJSON:
  """Tests for JSON to JSON conversion."""

  def test_simple_mapping(self):
    """Test basic JSON pointer mapping."""
    input_data = {
      "scene": {"name": "Retail", "id": 123},
      "cameras": ["cam1", "cam2"]
    }

    mapping = {
      "/sceneName": "/scene/name",
      "/sceneId": "/scene/id",
      "/cameraList": "/cameras"
    }

    result = convert_json_to_json(input_data, mapping)

    assert result == {
      "sceneName": "Retail",
      "sceneId": 123,
      "cameraList": ["cam1", "cam2"]
    }

  def test_nested_output(self):
    """Test creating nested output structure."""
    input_data = {"x": 1.5, "y": 2.5, "z": 3.5}

    mapping = {
      "/location/x": "/x",
      "/location/y": "/y",
      "/location/z": "/z"
    }

    result = convert_json_to_json(input_data, mapping)

    assert result == {
      "location": {"x": 1.5, "y": 2.5, "z": 3.5}
    }

  def test_file_output(self):
    """Test writing to file."""
    input_data = {"name": "test"}
    mapping = {"/outputName": "/name"}

    with tempfile.TemporaryDirectory() as tmpdir:
      output_path = Path(tmpdir) / "output.json"
      result = convert_json_to_json(input_data, mapping, str(output_path))

      assert output_path.exists()
      loaded = read_json(str(output_path))
      assert loaded == result


class TestJSONToCSV:
  """Tests for JSON to CSV conversion."""

  def test_simple_conversion(self):
    """Test basic JSON to CSV conversion."""
    input_data = [
      {"frameId": 1, "objId": 10, "x": 1.5},
      {"frameId": 2, "objId": 10, "x": 2.5}
    ]

    mapping = {
      "frame": {"pointer": "/frameId"},
      "id": {"pointer": "/objId"},
      "x": {"pointer": "/x"},
      "class": {"value": -1}
    }

    with tempfile.TemporaryDirectory() as tmpdir:
      output_path = Path(tmpdir) / "output.csv"
      df = convert_json_to_csv(input_data, mapping, str(output_path))

      assert len(df) == 2
      assert list(df.columns) == ["frame", "id", "x", "class"]
      assert df["frame"].tolist() == [1, 2]
      assert df["class"].tolist() == [-1, -1]

  def test_motchallenge_format(self):
    """Test MOTChallenge 3D CSV format conversion."""
    input_data = [
      {
        "frameId": 1,
        "objectId": 5,
        "location": {"x": 10.5, "y": 20.5, "z": 1.5},
        "confidence": 0.95
      }
    ]

    mapping = {
      "frame": {"pointer": "/frameId"},
      "id": {"pointer": "/objectId"},
      "x": {"pointer": "/location/x"},
      "y": {"pointer": "/location/y"},
      "z": {"pointer": "/location/z"},
      "conf": {"pointer": "/confidence"},
      "class": {"value": -1},
      "visibility": {"value": 1}
    }

    with tempfile.TemporaryDirectory() as tmpdir:
      output_path = Path(tmpdir) / "track.csv"
      df = convert_json_to_csv(input_data, mapping, str(output_path))

      assert len(df) == 1
      assert df.iloc[0]["frame"] == 1
      assert df.iloc[0]["id"] == 5
      assert df.iloc[0]["x"] == 10.5
      assert df.iloc[0]["conf"] == 0.95
      assert df.iloc[0]["class"] == -1

  def test_missing_field(self):
    """Test handling of missing fields."""
    input_data = [{"frameId": 1}]

    mapping = {
      "frame": {"pointer": "/frameId"},
      "missing": {"pointer": "/doesNotExist"}
    }

    with tempfile.TemporaryDirectory() as tmpdir:
      output_path = Path(tmpdir) / "output.csv"
      df = convert_json_to_csv(input_data, mapping, str(output_path))

      assert df["missing"].isna()[0]


class TestCSVReading:
  """Tests for CSV reading with Dask."""

  def test_read_without_header(self):
    """Test reading CSV without header."""
    with tempfile.TemporaryDirectory() as tmpdir:
      csv_path = Path(tmpdir) / "test.csv"
      csv_path.write_text("1,10,1.5\n2,10,2.5\n")

      df = read_csv_to_dataframe(
        str(csv_path),
        has_header=False,
        column_names=["frame", "id", "x"]
      )

      assert len(df) == 2
      assert list(df.columns) == ["frame", "id", "x"]

  def test_read_with_header(self):
    """Test reading CSV with header."""
    with tempfile.TemporaryDirectory() as tmpdir:
      csv_path = Path(tmpdir) / "test.csv"
      csv_path.write_text("frame,id,x\n1,10,1.5\n2,10,2.5\n")

      df = read_csv_to_dataframe(str(csv_path), has_header=True)

      assert len(df) == 2
      assert list(df.columns) == ["frame", "id", "x"]


class TestJSONIO:
  """Tests for JSON reading and writing."""

  def test_read_write_roundtrip(self):
    """Test reading and writing JSON."""
    data = {"test": "value", "number": 42, "nested": {"key": "val"}}

    with tempfile.TemporaryDirectory() as tmpdir:
      json_path = Path(tmpdir) / "test.json"

      write_json(data, str(json_path))
      loaded = read_json(str(json_path))

      assert loaded == data


class TestJSONL:
  """Tests for newline-delimited JSON helpers."""

  def test_write_and_stream_jsonl(self):
    """Test round-trip for JSONL write and streaming read."""
    objects = [
      {"id": 1, "value": "a"},
      {"id": 2, "value": "b"}
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
      jsonl_path = Path(tmpdir) / "data.jsonl"
      write_jsonl(objects, str(jsonl_path))

      streamed = list(stream_jsonl(str(jsonl_path)))
      assert streamed == objects

  def test_stream_jsonl_generator_consumption(self):
    """Test streaming JSONL lazily yields items in order."""
    objects = [{"index": i} for i in range(5)]

    with tempfile.TemporaryDirectory() as tmpdir:
      jsonl_path = Path(tmpdir) / "lazy.jsonl"
      write_jsonl(objects, str(jsonl_path))

      generator = stream_jsonl(str(jsonl_path))
      first = next(generator)
      assert first == objects[0]
      remaining = list(generator)
      assert remaining == objects[1:]


class TestConvertCanonicalToMOTChallenge:
  """Tests for convert_canonical_to_motchallenge_csv."""

  def _make_output(self, timestamp, uuid, translation):
    return {"timestamp": timestamp, "objects": [{"id": uuid, "translation": translation}]}

  def test_empty_input_writes_empty_file(self, tmp_path):
    csv = tmp_path / "empty.csv"
    result = convert_canonical_to_motchallenge_csv([], str(csv), 30.0)
    assert result == {}
    assert csv.read_text() == ""

  def test_basic_single_frame(self, tmp_path):
    """One frame, one object → one CSV row with correct fields."""
    outputs = [
      {"timestamp": "2026-01-01T00:00:00.000Z",
       "objects": [{"id": "uuid-1", "translation": [1.0, 2.0, 0.5]}]},
    ]
    csv = tmp_path / "track.csv"
    convert_canonical_to_motchallenge_csv(outputs, str(csv), 30.0)

    import pandas as pd
    df = pd.read_csv(str(csv), header=None,
                     names=["frame", "id", "x", "y", "z", "conf", "class", "visibility"])
    assert len(df) == 1
    assert df.iloc[0]["frame"] == 1
    assert df.iloc[0]["x"] == 1.0
    assert df.iloc[0]["y"] == 2.0
    assert df.iloc[0]["z"] == 0.5

  def test_frame_numbers_computed_from_timestamps(self, tmp_path):
    """Timestamps 33 ms apart at 30 fps produce consecutive frame numbers."""
    outputs = [
      {"timestamp": "2026-01-01T00:00:00.000Z",
       "objects": [{"id": "uuid-1", "translation": [0.0, 0.0, 0.0]}]},
      {"timestamp": "2026-01-01T00:00:00.033Z",
       "objects": [{"id": "uuid-1", "translation": [1.0, 0.0, 0.0]}]},
    ]
    csv = tmp_path / "track.csv"
    convert_canonical_to_motchallenge_csv(outputs, str(csv), 30.0)

    import pandas as pd
    df = pd.read_csv(str(csv), header=None,
                     names=["frame", "id", "x", "y", "z", "conf", "class", "visibility"])
    assert list(df["frame"]) == [1, 2]

  def test_uuids_mapped_to_stable_integers(self, tmp_path):
    """Each distinct UUID gets a unique integer ID that persists across frames."""
    outputs = [
      {"timestamp": "2026-01-01T00:00:00.000Z",
       "objects": [
         {"id": "uuid-a", "translation": [0.0, 0.0, 0.0]},
         {"id": "uuid-b", "translation": [1.0, 0.0, 0.0]},
       ]},
    ]
    csv = tmp_path / "track.csv"
    mapping = convert_canonical_to_motchallenge_csv(outputs, str(csv), 30.0)

    assert len(mapping) == 2
    assert mapping["uuid-a"] != mapping["uuid-b"]

    import pandas as pd
    df = pd.read_csv(str(csv), header=None,
                     names=["frame", "id", "x", "y", "z", "conf", "class", "visibility"])
    assert set(df["id"]) == {mapping["uuid-a"], mapping["uuid-b"]}

  def test_duplicate_frame_track_pair_skipped(self, tmp_path):
    """Two entries with different timestamps that round to the same frame number
    produce only one CSV row per (frame, track_id) — the first is kept."""
    # At 30 fps, frame duration = 1/30 s ≈ 33.3 ms.
    # T=0.000 s → frame 1; T=0.001 s also → frame 1 (rounds to 0 + 1).
    outputs = [
      {"timestamp": "2026-01-01T00:00:00.000Z",
       "objects": [{"id": "uuid-1", "translation": [1.0, 0.0, 0.0]}]},
      {"timestamp": "2026-01-01T00:00:00.001Z",
       "objects": [{"id": "uuid-1", "translation": [9.9, 0.0, 0.0]}]},
    ]
    csv = tmp_path / "track.csv"
    convert_canonical_to_motchallenge_csv(outputs, str(csv), 30.0)

    import pandas as pd
    df = pd.read_csv(str(csv), header=None,
                     names=["frame", "id", "x", "y", "z", "conf", "class", "visibility"])
    assert len(df) == 1, "Duplicate (frame, id) row must be dropped"
    assert df.iloc[0]["x"] == 1.0, "First occurrence must be kept"

  def test_same_track_different_frames_both_kept(self, tmp_path):
    """Same UUID across two distinct frames produces two rows — no false dedup."""
    outputs = [
      {"timestamp": "2026-01-01T00:00:00.000Z",
       "objects": [{"id": "uuid-1", "translation": [1.0, 0.0, 0.0]}]},
      {"timestamp": "2026-01-01T00:00:00.033Z",
       "objects": [{"id": "uuid-1", "translation": [2.0, 0.0, 0.0]}]},
    ]
    csv = tmp_path / "track.csv"
    convert_canonical_to_motchallenge_csv(outputs, str(csv), 30.0)

    import pandas as pd
    df = pd.read_csv(str(csv), header=None,
                     names=["frame", "id", "x", "y", "z", "conf", "class", "visibility"])
    assert len(df) == 2
    assert list(df["frame"]) == [1, 2]
