# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Certificate inspection and renewal without rotating application secrets."""

from datetime import datetime, timezone
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile

try:
  from .backup import compose_base
except ImportError:
  from backup import compose_base


CERTIFICATE_FILES = (
  "scenescape-ca.pem",
  "scenescape-broker.crt",
  "scenescape-web.crt",
  "scenescape-reid.crt",
  "scenescape-reid-s.crt",
  "scenescape-autocalibration.crt",
  "scenescape-mapping.crt",
)

PRIVATE_KEY_FILES = (
  "scenescape-broker.key",
  "scenescape-web.key",
  "scenescape-reid.key",
  "scenescape-reid-s.key",
  "scenescape-autocalibration.key",
  "scenescape-mapping.key",
)


def certificate_status(secrets_dir, minimum_valid_days=30, runner=subprocess.run):
  """Report whether every required certificate remains valid for the threshold."""
  if minimum_valid_days < 0:
    raise ValueError("minimum valid days cannot be negative")
  certs_dir = Path(secrets_dir) / "certs"
  seconds = minimum_valid_days * 24 * 60 * 60
  certificates = []
  for filename in CERTIFICATE_FILES:
    path = certs_dir / filename
    if not path.is_file():
      certificates.append({"name": filename, "status": "missing"})
      continue
    result = runner(["openssl", "x509", "-checkend", str(seconds), "-noout",
                     "-in", str(path)], check=False, capture_output=True, text=True)
    certificates.append({
      "name": filename,
      "status": "valid" if result.returncode == 0 else "renewal_required",
    })
  for filename in PRIVATE_KEY_FILES:
    path = certs_dir / filename
    certificates.append({
      "name": filename,
      "status": "valid" if path.is_file() else "missing",
    })
  ca_key = Path(secrets_dir) / "ca" / "scenescape-ca.key"
  certificates.append({
    "name": "ca/scenescape-ca.key",
    "status": "valid" if ca_key.is_file() else "missing",
  })
  status = "ready" if all(item["status"] == "valid" for item in certificates) \
    else "action_required"
  return {"status": status, "minimum_valid_days": minimum_valid_days,
          "certificates": certificates}


def generate_certificates(repository_root, destination, certdomain, extra_hosts,
                          runner=subprocess.run):
  """Generate a complete TLS trust set in an isolated directory."""
  environment = os.environ.copy()
  environment.update({
    "SECRETSDIR": str(destination),
    "CASECRETSDIR": str(destination),
    "CERTDOMAIN": certdomain,
    "CERTPASS": secrets.token_urlsafe(24),
    "BROKER_EXTRA_HOSTS": extra_hosts.get("broker", ""),
    "WEB_EXTRA_HOSTS": extra_hosts.get("web", ""),
    "REID_S_EXTRA_HOSTS": extra_hosts.get("reid_s", ""),
  })
  runner(["make", "-C", str(Path(repository_root) / "tools" / "certificates"),
          "deploy-certificates"], check=True, env=environment)


def validate_trust_set(secrets_dir, runner=subprocess.run):
  """Verify required files and every leaf certificate against the staged CA."""
  certs_dir = Path(secrets_dir) / "certs"
  ca_file = certs_dir / "scenescape-ca.pem"
  missing = [name for name in CERTIFICATE_FILES
             if not (certs_dir / name).is_file()]
  missing.extend(name for name in PRIVATE_KEY_FILES
                 if not (certs_dir / name).is_file())
  if not (Path(secrets_dir) / "ca" / "scenescape-ca.key").is_file():
    missing.append("ca/scenescape-ca.key")
  if missing:
    raise ValueError(f"generated certificate set is incomplete: {', '.join(missing)}")
  for filename in CERTIFICATE_FILES[1:]:
    runner(["openssl", "verify", "-CAfile", str(ca_file),
            str(certs_dir / filename)], check=True, capture_output=True, text=True)


def replace_trust_set(secrets_dir, staged_dir, backup_dir):
  """Replace only TLS directories, retaining rollback copies."""
  secrets_dir = Path(secrets_dir)
  staged_dir = Path(staged_dir)
  backup_dir = Path(backup_dir)
  backup_dir.mkdir(parents=True, mode=0o700)
  backup_dir.chmod(0o700)
  names = ("certs", "ca")
  for name in names:
    current = secrets_dir / name
    if current.exists():
      shutil.copytree(current, backup_dir / name)
  installed = []
  try:
    for name in names:
      current = secrets_dir / name
      replacement = staged_dir / name
      rollback = secrets_dir / f".{name}.renewal-rollback"
      if rollback.exists():
        shutil.rmtree(rollback)
      if current.exists():
        current.rename(rollback)
      replacement.rename(current)
      installed.append(name)
  except Exception:
    for name in reversed(names):
      current = secrets_dir / name
      rollback = secrets_dir / f".{name}.renewal-rollback"
      if name in installed and current.exists():
        shutil.rmtree(current)
      if rollback.exists():
        rollback.rename(current)
    raise
  for name in names:
    rollback = secrets_dir / f".{name}.renewal-rollback"
    if rollback.exists():
      shutil.rmtree(rollback)


def renew_certificates(repository_root, secrets_dir, compose_files, profiles,
                       project_name, output_parent, certdomain, extra_hosts,
                       runner=subprocess.run):
  """Stage, validate, install, and activate a complete TLS trust set."""
  operation_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
  backup_dir = Path(output_parent).resolve() / f"certificates-{operation_id}"
  secrets_dir = Path(secrets_dir).resolve()
  secrets_dir.parent.mkdir(parents=True, exist_ok=True)
  with tempfile.TemporaryDirectory(prefix=".certificate-renewal-",
                                   dir=secrets_dir.parent) as temporary:
    staged_dir = Path(temporary) / "secrets"
    generate_certificates(repository_root, staged_dir, certdomain, extra_hosts,
                          runner=runner)
    validate_trust_set(staged_dir, runner=runner)
    replace_trust_set(secrets_dir, staged_dir, backup_dir)
  compose = compose_base(compose_files, profiles, project_name)
  runner(compose + ["up", "-d", "--force-recreate"], check=True)
  return backup_dir
