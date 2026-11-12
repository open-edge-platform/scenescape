# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Deployment gates for the PTZ acceptance profile."""

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
MOSQUITTO_DIR = REPO_ROOT / "dlstreamer-pipeline-server/mosquitto"


def test_production_compose_and_helm_flags_default_off():
  compose = yaml.safe_load(
    (REPO_ROOT / "sample_data/compose/compose.dl-streamer-example.yml").read_text())
  values = yaml.safe_load((REPO_ROOT / "kubernetes/scenescape-chart/values.yaml").read_text())

  scene_env = compose["services"]["scene"]["environment"]
  assert scene_env["CONTROLLER_PTZ_ENABLED"] == "${CONTROLLER_PTZ_ENABLED:-false}"
  assert scene_env["CONTROLLER_PTZ_SHADOW_MODE"] == "${CONTROLLER_PTZ_SHADOW_MODE:-false}"
  assert values["scene"]["ptz"]["enabled"] is False
  assert values["scene"]["ptz"]["shadowMode"] is False
  assert values["positioning"]["enabled"] is False
  assert values["positioning"]["assignments"] == {}
  assert values["positioning"]["config"]["sources"] == {}


def test_broker_has_no_positioning_specific_listener():
  shared = (MOSQUITTO_DIR / "mosquitto-secure.conf").read_text()
  assert "acl_file" not in shared
  assert "8883" not in shared
  assert not (MOSQUITTO_DIR / "mosquitto-secure-positioning.conf").exists()

  compose = yaml.safe_load(
    (REPO_ROOT / "sample_data/compose/compose.dl-streamer-example.yml").read_text())
  assert compose["configs"]["mosquitto-secure"]["file"] == (
    "./dlstreamer-pipeline-server/mosquitto/mosquitto-secure.conf")


def test_positioning_production_transport_and_single_replica_gates():
  compose = yaml.safe_load(
    (REPO_ROOT / "sample_data/compose/compose.dl-streamer-example.yml").read_text())
  deployment = (REPO_ROOT / "kubernetes/scenescape-chart/templates/positioning/deployment.yaml").read_text()
  network_policy = (REPO_ROOT / "kubernetes/scenescape-chart/templates/positioning/networkpolicy.yaml").read_text()
  assignments = json.loads((REPO_ROOT / "deployment/positioning-assignments.json").read_text())
  certificates = (REPO_ROOT / "tools/certificates/Makefile").read_text()

  positioning_command = compose["services"]["positioning"]["command"]
  assert positioning_command[positioning_command.index("--broker") + 1] == (
    "broker.scenescape.intel.com")
  assert "--cert" not in positioning_command
  assert '"--broker"\n            - "broker.{{ .Release.Namespace }}.svc.cluster.local"' in deployment
  assert "replicas: 1" in deployment
  assert "type: Recreate" in deployment
  assert "readOnly: true" in deployment
  assert "policyTypes:" in network_policy
  assert "port: 1883" in network_policy
  assert "cameraCIDRs" in network_policy
  assert set(assignments) == {"$comment"}
  assert "chmod 0600 $(CASECRETSDIR)/ca/scenescape-ca.key" in certificates
