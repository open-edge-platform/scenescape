# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os

WHITESPACE_CORRECT = 0
WHITESPACE_TRAILING = 1
WHITESPACE_DOS = 2
WHITESPACE_TABS = 3

encoding = 'utf-8'

def readFile(filename):
  """
  reads file and returns all the lines as a list

  :param filename: any filename
  :return: buffer
  """

  f = open(filename, 'rb')
  lines = f.readlines()
  return [x.decode("UTF-8") for x in lines]

def checkNewline(filename):
  """
  this function will check if
  last char in file is new-line

  :param filename: any filename
  :return: True/False
  """
  retVal = False
  f = open(filename, 'rb+')
  f.seek(-1, os.SEEK_END)
  val = f.read()
  if val.decode(encoding) == '\n':
    retVal = True
  f.close()

  return retVal

def stripTrailingWhitespace(filename):
  """
  this function will strip trailing
  white spaces from file

  :param filename: any filename
  :return: buffer
  """

  buffer = readFile(filename)
  for idx in range(len(buffer)):
    fulline = buffer[idx].rstrip()
    buffer[idx] = fulline + '\n'

  return buffer

def checkTrailingWhitespace(filename):
  """
  this function will return WHITESPACE_TRAILING if it has trailing
  whitespace, WHITESPACE_DOS if there are DOS CRLF line endings.
  """

  original_buff = readFile(filename)
  trailing_buff = stripTrailingWhitespace(filename)
  if trailing_buff == original_buff:
    ret = WHITESPACE_CORRECT
  else:
    ret = WHITESPACE_TRAILING
    for line in original_buff:
      if line[-2:] == '\r\n':
        ret = WHITESPACE_DOS
        break

  return ret

def checkTabs(filename):
  """
  this function will return WHITESPACE_TABS if there are tab
  characters in the file. In the case of a Makefile it will only allow
  a single tab character at the beginning of a line.
  """

  base = os.path.basename(filename)
  is_makefile = base.startswith("Makefile")
  original_buff = readFile(filename)
  ret = WHITESPACE_CORRECT
  for line in original_buff:
    if is_makefile:
      line = line[1:]
    if '\t' in line:
      ret = WHITESPACE_TABS
      break

  return ret
