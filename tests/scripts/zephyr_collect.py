#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Pytest plugin that dumps the Zephyr ID declared by each collected test.

Loaded with ``-p zephyr_collect`` by ``utils/check_zephyr_mapping.py``. The
effective ID is resolved with ``get_closest_marker`` so it matches what
``record_test_name`` in tests/conftest.py writes into the JUnit XML.
"""

import json


def pytest_addoption(parser):
  group = parser.getgroup("zephyr")
  group.addoption("--zephyr-out", action="store", default=None, metavar="PATH",
                  help="write collected test / Zephyr ID pairs as JSON to PATH")


def pytest_collection_finish(session):
  out = session.config.getoption("zephyr_out", None)
  if not out:
    return

  records = []
  for item in session.items:
    marker = item.get_closest_marker("test_name")
    zephyr_id = marker.args[0] if marker and marker.args else None
    module_name = getattr(getattr(item, "module", None), "TEST_NAME", None)
    records.append({
      "nodeid": item.nodeid,
      # Parametrized variants of one function collapse to this key unless they
      # carry their own test_name mark.
      "function_nodeid": item.nodeid.split("[", 1)[0],
      "zephyr_id": str(zephyr_id) if zephyr_id is not None else None,
      # Legacy declaration style, reported to guide migration to the marker.
      "module_test_name": str(module_name) if module_name is not None else None,
    })

  with open(out, "w", encoding="utf-8") as handle:
    json.dump(records, handle, indent=2)
    handle.write("\n")
