# Copyright (C) 2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

"""
This module provides a Django management command that is used to indicate when the
database is ready when adding users and scenes during initialization.
"""

from django.core.management.base import BaseCommand
from django.db import DatabaseError
from manager.models import DatabaseStatus
from scene_common import log

class Command(BaseCommand):
  def add_arguments(self, parser):
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ready", action="store_true",
                       help="Indicate that the database is ready")
    group.add_argument("--not-ready", action="store_false", dest="ready",
                       help="Indicate that the database is not ready")

  def handle(self, *args, **kwargs):
    status = kwargs['ready']
    try:
      db_status = DatabaseStatus.get_instance()
    except DatabaseError:
      log.warn("Database status does not exist in the database.")
      return
    db_status.is_ready = status
    db_status.save()
    log.info(f"Database status updated to {'ready' if status else 'not ready'}")
    return
