#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

def record_test_result(name: str, error: int):
  print(f"\n{name}:", "FAIL" if error else "PASS")
  print("-----------------------------\n")
  return
