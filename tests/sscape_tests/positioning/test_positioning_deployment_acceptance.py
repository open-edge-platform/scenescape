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


def test_positioning_acl_principal_is_the_configured_certificate_identity(tmp_path):
  """A custom CERTDOMAIN issues positioning.<CERTDOMAIN>; the ACL must name that CN."""
  assert render_acl({}, "resolver-a", "positioning.example.org").splitlines()[0] == (
    "user positioning.example.org")

  output = tmp_path / "positioning.acl"
  subprocess.run(
    [sys.executable, str(REPO_ROOT / "tools/positioning/render_mosquitto_acl.py"),
     "--assignments", str(REPO_ROOT / "deployment/positioning-assignments.json"),
     "--resolver-id", "positioning-default", "--identity", "positioning.example.org",
     "--output", str(output)],
    check=True)
  assert output.read_text().splitlines()[0] == "user positioning.example.org"


@pytest.mark.parametrize("bad_identity", (
  "", "positioning example.org", "positioning.example.org\ntopic readwrite #",
  "positioning+", "positioning#", "positioning/example", "a" * 254, None))
def test_positioning_acl_rejects_unsafe_certificate_identity(bad_identity):
  with pytest.raises(ValueError):
    render_acl({}, "resolver-a", bad_identity)


def test_compose_acl_identity_follows_the_certificate_domain():
  compose = yaml.safe_load(
    (REPO_ROOT / "sample_data/compose/compose.dl-streamer-example.yml").read_text())
  entrypoint = compose["services"]["positioning-acl-init"]["entrypoint"]
  assert entrypoint[entrypoint.index("--identity") + 1] == (
    "${POSITIONING_CERT_IDENTITY:-positioning.scenescape.intel.com}")

  env_target = subprocess.run(
    ["make", "--no-print-directory", "-s", "-n", "-C", str(REPO_ROOT), ".env",
     "CERTDOMAIN=example.org", "SECRETSDIR=/nonexistent"],
    capture_output=True, text=True, check=True).stdout
  assert '"POSITIONING_CERT_IDENTITY=positioning.example.org"' in env_target
  certificates = (REPO_ROOT / "tools/certificates/Makefile").read_text()
  assert "positioning-cert: HOST=positioning\n" in certificates
  assert 's/##CN##/$(HOST)$(HOSTSUFFIX).$(CERTDOMAIN)/' in certificates


def test_helm_certificate_and_acl_share_one_identity():
  templates = REPO_ROOT / "kubernetes/scenescape-chart/templates/positioning"
  certificate = (templates / "certificate.yaml").read_text()
  helpers = (templates / "_helpers.tpl").read_text()
  assert 'commonName: {{ include "positioning.certIdentity" . | quote }}' in certificate
  assert '(printf "user %s" (include "positioning.certIdentity" .))' in helpers
  assert "positioning.scenescape.intel.com" not in certificate


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


MOSQUITTO_DIR = REPO_ROOT / "dlstreamer-pipeline-server/mosquitto"
SHARED_BROKER_CONFIG = "mosquitto-secure.conf"
POSITIONING_BROKER_CONFIG = "mosquitto-secure-positioning.conf"


def _broker_config_consumers():
  """Yield (compose file, service, config file name) for every Mosquitto config mount.

  Config sources resolve within the same Compose file first, then within sibling files
  of the same directory (the hierarchy stacks define configs in compose.common.yml).
  """
  tracked = subprocess.run(["git", "ls-files", "*compose*.yml", "*compose*.yaml"],
                           cwd=REPO_ROOT, capture_output=True, text=True, check=True)
  documents = {}
  for name in tracked.stdout.split():
    document = yaml.safe_load((REPO_ROOT / name).read_text())
    if isinstance(document, dict):
      documents[Path(name)] = document

  def config_file(path, source):
    candidates = [path] + sorted(p for p in documents if p.parent == path.parent and p != path)
    for candidate in candidates:
      definition = (documents[candidate].get("configs") or {}).get(source)
      if isinstance(definition, dict) and "file" in definition:
        return Path(definition["file"]).name
    return None

  for path, document in documents.items():
    for service_name, service in (document.get("services") or {}).items():
      for config in (service or {}).get("configs") or []:
        source = config["source"] if isinstance(config, dict) else config
        file_name = config_file(path, source)
        if file_name in (SHARED_BROKER_CONFIG, POSITIONING_BROKER_CONFIG):
          yield path, service_name, service, file_name


def _listener_blocks(text):
  """Listener 1883/1884 settings, normalizing the global vs per-listener anonymous flag."""
  blocks, current, anonymous = {}, None, None
  for line in text.splitlines():
    line = line.split("#", 1)[0].strip()
    if not line:
      continue
    key, _, value = line.partition(" ")
    if key == "allow_anonymous" and current is None:
      anonymous = value
    elif key == "listener":
      current = value
      blocks[current] = {"listener_allow_anonymous": anonymous} if anonymous else {}
    elif current is not None:
      blocks[current][key] = value
  return {port: settings for port, settings in blocks.items() if port in ("1883", "1884")}


def test_shared_broker_config_needs_no_positioning_acl():
  """Test, hierarchy, perf and pipeline-runner brokers mount only the secrets directory."""
  shared = (MOSQUITTO_DIR / SHARED_BROKER_CONFIG).read_text()
  assert "acl_file" not in shared
  assert "8883" not in shared
  assert "per_listener_settings" not in shared


def test_every_broker_loading_the_positioning_acl_mounts_it():
  consumers = list(_broker_config_consumers())
  assert {file_name for *_, file_name in consumers} == {
    SHARED_BROKER_CONFIG, POSITIONING_BROKER_CONFIG}
  for path, service_name, service, file_name in consumers:
    if file_name != POSITIONING_BROKER_CONFIG:
      continue
    targets = [volume.split(":")[1] if isinstance(volume, str) else volume.get("target")
               for volume in service.get("volumes") or []]
    assert "/mosquitto/acl" in targets, f"{path}:{service_name} loads the Positioning ACL"


def test_positioning_broker_config_keeps_the_shared_listeners():
  shared = _listener_blocks((MOSQUITTO_DIR / SHARED_BROKER_CONFIG).read_text())
  positioning = _listener_blocks((MOSQUITTO_DIR / POSITIONING_BROKER_CONFIG).read_text())
  assert set(shared) == {"1883", "1884"}
  assert positioning == shared


def test_positioning_production_transport_and_single_replica_gates():
  compose = yaml.safe_load(
    (REPO_ROOT / "sample_data/compose/compose.dl-streamer-example.yml").read_text())
  broker = (REPO_ROOT / "dlstreamer-pipeline-server/mosquitto/mosquitto-secure-positioning.conf").read_text()
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
