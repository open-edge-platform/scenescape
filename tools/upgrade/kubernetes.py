# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Read-only Kubernetes upgrade discovery and guardrails."""

import json
import subprocess


def require_compose(deployment_type):
  """Reject Compose-specific operations for Kubernetes deployments."""
  if deployment_type != "compose":
    raise ValueError(
      "Compose operations are unsupported for Kubernetes; run kubernetes-report")


def json_command(command, runner=subprocess.run):
  """Run a read-only command and parse its JSON output."""
  result = runner(command, check=True, capture_output=True, text=True)
  return json.loads(result.stdout)


def helm_release(release, namespace, runner=subprocess.run):
  """Read Helm release metadata and user-supplied values."""
  releases = json_command(
    ["helm", "list", "--namespace", namespace, "--filter", f"^{release}$",
     "--output", "json"], runner=runner)
  if len(releases) != 1 or releases[0].get("name") != release:
    raise ValueError(f"Helm release {release} was not found in namespace {namespace}")
  item = releases[0]
  return {
    "name": item.get("name"),
    "namespace": item.get("namespace", namespace),
    "revision": item.get("revision"),
    "status": item.get("status"),
    "chart": item.get("chart"),
    "app_version": item.get("app_version"),
  }


def named_resources(items):
  """Summarize resource identity and status without secret data."""
  resources = []
  for item in items:
    metadata = item.get("metadata", {})
    status = item.get("status", {})
    resources.append({
      "name": metadata.get("name"),
      "phase": status.get("phase"),
      "ready": next((condition.get("status") == "True"
                     for condition in status.get("conditions", [])
                     if condition.get("type") == "Ready"), None),
    })
  return resources


def ephemeral_volumes(deployments):
  """Report workload emptyDir volumes that cannot survive pod replacement."""
  ephemeral = []
  for deployment in deployments:
    name = deployment.get("metadata", {}).get("name")
    volumes = deployment.get("spec", {}).get("template", {}).get("spec", {}).get(
      "volumes", [])
    for volume in volumes:
      if "emptyDir" in volume:
        ephemeral.append({"workload": name, "volume": volume.get("name")})
  return ephemeral


def kubernetes_report(release, namespace, runner=subprocess.run):
  """Build a stable read-only report for operator-led Kubernetes upgrades."""
  helm = helm_release(release, namespace, runner=runner)
  selector = f"meta.helm.sh/release-name={release}"
  pvc = json_command(
    ["kubectl", "get", "pvc", "-n", namespace, "-l", selector, "-o", "json"],
    runner=runner)
  statefulsets = json_command(
    ["kubectl", "get", "statefulset", "-n", namespace, "-l", selector,
     "-o", "json"], runner=runner)
  deployments = json_command(
    ["kubectl", "get", "deployment", "-n", namespace, "-l", selector,
     "-o", "json"], runner=runner)
  certificates = json_command(
    ["kubectl", "get", "certificate", "-n", namespace, "-l", selector,
     "-o", "json"], runner=runner)
  ephemeral = ephemeral_volumes(deployments.get("items", []))
  warnings = []
  if ephemeral:
    warnings.append({
      "code": "ephemeral_storage",
      "message": "emptyDir data will not survive pod replacement",
      "volumes": ephemeral,
    })
  if any(item["ready"] is not True
         for item in named_resources(certificates.get("items", []))):
    warnings.append({
      "code": "certificate_not_ready",
      "message": "one or more cert-manager Certificates are not Ready",
    })
  return {
    "schema_version": 1,
    "operation": "kubernetes_upgrade_report",
    "status": "action_required",
    "deployment": {"type": "kubernetes", "helm": helm},
    "persistent_volume_claims": named_resources(pvc.get("items", [])),
    "statefulsets": named_resources(statefulsets.get("items", [])),
    "certificates": named_resources(certificates.get("items", [])),
    "warnings": warnings,
    "supported_operations": ["report"],
    "unsupported_operations": ["backup", "restore", "apply", "rollback"],
  }