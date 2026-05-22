# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Format conversion utilities for tracker evaluation pipeline.

This module provides utilities for converting between JSON and CSV formats using:
- orjson for fast JSON serialization/deserialization
- jsonpointer (RFC 6901) for accessing nested JSON data
- Dask for efficient CSV reading and writing
"""

from typing import Any, Dict, Iterable, List, Union
import json
import orjson
from jsonpointer import JsonPointer, JsonPointerException
import dask.dataframe as dd
import pandas as pd
from pathlib import Path


# TODO: Consider using jsonpatch library instead of custom implementation.
# The jsonpatch library provides RFC 6902 operations that can automatically
# create intermediate objects. This would simplify the code and align with
# standards. However, current implementation is sufficient for MVP.
def _set_nested_value(data: Dict[str, Any], pointer: str, value: Any) -> None:
  """Set a value in nested dict using JSON pointer, creating intermediate dicts.

  Args:
    data: Dictionary to modify
    pointer: JSON pointer string (e.g., "/path/to/field")
    value: Value to set
  """
  if not pointer or pointer == "/":
    raise ValueError("Cannot set root value")

  # Split pointer into parts (skip first empty string from leading /)
  parts = pointer.split("/")[1:]

  # Navigate/create nested structure
  current = data
  for part in parts[:-1]:
    # Unescape JSON pointer special characters
    part = part.replace("~1", "/").replace("~0", "~")
    if part not in current:
      current[part] = {}
    current = current[part]

  # Set final value
  final_key = parts[-1].replace("~1", "/").replace("~0", "~")
  current[final_key] = value


def convert_json_to_json(
  input_data: Union[str, Dict[str, Any]],
  mapping: Dict[str, str],
  output_path: str = None
) -> Dict[str, Any]:
  """Convert JSON to JSON using pointer-based mapping.

  This function uses STRICT validation: all fields referenced in the mapping
  must exist in the input data. Missing fields will raise a ValueError.
  This behavior is intended for schema transformations where data completeness
  is critical.

  Args:
    input_data: Input JSON as string, file path, or dictionary
    mapping: Dictionary mapping output JSON pointers to input JSON pointers
            Format: {"/output/path": "/input/path"}
    output_path: Optional path to write output JSON file

  Returns:
    Converted JSON as dictionary

  Raises:
    ValueError: If any field referenced in mapping is missing from input

  Example:
    >>> mapping = {"/scene/name": "/sceneName", "/scene/id": "/sceneId"}
    >>> convert_json_to_json(input_dict, mapping, "output.json")
  """
  # Load input data
  if isinstance(input_data, str):
    path_candidate = Path(input_data)
    if path_candidate.exists():
      data = read_json(str(path_candidate))
    else:
      data = orjson.loads(input_data)
  else:
    data = input_data

  # Build output using mapping
  output = {}
  for output_pointer, input_pointer in mapping.items():
    try:
      # Get value from input using JSON pointer
      input_ptr = JsonPointer(input_pointer)
      value = input_ptr.get(data)

      # Set value in output using custom nested setter
      _set_nested_value(output, output_pointer, value)
    except (JsonPointerException, KeyError) as e:
      raise ValueError(
        f"Error mapping {input_pointer} -> {output_pointer}: {e}"
      ) from e
    except Exception:
      # Bubble up unexpected errors with original traceback
      raise

  # Write output if path provided
  if output_path:
    write_json(output, output_path, indent=2)

  return output


def convert_json_to_csv(
  input_data: Union[str, Dict[str, Any], List[Dict[str, Any]]],
  mapping: Dict[str, Union[Dict[str, str], Any]],
  output_path: str,
  include_header: bool = False
) -> pd.DataFrame:
  """Convert JSON to CSV using column mapping.

  This function uses LENIENT validation: missing fields in the input data
  are set to None (becomes NaN in pandas DataFrame). This behavior is intended
  for data export where partial/incomplete data is common (e.g., tracker
  outputs with missing confidence scores or occluded objects).

  TODO: Consider adding optional 'strict' parameter to control behavior:
    - strict=False (current default): missing fields → None/NaN
    - strict=True: missing fields → raise ValueError

  Args:
    input_data: Input JSON as string, file path, dict, or list of dicts
    mapping: Dictionary mapping CSV column names to values or JSON pointers
            Format: {
              "column1": {"value": <literal_value>},
              "column2": {"pointer": "/path/to/field"}
            }
    output_path: Path to write CSV file
    include_header: Whether to include header row (default: False)

  Returns:
    DataFrame with converted data (missing fields contain NaN)

  Example:
    >>> mapping = {
    ...   "frame": {"pointer": "/frameId"},
    ...   "id": {"pointer": "/objectId"},
    ...   "x": {"pointer": "/location/x"},
    ...   "class": {"value": -1}
    ... }
    >>> convert_json_to_csv(data_list, mapping, "output.csv")
  """
  # Load input data
  if isinstance(input_data, str):
    path_candidate = Path(input_data)
    if path_candidate.exists():
      data = read_json(str(path_candidate))
    else:
      data = orjson.loads(input_data)
  else:
    data = input_data

  # Ensure data is a list
  if not isinstance(data, list):
    data = [data]

  # Convert each JSON object to CSV row
  rows = []
  for item in data:
    row = {}
    for column_name, source in mapping.items():
      if "value" in source:
        # Use literal value
        row[column_name] = source["value"]
      elif "pointer" in source:
        # Extract value using JSON pointer
        try:
          ptr = JsonPointer(source["pointer"])
          row[column_name] = ptr.get(item)
        except Exception:
          row[column_name] = None
      else:
        raise ValueError(
          f"Invalid mapping for column '{column_name}': "
          f"must contain 'value' or 'pointer'"
        )
    rows.append(row)

  # Create DataFrame
  df = pd.DataFrame(rows)

  # Write to CSV using Dask for consistent API
  ddf = dd.from_pandas(df, npartitions=1)
  ddf.to_csv(
    output_path,
    index=False,
    header=include_header,
    single_file=True
  )

  return df


def read_csv_to_dataframe(
  csv_path: str,
  has_header: bool = False,
  column_names: List[str] = None
) -> pd.DataFrame:
  """Read CSV file into DataFrame using Dask.

  Args:
    csv_path: Path to CSV file
    has_header: Whether CSV has header row
    column_names: List of column names (required if no header)

  Returns:
    DataFrame with CSV data

  Example:
    >>> df = read_csv_to_dataframe(
    ...   "track.csv",
    ...   has_header=False,
    ...   column_names=["frame", "id", "x", "y", "z", "conf", "class", "vis"]
    ... )
  """
  if has_header:
    ddf = dd.read_csv(csv_path)
  else:
    if column_names is None:
      raise ValueError("column_names required when has_header=False")
    ddf = dd.read_csv(csv_path, header=None, names=column_names)

  return ddf.compute()


def read_json(file_path: str) -> Any:
  """Read JSON file using orjson."""
  with open(file_path, 'rb') as f:
    return orjson.loads(f.read())


def write_json(data: Any, file_path: str, indent: int = 2) -> None:
  """Write data to JSON file using orjson."""
  serialized: bytes
  if indent in (None, 0):
    serialized = orjson.dumps(data)
  elif indent == 2:
    serialized = orjson.dumps(data, option=orjson.OPT_INDENT_2)
  else:
    serialized = json.dumps(data, indent=indent).encode('utf-8')

  with open(file_path, 'wb') as f:
    f.write(serialized)
    f.write(b"\n")


def write_jsonl(
  data_iterable: Iterable[Any],
  file_path: str,
  buffer_size: int = 1024 * 1024
) -> None:
  """Write iterable of JSON objects to newline-delimited JSON."""
  with open(file_path, 'wb', buffering=buffer_size) as f:
    for obj in data_iterable:
      f.write(orjson.dumps(obj))
      f.write(b"\n")


def stream_jsonl(
  file_path: str,
  buffer_size: int = 1024 * 1024
):
  """Stream newline-delimited JSON objects from disk."""
  with open(file_path, 'rb', buffering=buffer_size) as f:
    for line in f:
      chunk = line.strip()
      if not chunk:
        continue
      yield orjson.loads(chunk)


def convert_canonical_to_motchallenge_csv(
  tracker_outputs: Union[List[Dict[str, Any]], Any],
  output_path: str,
  camera_fps: float,
  uuid_to_id_map: Dict[str, int] = None
) -> Dict[str, int]:
  """Convert canonical tracker output format to MOTChallenge 3D CSV format.

  Converts from canonical JSON format (with UUID IDs and ISO timestamps) to
  MOTChallenge CSV format (with integer IDs and 1-indexed frame numbers).

  CSV format: frame,id,x,y,z,conf,class,visibility (no header)
  - frame: 1-indexed frame number
  - id: integer track ID (mapped from UUID)
  - x,y,z: 3D position in meters
  - conf: confidence score (1.0)
  - class: object class (1 for pedestrian)
  - visibility: visibility flag (1 for visible)

  Args:
    tracker_outputs: Iterator or list of tracker output dictionaries in canonical format
    output_path: Path to write MOTChallenge CSV file
    camera_fps: Camera frame rate (frames per second) for timestamp-to-frame conversion
    uuid_to_id_map: Optional existing UUID-to-integer mapping (for consistency across calls)

  Returns:
    Dictionary mapping UUIDs to integer IDs (for reuse in ground truth conversion)

  Example:
    >>> outputs = [
    ...   {"timestamp": "2026-01-20T10:05:01.000Z", "objects": [
    ...     {"id": "uuid-1", "translation": [1.0, 2.0, 0.0]}
    ...   ]},
    ...   {"timestamp": "2026-01-20T10:05:01.033Z", "objects": [
    ...     {"id": "uuid-1", "translation": [1.1, 2.1, 0.0]}
    ...   ]}
    ... ]
    >>> mapping = convert_canonical_to_motchallenge_csv(outputs, "track.csv", 30.0)
  """
  from datetime import datetime

  # Convert to list if needed
  if not isinstance(tracker_outputs, list):
    tracker_outputs = list(tracker_outputs)

  if not tracker_outputs:
    # Write empty CSV
    Path(output_path).write_text("")
    return uuid_to_id_map or {}

  # Initialize UUID to integer ID mapping
  if uuid_to_id_map is None:
    uuid_to_id_map = {}
  next_id = max(uuid_to_id_map.values()) + 1 if uuid_to_id_map else 1

  # Parse first timestamp as reference (frame 1)
  first_timestamp = datetime.fromisoformat(
    tracker_outputs[0]["timestamp"].replace("Z", "+00:00")
  )
  frame_duration_seconds = 1.0 / camera_fps

  # Convert tracker outputs to CSV rows
  rows = []
  for scene_data in tracker_outputs:
    # Calculate frame number from timestamp
    timestamp = datetime.fromisoformat(
      scene_data["timestamp"].replace("Z", "+00:00")
    )
    time_delta = (timestamp - first_timestamp).total_seconds()
    frame = int(round(time_delta / frame_duration_seconds)) + 1  # 1-indexed

    # Process each object detection
    for obj in scene_data.get("objects", []):
      # Map UUID to integer ID
      uuid = obj["id"]
      if uuid not in uuid_to_id_map:
        uuid_to_id_map[uuid] = next_id
        next_id += 1
      track_id = uuid_to_id_map[uuid]

      # Extract 3D position
      translation = obj["translation"]
      x, y, z = translation[0], translation[1], translation[2]

      # Create CSV row: frame,id,x,y,z,conf,class,visibility
      rows.append({
        "frame": frame,
        "id": track_id,
        "x": x,
        "y": y,
        "z": z,
        "conf": 1.0,  # Default confidence
        "class": 1,   # Pedestrian class
        "visibility": 1  # Fully visible
      })

  # Use convert_json_to_csv to write CSV (no header, lenient validation)
  mapping = {
    "frame": {"pointer": "/frame"},
    "id": {"pointer": "/id"},
    "x": {"pointer": "/x"},
    "y": {"pointer": "/y"},
    "z": {"pointer": "/z"},
    "conf": {"pointer": "/conf"},
    "class": {"pointer": "/class"},
    "visibility": {"pointer": "/visibility"}
  }
  convert_json_to_csv(rows, mapping, output_path, include_header=False)

  return uuid_to_id_map


def create_motchallenge_seqinfo(
  seq_name: str,
  num_frames: int,
  camera_fps: float,
  output_folder: Union[str, Path]
) -> None:
  """Create MOTChallenge seqinfo.ini file for TrackEval.

  Args:
    seq_name: Sequence name
    num_frames: Total number of frames in sequence
    camera_fps: Camera frame rate (frames per second)
    output_folder: Folder where seqinfo.ini will be created

  Example:
    >>> create_motchallenge_seqinfo("test_seq", 100, 30.0, "/tmp/seqs/test_seq")
  """
  import configparser

  output_folder = Path(output_folder)
  output_folder.mkdir(parents=True, exist_ok=True)

  config = configparser.ConfigParser()
  config['Sequence'] = {
    'name': seq_name,
    'imDir': 'img1',  # Required by TrackEval but not used for 3D point tracking
    'frameRate': str(int(camera_fps)),
    'seqLength': str(num_frames),
    'imWidth': '1920',  # Placeholder values
    'imHeight': '1080',
    'imExt': '.jpg'
  }

  seqinfo_path = output_folder / 'seqinfo.ini'
  with open(seqinfo_path, 'w') as f:
    config.write(f)
