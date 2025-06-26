# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import json
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db.utils import IntegrityError
from manager.models import PubSubACL

from scene_common import log

USER_ACCESS_CONFIG = "user_access_config.json"

class Command(BaseCommand):
  def add_arguments(self, parser):
    parser.add_argument("auth", nargs='+', help="One or more user:password/JSON files")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Ignore users that already exist")
    return

  def handle(self, *args, **options):
    self.loadUserAccessConfig()
    for auth in options['auth']:
      log.info(f"Adding {auth} to database...")
      user = pw = None

      auth_conf = self.user_access_config.get(os.path.basename(auth), {})
      is_superuser = auth_conf.get('is_superuser', False)
      acl_data = auth_conf.get('acls', [])

      if os.path.exists(auth):
        with open(auth) as json_file:
          data = json.load(json_file)
        user = data.get('user')
        pw = data.get('password')
      else:
        sep = auth.find(':')
        if sep < 0:
          log.error(f"Invalid user/password format in {auth}")
          continue
        user = auth[:sep]
        pw = auth[sep+1:]

      if User.objects.filter(username=user).exists():
        if not options['skip_existing']:
          log.error(f"User \"{user}\" already exists")
          exit(1)
        current_user = User.objects.get(username=user)
        current_user.is_superuser = is_superuser
        current_user.save()

      else:
        current_user = User.objects.create_user(
            username=user,
            password=pw,
            is_superuser=is_superuser
        )

      for acl in acl_data:
        PubSubACL.objects.update_or_create(
            user=current_user,
            topic=acl.get('topic'),
            defaults={'access':acl.get('access', 0)}
        )

  def loadUserAccessConfig(self):
    self.user_access_config = {}
    if os.path.exists(USER_ACCESS_CONFIG):
      with open(USER_ACCESS_CONFIG) as config_json_file:
        try:
          self.user_access_config = json.load(config_json_file)
        except json.JSONDecodeError as e:
          log.error(f"Invalid file {USER_ACCESS_CONFIG}: {e}")
    return
