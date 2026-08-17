#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Wait for a deploy_scenescape.sh run to finish, then print a stable completion
# banner for agent notify_on_output watchers.
#
# Usage:
#   watch_orchestrator.sh --deploy-dir DIR --pid ORCH_PID [--interval-s N]
#
# Always prints (in order):
#   ORCHESTRATOR_FINISHED
#   <tail of orchestrator.log>
#   RESULT=SUCCESS | RESULT=FAILURE
#
# Exit 0 on SUCCESS, 1 on FAILURE.

set -euo pipefail

DEPLOY_DIR=""
ORCH_PID=""
INTERVAL_S=5

usage() {
  cat <<'EOF'
Usage: watch_orchestrator.sh --deploy-dir DIR --pid ORCH_PID [--interval-s N]
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --deploy-dir)
      DEPLOY_DIR="${2:?}"
      shift 2
      ;;
    --pid)
      ORCH_PID="${2:?}"
      shift 2
      ;;
    --interval-s)
      INTERVAL_S="${2:?}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$DEPLOY_DIR" || -z "$ORCH_PID" ]]; then
  usage >&2
  exit 2
fi

LOG_FILE="${DEPLOY_DIR}/orchestrator.log"
STATE_FILE="${DEPLOY_DIR}/.deploy-state.json"

# Wait until the orchestrator PID exits. Do not match on pgrep for the script
# name — that can accidentally include this watcher or the launching shell.
while kill -0 "$ORCH_PID" 2>/dev/null; do
  sleep "$INTERVAL_S"
done

# Brief settle so the final log lines are flushed.
sleep 1

echo "ORCHESTRATOR_FINISHED"
echo "===== orchestrator.log ====="
if [[ -f "$LOG_FILE" ]]; then
  cat "$LOG_FILE"
else
  echo "(missing $LOG_FILE)"
fi

if [[ -f "$STATE_FILE" ]]; then
  echo "===== .deploy-state.json ====="
  cat "$STATE_FILE"
fi

# SUCCESS when DEPLOY COMPLETE appears and no FAIL line is after it (WARN is OK).
success=0
if [[ -f "$LOG_FILE" ]] && awk '
  /DEPLOY COMPLETE/ { complete = NR }
  /FAIL/ { fail = NR }
  END { exit (complete && (!fail || fail < complete)) ? 0 : 1 }
' "$LOG_FILE"; then
  success=1
fi

if [[ "$success" -eq 1 ]]; then
  echo "RESULT=SUCCESS"
  exit 0
fi

echo "RESULT=FAILURE"
exit 1
