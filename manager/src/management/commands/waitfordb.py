# Copyright (C) 2021-2023 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import psycopg2
import time
from scene_common import log
from django.core.management.base import BaseCommand
from django.conf import settings
import manager.models
from django.db.models.base import ModelBase

class Command(BaseCommand):
  def fullExceptionName(self, ex):
    name = ex.__class__.__name__
    module = ex.__class__.__module__
    if module is not None and module != str.__class__.__module__:
      name = module + "." + name
    return name

  def handle(self, *args, **options):
    while True:
      try:
        conn = psycopg2.connect("dbname='" + settings.DATABASES['default']['NAME']
                                + "' user='" + settings.DATABASES['default']['USER']
                                + "' host='" + settings.DATABASES['default']['HOST']
                                + "' password='" + settings.DATABASES['default']['PASSWORD']
                                + "'")
        tables_av = {}
        # This first loop waits for the tables to exist.
        # If one of the tables in the DB doesnt exist, it will end up retrying.
        log.info("Waiting for tables")
        for model, obj in manager.models.__dict__.items():
          if isinstance( obj, ModelBase ):
            data_av = obj.objects.all()
            if model not in tables_av:
              tables_av[model] = len(data_av)

        # This next loop waits for tables to stabilize,
        # Cant wait for them to be non-empty,
        # since an empty DB is a valid usecase.
        time.sleep(10)
        log.info("Waiting for data")
        tables_updated = True
        while tables_updated == True:
          tables_updated = False
          for model, obj in manager.models.__dict__.items():
            if isinstance( obj, ModelBase ):
              table_count = len(obj.objects.all())
              if model not in tables_av or table_count != tables_av[model]:
                tables_av[model] = table_count
                tables_updated = True

          if tables_updated:
            time.sleep(0.5)
          else:
            break

        log.info("Database ready")
        break

      except psycopg2.OperationalError:
        log.error("Server not online")
        time.sleep(2)

      except Exception as ex:
        log.error("W4DB ERROR", self.fullExceptionName(ex), ex)
        time.sleep(2)
