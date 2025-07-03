#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

"""
This script is intended to be used for debugging tests without the use of pytest.
It assumes that there are containers set up using an appropriate .yml file and that
all tests are run out of a container brought up with tools/scenescape-start.

Example commands:
$ docker compose -f tests/common-services-test.yml --project-directory ${PWD} up

$ tools/scenescape-start --image scenescape-manager-test \
    --network applicationsaiscene-intelligenceopensail_scenescape_test

$ ./tests/debugtest.py tests/ui/tc_boundingBox.py
"""

from importlib import import_module
from inspect import getmembers
from pathlib import Path
import argparse
import os
import pprint
import sys
import types

class _RequestPlaceholder:
  def __init__(self, args, fixtures):
    self.config = self._ConfigPlaceholder(args)
    self.fixtures = fixtures

  def getfixturevalue(self, param):
    return self.fixtures[param].__wrapped__()

  class _ConfigPlaceholder:
    def __init__(self, args):
      self.args = args

    def getoption(self, option, default=None):
      if option[2:] in self.args:
        return self.args[option[2:]]
      else:
        return default

def _is_test(Object):
  return isinstance(Object, types.FunctionType) and Object.__name__.startswith("test_")

def _is_fixture(Object):
  return isinstance(Object, types.FunctionType) and hasattr(Object, "_pytestfixturefunction")

def _is_params_func(Object):
  return isinstance(Object, types.FunctionType) and Object.__name__ == "pytest_addoption"

def _resolve_fixtures(fixture_with_args, fixtures, request):
  if fixture_with_args.__code__.co_argcount == 0:
    return fixture_with_args()
  args = fixture_with_args.__code__.co_varnames[:fixture_with_args.__code__.co_argcount]
  params = []
  for arg in args:
    if arg == "request":
      params.append(request)
    elif arg in fixtures:
      params.append(_resolve_fixtures(fixtures[arg].__wrapped__, fixtures, request))
    else:
      # Case where a fixture has a non-fixture arg, need to check if common occurence
      pass
  return fixture_with_args(*params)

def _process_conftest_values(conftest, test_cmdline_params, test_name):
  fixtures = {}
  cmdline_args = {}

  if conftest:
    fixtures = {k: v for (k, v) in getmembers(conftest, _is_fixture)}

    cmdline_options = getmembers(conftest, _is_params_func)
    if cmdline_options:
      parser = argparse.ArgumentParser()
      parser.addoption = parser.add_argument
      cmdline_options[0][1](parser)
      # 25 used to replace "usage: debugtest.py [-h] " from the default string
      parser.usage = ' '.join((str(Path(__file__)), test_name, parser.format_usage()[25:]))
      cmdline_args = parser.parse_args(test_cmdline_params)
      cmdline_args = vars(cmdline_args)

  return fixtures, cmdline_args

def _replace_args(arg, fixtures, request, parameterize_pairs):
  if arg == "request":
    return request
  elif arg == "record_xml_attribute":
    return lambda *args: None
  elif arg in fixtures:
    if fixtures[arg].__wrapped__.__code__.co_argcount != 0:
      return _resolve_fixtures(fixtures[arg].__wrapped__, fixtures, request)
    else:
      return fixtures[arg].__wrapped__()
  elif arg in parameterize_pairs:
    return parameterize_pairs[arg]
  else:
    return None

def run_test(test_path, test_cmdline_params):
  filepath = Path(os.path.relpath(test_path))

  if not Path(filepath).is_file():
    sys.exit(f"Test not found at specified path: {filepath.resolve()}")

  test_name = str(filepath.with_suffix('')).replace('/', '.')
  module = import_module(test_name, package=None)
  conftest = None

  if (filepath.parent.joinpath("conftest.py").is_file()):
    conftest_path = str(filepath.parent).replace('/', '.') + ".conftest"
    conftest = import_module(conftest_path, package=None)

  fixtures, cmdline_args = _process_conftest_values(conftest,
                                                    test_cmdline_params,
                                                    str(filepath))
  request = _RequestPlaceholder(cmdline_args, fixtures)

  tests = getmembers(module, _is_test)

  for _, test in tests:
    testcase = test.__name__
    args = test.__code__.co_varnames[:test.__code__.co_argcount]

    parametrize_args = None
    parametrize_values = [None]
    if "pytestmark" in test.__dict__:
      pytest_parametrize = test.__dict__['pytestmark'][0].args
      parametrize_args = [arg.strip() for arg in pytest_parametrize[0].split(',')]
      parametrize_values = pytest_parametrize[1]
      # print(f"pytest parameters {parametrize_args} and values {parametrize_values}")

    for value in parametrize_values:
      if value is not None:
        if isinstance(value, str):
          parametrize_pairs = dict(zip(parametrize_args, (value,)))
        else:
          parametrize_pairs = dict(zip(parametrize_args, value))
      else:
        parametrize_pairs = None
      test_args = [_replace_args(arg, fixtures, request, parametrize_pairs)
                   for arg in args]
      print(f"DEBUG: Running {testcase}")
      # pprint.pprint(dict(zip(args, test_args)))
      test(*test_args)


if __name__ == "__main__":
  parser = argparse.ArgumentParser(add_help=False)
  parser.add_argument("test", help="path of test to run")
  test_path, args = parser.parse_known_args()
  run_test(test_path.test, args)
