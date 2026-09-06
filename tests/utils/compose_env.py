#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Compose environment helpers for the functional test harness."""

import os


def sync_supass_for_compose(supass):
  """Mirror the session password into the process environment.

  Docker Compose prefers process-environment values over ``--env-file`` for
  pass-through entries such as ``environment: [SUPASS]``. An empty shell
  ``SUPASS`` (e.g. from ``make ... SUPASS=$(SUPASS)``) would otherwise create
  the django admin with a blank password while tests authenticate with the
  session value.
  """
  os.environ["SUPASS"] = supass
