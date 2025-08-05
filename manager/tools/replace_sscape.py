# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import argparse

def should_edit_file(filename):
  text_extensions = (".py",)
  return filename.endswith(text_extensions)

def replace_in_file(file_path, old_string, new_string):
  try:
    with open(file_path, "r", encoding="utf-8") as f:
      content = f.read()

    if old_string not in content:
      return False

    new_content = content.replace(old_string, new_string)

    with open(file_path, "w", encoding="utf-8") as f:
      f.write(new_content)

    print(f"Updated: {file_path}")
    return True
  except UnicodeDecodeError:
    print(f"Skipped binary or unreadable file: {file_path}")
    return False
  except Exception as e:
    print(f"Error processing {file_path}: {e}")
    return False

def replace_in_directory(root_dir, old_string, new_string):
  for dirpath, _, filenames in os.walk(root_dir):
    if any(part in dirpath for part in [".git", "venv", "__pycache__"]):
      continue
    for filename in filenames:
      if should_edit_file(filename):
        file_path = os.path.join(dirpath, filename)
        replace_in_file(file_path, old_string, new_string)

def main():
  parser = argparse.ArgumentParser(description="Replace string in files recursively.")
  parser.add_argument('--old', required=True, help="String to replace (e.g. 'sscape')")
  parser.add_argument('--new', required=True, help="Replacement string (e.g. 'manager')")
  parser.add_argument('--dir', default='.', help="Root directory to scan (default: current directory)")

  args = parser.parse_args()

  replace_in_directory(args.dir, args.old, args.new)

if __name__ == "__main__":
  main()
