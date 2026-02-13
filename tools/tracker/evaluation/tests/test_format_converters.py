# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for format conversion utilities."""

import sys
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.format_converters import (
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
