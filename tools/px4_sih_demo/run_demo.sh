#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# End-to-end PX4 SIH → MAVLink adapter → SceneScape geospatial scene demo.
#
# Prerequisites:
#   - SceneScape running (make demo with MAPBOX_API_KEY and SUPASS set)
#   - setup_geospatial_drone_scene.py already run (px4_sih_config.json present)
#   - pip install -r tools/external_source_adapters/requirements.txt
#   - Docker (for px4io/px4-sitl-sih)
#
# Usage:
#   export MAPBOX_API_KEY=pk....
#   export SUPASS=...
#   ./tools/px4_sih_demo/run_demo.sh setup     # create scene + ROI once
#   ./tools/px4_sih_demo/run_demo.sh start     # SIH + MAVLink adapter + mission
#   ./tools/px4_sih_demo/run_demo.sh stop

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CONFIG="${SCRIPT_DIR}/px4_sih_config.json"
VENV="${SCRIPT_DIR}/.venv"
PX4_IMAGE="${PX4_SITL_IMAGE:-px4io/px4-sitl-sih:latest}"
PX4_CONTAINER="${PX4_SITL_CONTAINER:-px4-sih-demo}"
PX4_HOST_MAVLINK_PORT="${PX4_HOST_MAVLINK_PORT:-14550}"
PX4_HOST_OFFBOARD_PORT="${PX4_HOST_OFFBOARD_PORT:-14540}"

ensure_venv() {
  if [[ ! -x "${VENV}/bin/python3" ]]; then
    python3 -m venv "${VENV}"
  fi
  "${VENV}/bin/pip" install -q \
    -r "${REPO_ROOT}/tools/external_source_adapters/requirements.txt" \
    requests
}

python_demo() {
  ensure_venv
  PYTHONPATH="${REPO_ROOT}/scene_common/src:${PYTHONPATH:-}" \
    "${VENV}/bin/python3" "$@"
}

die() { echo "ERROR: $*" >&2; exit 1; }

require_config() {
  [[ -f "${CONFIG}" ]] || die "Missing ${CONFIG}. Run: $0 setup"
}

read_config_field() {
  python_demo -c "import json; print(json.load(open('${CONFIG}'))['$1'])"
}

resolve_broker_host() {
  # TLS cert is issued for broker.scenescape.intel.com — never use the container IP
  # from the host (hostname verification fails silently and publishes are dropped).
  export SCENESCAPE_BROKER="${SCENESCAPE_BROKER:-broker.scenescape.intel.com}"
}

PX4_DEMO_COMPOSE=( -f docker-compose.yml -f tools/px4_sih_demo/docker-compose.broker-port.yml )

ensure_host_demo_compose() {
  echo "Applying host-side demo compose overrides (MQTT port + scene timestamp tolerance) …"
  (cd "${REPO_ROOT}" && docker compose "${PX4_DEMO_COMPOSE[@]}" up -d broker scene)
  sleep 3
}

ensure_mqtt_from_host() {
  resolve_broker_host
  if ! timeout 1 bash -c 'echo > /dev/tcp/127.0.0.1/1883' 2>/dev/null; then
    echo "MQTT broker port 1883 is not reachable on localhost."
    ensure_host_demo_compose
  elif ! docker inspect scenescape-scene-1 --format '{{json .Config.Cmd}}' 2>/dev/null \
      | grep -q rewriteBadTime; then
    echo "Scene controller is not configured for host-side adapters (missing --rewriteBadTime)."
    ensure_host_demo_compose
  fi
  if ! timeout 2 bash -c 'echo > /dev/tcp/127.0.0.1/1883' 2>/dev/null; then
    die "MQTT broker still unreachable on localhost:1883 after compose update"
  fi
  if ! getent hosts broker.scenescape.intel.com 2>/dev/null | grep -qE '127\.0\.0\.1|::1'; then
    echo "Note: broker.scenescape.intel.com is not in /etc/hosts; using 127.0.0.1 with TLS verify disabled."
    export SCENESCAPE_BROKER="127.0.0.1"
    export SCENESCAPE_MQTT_INSECURE=1
  fi
}

cmd_setup() {
  : "${MAPBOX_API_KEY:?Set MAPBOX_API_KEY}"
  : "${SUPASS:?Set SUPASS (Scenescape admin password)}"
  python_demo "${SCRIPT_DIR}/setup_geospatial_drone_scene.py" "$@"
}

cmd_start_px4() {
  require_config
  local home_lat home_lon home_alt
  home_lat="$(read_config_field px4_home_lat)"
  home_lon="$(read_config_field px4_home_lon)"
  home_alt="$(read_config_field px4_home_alt_m)"

  docker rm -f "${PX4_CONTAINER}" 2>/dev/null || true
  echo "Starting PX4 SIH (${PX4_IMAGE}) at home ${home_lat}, ${home_lon}, alt ${home_alt} m …"
  # Host networking lets pymavlink bind 14550/14540 on the host (port-publish would
  # occupy the UDP port and block the adapter).
  docker run -d --name "${PX4_CONTAINER}" --network host \
    -e "PX4_HOME_LAT=${home_lat}" \
    -e "PX4_HOME_LON=${home_lon}" \
    -e "PX4_HOME_ALT=${home_alt}" \
    -e "PX4_SIM_MODEL=sihsim_quadx" \
    "${PX4_IMAGE}"
  echo "Waiting for MAVLink heartbeat on UDP ${PX4_HOST_MAVLINK_PORT} …"
  python_demo - <<PY
import time
from pymavlink import mavutil
port = ${PX4_HOST_MAVLINK_PORT}
for _ in range(60):
    try:
        m = mavutil.mavlink_connection(f"udpin:0.0.0.0:{port}")
        if m.wait_heartbeat(timeout=2):
            msg = m.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=5)
            if msg:
                print('PX4 SIH ready; GPS', msg.lat/1e7, msg.lon/1e7)
            else:
                print('PX4 SIH ready (awaiting GPS fix).')
            raise SystemExit(0)
    except SystemExit:
        raise
    except Exception:
        pass
    time.sleep(2)
raise SystemExit("PX4 SIH did not respond — check: docker logs ${PX4_CONTAINER}")
PY
}

cmd_start_adapter() {
  require_config
  if pgrep -f "mavlink_to_external_source.py" >/dev/null 2>&1; then
    echo "Stopping existing MAVLink adapter instance(s) …"
    pkill -f "mavlink_to_external_source.py" 2>/dev/null || true
    sleep 0.5
  fi
  ensure_mqtt_from_host
  export SCENESCAPE_MQTT_AUTH="${SCENESCAPE_MQTT_AUTH:-${REPO_ROOT}/manager/secrets/controller.auth}"
  export SCENESCAPE_SOURCE_ID="$(read_config_field source_id)"
  export SCENESCAPE_SCENE_ID="$(read_config_field scene_uid)"
  export SCENESCAPE_THING_TYPE="$(read_config_field thing_type)"
  export SCENESCAPE_ROOT_CERT="${REPO_ROOT}/manager/secrets/certs/scenescape-ca.pem"
  export SCENESCAPE_BROKER_PORT="${SCENESCAPE_BROKER_PORT:-1883}"
  export MAVLINK_CONNECTION="${MAVLINK_CONNECTION:-udpin:0.0.0.0:${PX4_HOST_MAVLINK_PORT}}"

  echo "Starting MAVLink → SceneScape adapter (source_id=${SCENESCAPE_SOURCE_ID}) …"
  echo "  Note: adapter publishes telemetry only — run '$0 fly' to move the drone."
  echo "  MQTT broker: ${SCENESCAPE_BROKER}:${SCENESCAPE_BROKER_PORT}"
  echo "  MQTT auth:   ${SCENESCAPE_MQTT_AUTH}"
  echo "  MAVLink:     ${MAVLINK_CONNECTION}"
  python_demo "${REPO_ROOT}/tools/external_source_adapters/mavlink_to_external_source.py"
}

cmd_fly() {
  require_config
  pkill -f "fly_roi_pattern.py" 2>/dev/null || true
  sleep 0.5
  python_demo "${SCRIPT_DIR}/fly_roi_pattern.py" \
    --config "${CONFIG}" \
    --connection "udp:127.0.0.1:${PX4_HOST_OFFBOARD_PORT}" \
    "$@"
}

cmd_stop_fly() {
  require_config
  pkill -f "fly_roi_pattern.py" 2>/dev/null || true
  python_demo "${SCRIPT_DIR}/fly_roi_pattern.py" \
    --config "${CONFIG}" \
    --connection "udp:127.0.0.1:${PX4_HOST_OFFBOARD_PORT}" \
    --stop
}

cmd_watch_roi() {
  require_config
  local scene_uid roi_uid
  scene_uid="$(read_config_field scene_uid)"
  roi_uid="$(read_config_field roi_uid)"
  local ca="${REPO_ROOT}/manager/secrets/certs/scenescape-ca.pem"
  local auth
  auth="$(cat "${REPO_ROOT}/manager/secrets/controller.auth")"
  local user pass
  user="${auth%%:*}"
  pass="${auth#*:}"
  echo "Subscribing to ROI count events for scene ${scene_uid} region ${roi_uid} …"
  docker run --rm --network host \
    -v "${ca}:/ca.pem:ro" \
    eclipse-mosquitto:2.0.22 \
    mosquitto_sub -h localhost -p 1883 \
    --cafile /ca.pem --insecure \
    -u "${user}" -P "${pass}" \
    -t "scenescape/event/region/${scene_uid}/${roi_uid}/count" -v
}

cmd_stop() {
  docker rm -f "${PX4_CONTAINER}" 2>/dev/null || true
  pkill -f "mavlink_to_external_source.py" 2>/dev/null || true
  echo "Stopped PX4 SIH container and MAVLink adapter (if running)."
}

cmd_start() {
  ensure_venv
  cmd_start_px4
  echo ""
  echo "Open a second terminal and run the MAVLink adapter:"
  echo "  ${SCRIPT_DIR}/run_demo.sh adapter"
  echo ""
  echo "Open a third terminal, fly the mission through the ROI:"
  echo "  ${SCRIPT_DIR}/run_demo.sh fly"
  echo ""
  echo "Watch ROI MQTT events:"
  echo "  ${SCRIPT_DIR}/run_demo.sh watch-roi"
  echo ""
  echo "Scene UI: https://localhost/ (scene name in px4_sih_config.json)"
}

usage() {
  cat <<EOF
Usage: $(basename "$0") <command>

Commands:
  setup       Create geospatial scene + ROI (needs MAPBOX_API_KEY, SUPASS)
  start       Start PX4 SIH Docker container and print next steps
  adapter     Run MAVLink → SceneScape MQTT adapter (foreground)
  fly         Ping-pong across ROI edge for enter/exit analytics (Ctrl+C to stop)
  stop-fly    Exit auto mission and hold position (keeps PX4 SIH running)
  watch-roi   Subscribe to ROI count MQTT events
  stop        Stop PX4 container and adapter

Environment:
  MAPBOX_API_KEY          Required for setup
  SUPASS                  Scenescape admin password
  PX4_DEMO_LOCATION       Geocode query (default: Shoreline Amphitheatre, MV)
  SCENESCAPE_MQTT_AUTH    Defaults to manager/secrets/controller.auth
EOF
}

main() {
  local cmd="${1:-}"
  shift || true
  case "${cmd}" in
    setup) cmd_setup "$@" ;;
    start) cmd_start "$@" ;;
    adapter) cmd_start_adapter "$@" ;;
    fly) cmd_fly "$@" ;;
    stop-fly) cmd_stop_fly "$@" ;;
    watch-roi) cmd_watch_roi "$@" ;;
    stop) cmd_stop "$@" ;;
    -h|--help|help|"") usage ;;
    *) die "Unknown command: ${cmd}. Try: $0 help" ;;
  esac
}

main "$@"
