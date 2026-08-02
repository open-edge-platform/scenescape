#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Host-port allocation for multi-controller hierarchy ReID compose profiles."""

import os
import socket
from contextlib import closing

_ROLE_KEYS = {
  "parent": ("PARENT_WEB_PORT", "PARENT_BROKER_PORT", "parent-web", "parent-broker"),
  "child1": ("CHILD1_WEB_PORT", "CHILD1_BROKER_PORT", "child1-web", "child1-broker"),
  "child2": ("CHILD2_WEB_PORT", "CHILD2_BROKER_PORT", "child2-web", "child2-broker"),
}

_REID_ENDPOINTS = {
  "shared": ("reid.scenescape.intel.com", "REID_SHARED_PORT"),
  "a": ("reid-a.scenescape.intel.com", "REID_A_PORT"),
  "b": ("reid-b.scenescape.intel.com", "REID_B_PORT"),
}

HIERARCHY_PORT_ENV_KEYS = (
  "PARENT_WEB_PORT",
  "PARENT_BROKER_PORT",
  "CHILD1_WEB_PORT",
  "CHILD1_BROKER_PORT",
  "CHILD2_WEB_PORT",
  "CHILD2_BROKER_PORT",
  "REID_SHARED_PORT",
  "REID_A_PORT",
  "REID_B_PORT",
)


def _free_port():
  with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
    sock.bind(("127.0.0.1", 0))
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    return sock.getsockname()[1]


def allocate_hierarchy_ports():
  """Return env dict of unique host ports for parent/child1/child2/VDMS services."""
  return {key: str(_free_port()) for key in HIERARCHY_PORT_ENV_KEYS}


def clear_hierarchy_port_env(environ=None):
  """Remove hierarchy host-port keys from *environ* (default ``os.environ``)."""
  env = os.environ if environ is None else environ
  for key in HIERARCHY_PORT_ENV_KEYS:
    env.pop(key, None)


def hierarchy_params(secrets_dir, supass, ports, role):
  """Build a params dict for parent|child1|child2 host access."""
  web_port_key, broker_port_key, web_host, broker_host = _ROLE_KEYS[role]
  web_port = ports[web_port_key]
  broker_port = int(ports[broker_port_key])
  return {
    "user": "admin",
    "password": supass,
    "auth": f"{secrets_dir}/controller.auth",
    "rootcert": f"{secrets_dir}/certs/scenescape-ca.pem",
    "broker_url": f"{broker_host}.scenescape.intel.com",
    "broker_port": broker_port,
    "weburl": f"https://{web_host}.scenescape.intel.com:{web_port}",
    "resturl": f"https://{web_host}.scenescape.intel.com:{web_port}/api/v1",
    "scene_name": "Demo",
    "docker_broker_host": f"{broker_host}.scenescape.intel.com",
    "role": role,
  }


def reid_endpoint(ports, which="shared"):
  """Return (hostname, host_port) for a hierarchy VDMS instance."""
  hostname, port_key = _REID_ENDPOINTS[which]
  return hostname, int(ports[port_key])
