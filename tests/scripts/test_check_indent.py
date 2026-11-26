# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Check that tracked Python files use 2-space indentation, no trailing
whitespace and no DOS newlines.

Run from anywhere with:
  pytest tests/scripts/test_check_indent.py --confcutdir=tests/scripts
"""

import os
import subprocess
from pathlib import Path

import pytest

from check_common import checkNewline, readFile, stripTrailingWhitespace

REPO_ROOT = Path(__file__).resolve().parents[2]
REINDENT = Path(__file__).resolve().parent / "reindent"

INDENT_CORRECT = 0
INDENT_WRONG = 1
INDENT_TRAILING = 2
INDENT_DOS = 3

MESSAGES = {
  INDENT_WRONG: "Incorrect indentation",
  INDENT_TRAILING: "Trailing whitespace",
  INDENT_DOS: "DOS newlines",
}


def strip_empty_lines(filename):
  """Return the file's lines without empty lines and trailing whitespace."""
  buffer = []
  for line in readFile(filename):
    stripped = line.rstrip()
    if stripped:
      buffer.append(stripped + '\n')
  return buffer


def truncate_last_char(filename):
  with open(filename, 'rb+') as f:
    f.seek(-1, os.SEEK_END)
    f.truncate()


def check_reindent(filename):
  """Return INDENT_CORRECT, INDENT_WRONG, INDENT_TRAILING or INDENT_DOS for a file."""
  subprocess.run([str(REINDENT), '-v', '-n', filename],
                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
  backup = filename + ".reindent.bak"

  ret = INDENT_WRONG
  if os.path.exists(backup):
    if not checkNewline(filename) and checkNewline(backup):
      truncate_last_char(backup)

    if strip_empty_lines(filename) == strip_empty_lines(backup):
      ret = INDENT_CORRECT
    os.remove(backup)
  else:
    ret = INDENT_CORRECT

  original = readFile(filename)
  if stripTrailingWhitespace(filename) != original:
    ret = INDENT_DOS if any(line.endswith('\r\n') for line in original) else INDENT_TRAILING

  return ret


def is_python_file(filename):
  if filename.endswith('.py'):
    return True
  try:
    with open(filename, "r") as f:
      return "#!/usr/bin/env python" in f.readline()
  except UnicodeDecodeError:
    return False


def tracked_files():
  out = subprocess.run(
    ["git", "ls-tree", "--full-tree", "-r", "--name-only", "--full-name", "HEAD"],
    cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True)
  return [REPO_ROOT / name for name in out.stdout.decode("utf-8").splitlines() if name]


def is_text_file(path):
  out = subprocess.run(['file', '--mime', str(path)], stdout=subprocess.PIPE, check=True)
  return 'charset=binary' not in out.stdout.decode("utf-8")


@pytest.mark.test_name("NEX-T10448")
def test_python_indentation(record_xml_attribute):
  record_xml_attribute("name", "NEX-T10448")

  failures = []
  for path in tracked_files():
    if path.is_dir() or not (path.exists() or path.is_symlink()):
      continue
    if not path.is_file():
      failures.append(f"Unable to read: {path}")
      continue
    if not is_text_file(path) or not is_python_file(str(path)):
      continue
    result = check_reindent(str(path))
    if result != INDENT_CORRECT:
      failures.append(f"{MESSAGES[result]}: {path}")

  assert not failures, "\n" + "\n".join(failures)
