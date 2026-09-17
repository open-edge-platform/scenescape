# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for read-only Kubernetes upgrade guardrails. NEX-T20005"""

import json
from subprocess import CompletedProcess

import pytest

from tools.upgrade.kubernetes import kubernetes_report
from tools.upgrade.kubernetes import require_compose


def test_report_identifies_ephemeral_storage_and_never_mutates():
  commands = []

  def runner(command, **_kwargs):
    commands.append(command)
    if command[:2] == ["helm", "list"]:
      payload = [{"name": "scenescape", "namespace": "custom", "revision": "3",
                  "status": "deployed", "chart": "scenescape-2026.2.0",
                  "app_version": "2026.2.0"}]
    elif command[2] == "deployment":
      payload = {"items": [{"metadata": {"name": "scenescape-reid"},
                            "spec": {"template": {"spec": {"volumes": [
                              {"name": "reid-data", "emptyDir": {}}]}}}}]}
    elif command[2] == "certificate":
      payload = {"items": [{"metadata": {"name": "web"}, "status": {
        "conditions": [{"type": "Ready", "status": "True"}]}}]}
    else:
      payload = {"items": []}
    return CompletedProcess(command, 0, stdout=json.dumps(payload))

  report = kubernetes_report("scenescape", "custom", runner=runner)

  assert report["status"] == "action_required"
  assert report["warnings"][0]["code"] == "ephemeral_storage"
  assert report["unsupported_operations"] == ["backup", "restore", "apply", "rollback"]
  assert all(command[0:2] in (["helm", "list"], ["kubectl", "get"])
             for command in commands)


def test_report_warns_when_certificate_is_not_ready():
  def runner(command, **_kwargs):
    if command[:2] == ["helm", "list"]:
      payload = [{"name": "scenescape", "namespace": "scenescape"}]
    elif command[2] == "certificate":
      payload = {"items": [{"metadata": {"name": "web"}, "status": {
        "conditions": [{"type": "Ready", "status": "False"}]}}]}
    else:
      payload = {"items": []}
    return CompletedProcess(command, 0, stdout=json.dumps(payload))

  report = kubernetes_report("scenescape", "scenescape", runner=runner)

  assert report["warnings"] == [{
    "code": "certificate_not_ready",
    "message": "one or more cert-manager Certificates are not Ready",
  }]


def test_compose_operations_reject_kubernetes_deployments():
  with pytest.raises(ValueError, match="kubernetes-report"):
    require_compose("kubernetes")

  assert require_compose("compose") is None
