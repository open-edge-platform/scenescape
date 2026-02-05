# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Format conversion utilities for tracker evaluation pipeline.

This module provides utilities for converting between JSON and CSV formats using:
- python-rapidjson for fast JSON serialization/deserialization
- jsonpointer (RFC 6901) for accessing nested JSON data
- Dask for efficient CSV reading and writing
"""

from typing import Any, Dict, List, Union
import rapidjson
from jsonpointer import JsonPointer
import dask.dataframe as dd
import pandas as pd
from pathlib import Path


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

  Args:
    input_data: Input JSON as string, file path, or dictionary
    mapping: Dictionary mapping output JSON pointers to input JSON pointers
            Format: {"/output/path": "/input/path"}
    output_path: Optional path to write output JSON file

  Returns:
    Converted JSON as dictionary

  Example:
    >>> mapping = {"/scene/name": "/sceneName", "/scene/id": "/sceneId"}
    >>> convert_json_to_json(input_dict, mapping, "output.json")
  """
  # Load input data
  if isinstance(input_data, str):
    if Path(input_data).exists():
      with open(input_data, 'r') as f:
        data = rapidjson.load(f)
    else:
      data = rapidjson.loads(input_data)
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
    except Exception as e:
      raise ValueError(
        f"Error mapping {input_pointer} -> {output_pointer}: {e}"
      )

  # Write output if path provided
  if output_path:
    with open(output_path, 'w') as f:
      rapidjson.dump(output, f, indent=2)

  return output


def convert_json_to_csv(
  input_data: Union[str, Dict[str, Any], List[Dict[str, Any]]],
  mapping: Dict[str, Union[Dict[str, str], Any]],
  output_path: str,
  include_header: bool = False
) -> pd.DataFrame:
  """Convert JSON to CSV using column mapping.

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
    DataFrame with converted data

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
    if Path(input_data).exists():
      with open(input_data, 'r') as f:
        data = rapidjson.load(f)
    else:
      data = rapidjson.loads(input_data)
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
  """Read JSON file using rapidjson.

  Args:
    file_path: Path to JSON file

  Returns:
    Parsed JSON data
  """
  with open(file_path, 'r') as f:
    return rapidjson.load(f)


def write_json(data: Any, file_path: str, indent: int = 2) -> None:
  """Write data to JSON file using rapidjson.

  Args:
    data: Data to serialize
    file_path: Output file path
    indent: Indentation level (default: 2)
  """
  with open(file_path, 'w') as f:
    rapidjson.dump(data, f, indent=indent)
