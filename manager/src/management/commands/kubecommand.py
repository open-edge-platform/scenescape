# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from django.core.management.base import BaseCommand, CommandError
from manager.kubeclient import KubeClient

class Command(BaseCommand):
  def add_arguments(self, parser):
    parser.add_argument("--broker", nargs="?",
                        help="hostname or IP of MQTT broker")
    parser.add_argument("--resturl", default="https://web.scenescape.intel.com/api/v1",
                      help="URL of REST server")
    parser.add_argument("--ntp", help="NTP server, default is to use mqtt broker")
    parser.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem",
                        help="path to ca certificate")
    parser.add_argument("--cert", help="path to client certificate")
    parser.add_argument("--auth", help="user:password or JSON file for MQTT authentication")

  def handle(self, *args, **options):

    print("Kubeclient Container started")
    kubeclient = KubeClient(options['broker'],
                            options['auth'],
                            options['cert'],
                            options['rootcert'],
                            options['resturl'])
    try:
      kubeclient.setup()
    except Exception as e:
      print(f"Kubeclient can't be set up, exception: {e}")
      raise CommandError
    kubeclient.loopForever()
    return
