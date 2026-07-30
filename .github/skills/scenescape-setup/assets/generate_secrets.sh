#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Generates all secrets required by a SceneScape deployment.
# Usage: bash generate_secrets.sh [SUPASS]
#
# If SUPASS is not supplied, a random one is generated and written to supass in this directory.
# Run this script from <deploy_dir>/secrets/.

set -euo pipefail

EXEC_PATH="$(cd "$(dirname "$0")" && pwd)"
SECRETSDIR="$EXEC_PATH"
CERTDOMAIN="scenescape.intel.com"
CERTPASS=$(openssl rand -base64 33)
DBPASS=$(openssl rand -base64 12)
SUPASS="${1:-$(openssl rand -base64 16)}"
MQTTUSERS="controller.auth=scenectrl browser.auth=webuser calibration.auth=calibration"

OWNER_UID="$(stat -c '%u' "$EXEC_PATH")"
OWNER_GID="$(stat -c '%g' "$EXEC_PATH")"

mkdir -p "$SECRETSDIR/ca" "$SECRETSDIR/certs"

# ── Root CA ───────────────────────────────────────────────────────────────────
echo "Generating root CA key..."
openssl ecparam -name secp384r1 -genkey \
  | openssl ec -aes256 -passout pass:"$CERTPASS" \
    -out "$SECRETSDIR/ca/scenescape-ca.key"
chmod 0644 "$SECRETSDIR/ca/scenescape-ca.key"

echo "Generating root CA certificate..."
openssl req -passin pass:"$CERTPASS" -x509 -new \
  -key "$SECRETSDIR/ca/scenescape-ca.key" -days 1825 \
  -out "$SECRETSDIR/certs/scenescape-ca.pem" \
  -subj "/CN=ca.$CERTDOMAIN"
chmod 0644 "$SECRETSDIR/certs/scenescape-ca.pem"

# ── Helper: issue a service certificate using openssl.cnf template ────────────
# HOST is used for CN/SAN (e.g. reid → reid.scenescape.intel.com). Optional
# FILEHOST overrides the on-disk basename (e.g. reid-s → scenescape-reid-s.crt)
# while keeping the same CN/SAN — matches tools/certificates reid / reid-s.
issue_cert() {
  local HOST="$1" USAGE="$2" FILEHOST="${3:-$1}"
  local KEYFILE="$SECRETSDIR/certs/scenescape-${FILEHOST}.key"
  local CSRFILE="$SECRETSDIR/certs/scenescape-${FILEHOST}.csr"
  local CRTFILE="$SECRETSDIR/certs/scenescape-${FILEHOST}.crt"
  local SAN="DNS.1=${HOST}.${CERTDOMAIN}"
  local CN="${HOST}.${CERTDOMAIN}"

  echo "Generating ${FILEHOST}.key..."
  openssl ecparam -name secp384r1 -genkey -noout -out "$KEYFILE"
  chmod 0644 "$KEYFILE"

  openssl req -new -out "$CSRFILE" -key "$KEYFILE" \
    -config <(sed -e "s/##CN##/$CN/" -e "s/##SAN##/$SAN/" \
              -e "s/##KEYUSAGE##/$USAGE/" "$EXEC_PATH/openssl.cnf")

  echo "Generating certificate for $CN (file: ${FILEHOST})..."
  openssl x509 -passin pass:"$CERTPASS" -req \
    -in "$CSRFILE" \
    -CA "$SECRETSDIR/certs/scenescape-ca.pem" \
    -CAkey "$SECRETSDIR/ca/scenescape-ca.key" \
    -CAcreateserial \
    -out "$CRTFILE" -days 360 \
    -extensions x509_ext \
    -extfile <(sed -e "s/##SAN##/$SAN/" -e "s/##KEYUSAGE##/$USAGE/" "$EXEC_PATH/openssl.cnf")
  chmod 0644 "$CRTFILE"
}

issue_cert broker          serverAuth
issue_cert web             serverAuth
issue_cert reid            clientAuth
issue_cert reid            serverAuth reid-s
issue_cert autocalibration serverAuth
issue_cert mapping         serverAuth

# ── MQTT auth files ───────────────────────────────────────────────────────────
echo "Generating auth files..."
for uid in $MQTTUSERS; do
  JSONFILE="${uid%=*}"
  USERPASS="${uid##*=}"
  case "$USERPASS" in
    *:* ) ;;
    * ) USERPASS="$USERPASS:$(openssl rand -base64 12)" ;;
  esac
  USER="${USERPASS%:*}"
  PASS="${USERPASS##*:}"
  echo '{"user": "'"$USER"'", "password": "'"$PASS"'"}' > "$SECRETSDIR/$JSONFILE"
  chmod 0644 "$SECRETSDIR/$JSONFILE"
done

# ── Django secrets ────────────────────────────────────────────────────────────
echo "Generating Django secrets..."
mkdir -p "$SECRETSDIR/django"
SECRET_KEY=$(python3 -c \
  'import secrets; chars="abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)"; \
   print("".join(secrets.choice(chars) for _ in range(50)))')
{
  echo "SECRET_KEY='${SECRET_KEY}'"
  echo "DATABASE_PASSWORD='${DBPASS}'"
} > "$SECRETSDIR/django/secrets.py"

# ── Postgres password ─────────────────────────────────────────────────────────
mkdir -p "$SECRETSDIR/pgserver"
printf 'POSTGRES_PASSWORD="%s"\n' "$DBPASS" > "$SECRETSDIR/pgserver/pgserver.env"

# ── Superuser password ────────────────────────────────────────────────────────
echo -n "$SUPASS" > "$SECRETSDIR/supass"
chmod 0644 "$SECRETSDIR/supass"

# Keep generated secrets owned by the deployment directory owner. This prevents
# root-owned files when the script is run with sudo and keeps the tree easy to delete.
chown -R "$OWNER_UID:$OWNER_GID" "$SECRETSDIR"
find "$SECRETSDIR" -type d -exec chmod 0755 {} +
find "$SECRETSDIR" -type f -exec chmod 0644 {} +

echo ""
echo "Secrets written to: $SECRETSDIR"
echo "Superuser password: $SUPASS"
echo "(also saved to $SECRETSDIR/supass)"

