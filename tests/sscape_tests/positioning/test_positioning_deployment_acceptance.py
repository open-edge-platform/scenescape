# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Deployment and security gates for the PTZ acceptance profile."""

import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest
import yaml

from scene_common.positioning_assignments import parse_assignments
from tools.positioning.render_mosquitto_acl import render_acl

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_positioning_acl_is_limited_to_assigned_sources():
  acl = render_acl(
    {
      "camera-a": "resolver-a",
      "camera-b": "resolver-b",
    },
    "resolver-a",
  )

  assert acl.splitlines() == [
    "user positioning.scenescape.intel.com",
    "topic write scenescape/positioning/status/resolver-a",
    "topic read scenescape/cmd/camera/config/camera-a",
    "topic write scenescape/positioning/pose/camera-a",
  ]


@pytest.mark.parametrize("bad_segment", ("", "a/b", "a+", "a#", "a b", "a\nb"))
def test_positioning_acl_rejects_topic_wildcards_and_delimiters(bad_segment):
  with pytest.raises(ValueError):
    render_acl({bad_segment: "resolver-a"}, "resolver-a")

  with pytest.raises(ValueError):
    render_acl({}, bad_segment)


def test_positioning_acl_renders_the_tracked_default_manifest(tmp_path):
  """The Compose broker depends on this succeeding for the shipped manifest."""
  output = tmp_path / "positioning.acl"
  subprocess.run(
    [sys.executable, str(REPO_ROOT / "tools/positioning/render_mosquitto_acl.py"),
     "--assignments", str(REPO_ROOT / "deployment/positioning-assignments.json"),
     "--resolver-id", "positioning-default", "--output", str(output)],
    check=True)

  assert output.read_text().splitlines() == [
    "user positioning.scenescape.intel.com",
    "topic write scenescape/positioning/status/positioning-default",
  ]


def test_positioning_acl_is_never_world_readable(tmp_path):
  """Mosquitto 2.1 crashes on, and will later refuse, world-readable ACL files."""
  script = REPO_ROOT / "tools/positioning/render_mosquitto_acl.py"
  manifest = REPO_ROOT / "deployment/positioning-assignments.json"
  for group, mode in ((None, 0o600), (os.getgid(), 0o640)):
    output = tmp_path / f"{mode:o}.acl"
    command = [sys.executable, str(script), "--assignments", str(manifest),
               "--resolver-id", "positioning-default", "--output", str(output)]
    if group is not None:
      command += ["--group", str(group)]
    subprocess.run(command, check=True)
    assert stat.S_IMODE(output.stat().st_mode) == mode
    assert output.stat().st_gid == os.getgid()


def test_positioning_acl_rendered_with_the_broker_group():
  compose = yaml.safe_load(
    (REPO_ROOT / "sample_data/compose/compose.dl-streamer-example.yml").read_text())
  entrypoint = compose["services"]["positioning-acl-init"]["entrypoint"]
  assert entrypoint[entrypoint.index("--group") + 1] == "${GID:-1000}"
  assert compose["services"]["broker"]["user"] == "${UID:-1000}:${GID:-1000}"

  broker = (REPO_ROOT / "kubernetes/scenescape-chart/templates/broker/deployment.yaml").read_text()
  assert "fsGroup: {{ .Values.broker.gid }}" in broker
  assert "- key: positioning.acl\n                path: positioning.acl\n                mode: 0440" in broker


def test_positioning_acl_ignores_comment_keys_like_the_shared_loader():
  manifest = {"$comment": "x", "camera-a": "resolver-a"}

  assert render_acl(manifest, "resolver-a").splitlines()[2:] == [
    "topic read scenescape/cmd/camera/config/camera-a",
    "topic write scenescape/positioning/pose/camera-a",
  ]
  assert list(parse_assignments(manifest)) == ["camera-a"]


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


def test_positioning_production_transport_and_single_replica_gates():
  compose = yaml.safe_load(
    (REPO_ROOT / "sample_data/compose/compose.dl-streamer-example.yml").read_text())
  broker = (REPO_ROOT / "dlstreamer-pipeline-server/mosquitto/mosquitto-secure.conf").read_text()
  deployment = (REPO_ROOT / "kubernetes/scenescape-chart/templates/positioning/deployment.yaml").read_text()
  network_policy = (REPO_ROOT / "kubernetes/scenescape-chart/templates/positioning/networkpolicy.yaml").read_text()
  assignments = json.loads((REPO_ROOT / "deployment/positioning-assignments.json").read_text())
  dockerfile = (REPO_ROOT / "positioning/Dockerfile").read_text()
  certificates = (REPO_ROOT / "tools/certificates/Makefile").read_text()

  positioning_command = compose["services"]["positioning"]["command"]
  assert positioning_command[positioning_command.index("--broker") + 1] == (
    "broker.scenescape.intel.com:8883")
  assert "require_certificate true" in broker
  assert "use_identity_as_username true" in broker
  assert "acl_file /mosquitto/acl/positioning.acl" in broker
  assert '"--broker"\n            - "broker.{{ .Release.Namespace }}.svc.cluster.local:8883"' in deployment
  assert "replicas: 1" in deployment
  assert "type: Recreate" in deployment
  assert "readOnly: true" in deployment
  assert "policyTypes:" in network_policy
  assert "cameraCIDRs" in network_policy
  assert set(assignments) == {"$comment"}
  assert "tools/positioning/render_mosquitto_acl.py" in dockerfile
  assert "chmod 0600 $(CASECRETSDIR)/ca/scenescape-ca.key" in certificates
