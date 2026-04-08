#!/bin/bash
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Script to generate Django migrations
# This should be run during development or as part of the release process
# DO NOT run this in production or at container startup

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

SECRETS_DIR="${PROJECT_ROOT}/manager/secrets"
RUN_SECRETS="/run/secrets/django/secrets.py"
MANAGER_DIR="/home/scenescape/SceneScape/manager"

# Where we want to copy migrations to on the host
HOST_MIGRATIONS_DIR="${PROJECT_ROOT}/manager/src/manager/migrations"

IMAGE="scenescape-manager:latest"

# Defaults for showmigrations (can be overridden via flags/env)
DB_NETWORK="${DB_NETWORK:-scenescape_scenescape}"
DB_HOST="${DB_HOST:-pgserver}"   # service/container name on the network
DB_PORT="${DB_PORT:-5432}"

SHOW_AFTER=0

usage() {
  cat <<EOF
Usage: $(basename "$0") [--show] [--dbhost NAME] [--dbport PORT] [--network NAME]

Generates Django migrations by running makemigrations in the manager image, then copies the result to:
  ${HOST_MIGRATIONS_DIR}

Options:
  --show            After generating migrations, run "python manage.py showmigrations"
                    (requires DB reachable at --dbhost on --network).
  --dbhost NAME     DB hostname/container name on docker network (default: ${DB_HOST})
  --dbport PORT     DB port (default: ${DB_PORT})
  --network NAME    Docker network where DB is reachable (default: ${DB_NETWORK})
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --show) SHOW_AFTER=1; shift ;;
    --dbhost) DB_HOST="$2"; shift 2 ;;
    --dbport) DB_PORT="$2"; shift 2 ;;
    --network) DB_NETWORK="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1"; usage; exit 1 ;;
  esac
done

echo "==> Django Migration Generator for SceneScape Manager"
echo ""

generate_migrations() {
  local container="scenescape-migrate-gen-$$"

  mkdir -p "${HOST_MIGRATIONS_DIR}"
  docker run --rm --name "${container}" \
  --user "$(id -u):$(id -g)" \
  --network "${DB_NETWORK}" \
  -e DBHOST=pgserver \
  -e DBPORT=5432 \
  -v "${SECRETS_DIR}/django:/run/secrets/django:ro" \
  -v "${PROJECT_ROOT}/manager/src/manager/migrations:/home/scenescape/SceneScape/manager/migrations:rw" \
  -v "${PROJECT_ROOT}/manager/src/manager:/home/scenescape/SceneScape/manager:rw" \
  --entrypoint /bin/bash \
  "${IMAGE}" \
  -lc '
    set -euo pipefail
    cd /home/scenescape/SceneScape
    cp /run/secrets/django/secrets.py /home/scenescape/SceneScape/manager/secrets.py
    python manage.py makemigrations manager
  '
  echo "==> Migrations can be found at ${HOST_MIGRATIONS_DIR}"
}

show_migrations() {
  echo ""
  echo "==> showmigrations (requires DB reachable)"
  echo "DB network: ${DB_NETWORK}"
  echo "DB host:    ${DB_HOST}"
  echo "DB port:    ${DB_PORT}"
  echo ""

  # Quick preflight: ensure the network exists
  if ! docker network inspect "${DB_NETWORK}" >/dev/null 2>&1; then
    echo "ERROR: Docker network '${DB_NETWORK}' not found."
    echo "Hint: start your compose stack or create the network, or pass --network <name>."
    return 2
  fi

  # Run showmigrations against DB_HOST on the network.
  # We patch settings.py HOST/PORT just for this container run.
  docker run --rm \
    --network "${DB_NETWORK}" \
    -e DBHOST=pgserver \
    -e DBPORT=5432 \
    -v "${SECRETS_DIR}/django:/run/secrets/django:ro" \
    --entrypoint /bin/bash \
    "${IMAGE}" \
    -lc "
      set -e
      cd /home/scenescape/SceneScape
      cp ${RUN_SECRETS} ${MANAGER_DIR}/secrets.py

      sed -i -E \"s|'HOST': '[^']*'|'HOST': '${DB_HOST}'|; s|'PORT': '[^']*'|'PORT': '${DB_PORT}'|\" \
        /home/scenescape/SceneScape/manager/settings.py

      python manage.py showmigrations
    "
}

generate_migrations

echo ""
echo "==> Migration files generated in manager/src/manager/migrations/"
echo ""
echo "Next steps:"
echo "1. Review the generated migration files"
echo "2. Commit migration files to version control"

if [[ "${SHOW_AFTER}" -eq 1 ]]; then
  show_migrations
else
  echo "3. (Optional) Check applied/unapplied status (requires DB):"
  echo "   $(basename "$0") --show --network ${DB_NETWORK}"
fi
echo ""
