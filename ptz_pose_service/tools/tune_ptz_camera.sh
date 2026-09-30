#!/usr/bin/env bash

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Tune a PTZ camera for the ptz-pose service in one run.
#
# Measures everything the service needs for accurate pose tracking and writes
# it into ptz_pose_service/config/cameras.json:
#
#   1. lens     - intrinsics + distortion from an AprilTag sweep
#                 (collect_calibration_views.py + calibrate_intrinsics.py)
#   2. scale    - starting pan/tilt scale from a texture sweep
#                 (capture_ptz_sweep.py + measure_ptz_scale.py)
#   3. model    - pan/tilt curves, pan axis and backlash, fitted against
#                 AprilTags over several rounds
#                 (measure_reprojection_accuracy.py + fit_ptz_curves.py)
#   4. verify   - a final accuracy measurement with the applied values
#
# Tracking of this camera is paused (track: false) while the tools drive it.
# Every round parks the camera at its start position from a known direction,
# saves a fresh auto-calibration there as the trusted home, and restarts the
# service. On failure or Ctrl-C the config is restored and the service restarted.
#
# Prerequisites:
#   - the camera exists in Scenescape, streams through the pipeline server,
#     and sees at least 6 AprilTags from its current (start) position
#   - the ptz-pose and autocalibration containers are running; if a proxy is
#     configured, the camera's IP is in the ptz-pose container's no_proxy
#   - the service code in the ptz-pose container supports track: false
#
# Usage:
#   ptz_pose_service/tools/tune_ptz_camera.sh --camera-uid atag-ptzcam4 \
#       --onvif-host 192.168.0.94 --onvif-port 2020
#
# Options:
#   --camera-uid UID          Scenescape camera UID (required)
#   --onvif-host HOST         camera ONVIF address (required)
#   --onvif-port PORT         ONVIF port (default 80)
#   --rounds N                measure+fit rounds before verifying (default 2)
#   --skip-lens               keep the configured lens values
#   --skip-scale              keep the configured scale/curves as the fit's start
#   --lens-span PAN TILT      lens sweep half-width around start (default 0.12 0.1)
#   --scale-pan-range A B     texture sweep pan range (default -0.9 0.9)
#   --scale-tilt-range A B    texture sweep tilt range (default 0.2 0.9)
#   --pan-path "OFFSETS"      accuracy measurement pan offsets (default: tool's)
#   --tilt-path "OFFSETS"     accuracy measurement tilt offsets (default: tool's)
#   --accept-poor-lens        continue even if the lens fit is poorly constrained
#   --yes                     don't ask for confirmation
#
# Environment: CONFIG (cameras.json path), POSE_CONTAINER, AUTOCAL_CONTAINER.

set -euo pipefail

TOOLS_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CONFIG=${CONFIG:-$TOOLS_DIR/../config/cameras.json}
POSE=${POSE_CONTAINER:-scenescape-ptz-pose-1}
AUTOCAL=${AUTOCAL_CONTAINER:-scenescape-autocalibration-1}
REMOTE=/tmp/ptz_tools

CAMERA="" HOST="" PORT=80 ROUNDS=2 SKIP_LENS=0 SKIP_SCALE=0 YES=0 ACCEPT_POOR_LENS=0
LENS_PAN_SPAN=0.12 LENS_TILT_SPAN=0.1
SCALE_PAN_RANGE=(-0.9 0.9) SCALE_TILT_RANGE=(0.2 0.9)
PAN_PATH=() TILT_PATH=()

usage() { sed -n '/^# Usage:/,/^# Environment/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [[ $# -gt 0 ]]; do
  case $1 in
    --camera-uid) CAMERA=$2; shift 2 ;;
    --onvif-host) HOST=$2; shift 2 ;;
    --onvif-port) PORT=$2; shift 2 ;;
    --rounds) ROUNDS=$2; shift 2 ;;
    --skip-lens) SKIP_LENS=1; shift ;;
    --skip-scale) SKIP_SCALE=1; shift ;;
    --lens-span) LENS_PAN_SPAN=$2; LENS_TILT_SPAN=$3; shift 3 ;;
    --scale-pan-range) SCALE_PAN_RANGE=("$2" "$3"); shift 3 ;;
    --scale-tilt-range) SCALE_TILT_RANGE=("$2" "$3"); shift 3 ;;
    --pan-path) read -ra PAN_PATH <<<"$2"; shift 2 ;;
    --tilt-path) read -ra TILT_PATH <<<"$2"; shift 2 ;;
    --accept-poor-lens) ACCEPT_POOR_LENS=1; shift ;;
    --yes) YES=1; shift ;;
    -h|--help) usage ;;
    *) echo "Unknown option: $1" >&2; usage 1 ;;
  esac
done
[[ -n $CAMERA && -n $HOST ]] || { echo "--camera-uid and --onvif-host are required" >&2; usage 1; }

OUT=/tmp/ptz_tune_${CAMERA}_$(date +%Y%m%d_%H%M%S)
mkdir -p "$OUT"
ONVIF=(--onvif-host "$HOST" --onvif-port "$PORT")

log() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
quiet() { { grep -vE '^(INFO|WARNING|DEBUG):|connection accepted' || true; }; }
in_pose() { docker exec -e "no_proxy=$TOOL_NO_PROXY" -e "NO_PROXY=$TOOL_NO_PROXY" "$POSE" python3 "$@" 2>&1 | quiet; }
in_autocal() { docker exec "$AUTOCAL" python3 "$@" 2>&1 | quiet; }
cfg() { python3 "$TOOLS_DIR/update_camera_config.py" "$CONFIG" --camera-uid "$CAMERA" "$@"; }
json() { python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print($2)" "$1"; }

# Moves a file or directory from the ptz-pose container to the autocalibration one.
relay() {
  local name; name=$(basename "$1")
  rm -rf "${OUT:?}/$name"
  docker cp "$POSE:$1" "$OUT/$name" >/dev/null
  docker exec -u root "$AUTOCAL" rm -rf "$1"
  docker cp "$OUT/$name" "$AUTOCAL:$1" >/dev/null
}

restart_service() {
  local since logs; since=$(date +%s)
  docker restart "$POSE" >/dev/null
  for _ in $(seq 90); do
    logs=$(docker logs --since "$since" "$POSE" 2>&1 || true)
    if grep -qF "($CAMERA):" <<<"$logs" && grep -q "Skipping camera" <<<"$logs"; then
      grep "Skipping camera" <<<"$logs" >&2
      die "the service could not track $CAMERA"
    fi
    grep -qE -- "-> $CAMERA \(|(Tracking paused for|Static camera) $CAMERA:" <<<"$logs" && {
      sleep 3
      [[ $(docker inspect -f '{{.State.Status}}' "$POSE") == running ]] \
        || die "$POSE stopped after starting; see: docker logs $POSE"
      return 0
    }
    sleep 1
  done
  die "the service didn't report $CAMERA within 90s; see: docker logs $POSE"
}

park() {
  in_pose "$REMOTE/ptz_goto.py" "${ONVIF[@]}" --pan "$START_PAN" --tilt "$START_TILT" \
      --pan-approach decreasing --tilt-approach increasing >/dev/null
}

measure_and_fit() {
  local tag=$1 paths=()
  [[ ${#PAN_PATH[@]} -gt 0 ]] && paths+=(--pan-path "${PAN_PATH[@]}")
  [[ ${#TILT_PATH[@]} -gt 0 ]] && paths+=(--tilt-path "${TILT_PATH[@]}")
  in_pose "$REMOTE/measure_reprojection_accuracy.py" --camera-uid "$CAMERA" "${ONVIF[@]}" \
      "${paths[@]}" --output "/tmp/accuracy_${CAMERA}_$tag.json"
  relay "/tmp/accuracy_${CAMERA}_$tag.json"
  fit "$tag"
  # A curve that bends implausibly outside the measured range isn't trusted:
  # refit that axis with a constant scale instead.
  local degrees=()
  for axis in pan tilt; do
    [[ $(json "$OUT/fit_$tag.json" "any(w.startswith('$axis:') for w in d['warnings'])") == True ]] \
      && degrees+=(--"$axis"-degree 1)
  done
  if [[ ${#degrees[@]} -gt 0 ]]; then
    echo "Curve rejected for: ${degrees[*]}; refitting with a constant scale"
    fit "$tag" "${degrees[@]}"
  fi
}

fit() {
  local tag=$1; shift
  in_autocal "$REMOTE/fit_ptz_curves.py" --input "/tmp/accuracy_${CAMERA}_$tag.json" \
      --fit-backlash --try-sign-flips --result-json "/tmp/fit_${CAMERA}_$tag.json" "$@" \
      | grep -E 'Dropping|correction|Pan axis|^==|service, as|current|curve |floor|WARNING'
  docker cp "$AUTOCAL:/tmp/fit_${CAMERA}_$tag.json" "$OUT/fit_$tag.json" >/dev/null
}

# Park at the start, save a fresh auto-calibration as the trusted home, and
# restart the service so it loads the current config from that home.
new_home() {
  cfg --set pan_home_approach='"decreasing"' --set tilt_home_approach='"increasing"' --unset track
  park
  in_pose "$REMOTE/save_fresh_calibration.py" --camera-uid "$CAMERA"
  restart_service
}

# --- preflight ---------------------------------------------------------------

log "Preflight"
for c in "$POSE" "$AUTOCAL"; do
  [[ $(docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null) == true ]] || die "container $c is not running"
done
[[ -f $CONFIG ]] || die "config not found: $CONFIG"

env_of() { docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$POSE"; }
SERVICE_NO_PROXY=$(env_of | sed -n 's/^no_proxy=//p' | head -1)
TOOL_NO_PROXY="${SERVICE_NO_PROXY:+$SERVICE_NO_PROXY,}$HOST"
if env_of | grep -qiE '^https?_proxy=.+' && [[ ",$SERVICE_NO_PROXY," != *",$HOST,"* ]]; then
  die "$HOST is not in the ptz-pose container's no_proxy, so the service can't reach it.
Add it to no_proxy and NO_PROXY of the ptz-pose service in docker-compose.yml, then
recreate the container with ONVIF_USERNAME/ONVIF_PASSWORD exported:
  docker compose --profile ptz-pose up -d ptz-pose"
fi

for c in "$POSE" "$AUTOCAL"; do
  docker exec -u root "$c" rm -rf "$REMOTE"
  docker cp "$TOOLS_DIR" "$c:$REMOTE" >/dev/null
done

position=$(in_pose "$REMOTE/ptz_goto.py" "${ONVIF[@]}" --status-only | tail -1)
START_PAN=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['pan'])" "$position") \
  || die "can't read the PTZ position of $HOST:$PORT: $position"
START_TILT=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['tilt'])" "$position")
echo "ONVIF OK, start position pan=$START_PAN tilt=$START_TILT"
in_pose "$REMOTE/save_fresh_calibration.py" --camera-uid "$CAMERA" --dry-run \
  || die "the camera must see at least 6 AprilTags from its start position"

cp "$CONFIG" "$OUT/cameras.json.before"
existing=$(cfg --get onvif_host)
[[ $SKIP_SCALE -eq 0 || $(cfg --get pan_scale) != null || $(cfg --get pan_curve) != null ]] \
  || die "--skip-scale needs a pan_scale or pan_curve already in the config"

cat <<EOF

About to tune $CAMERA ($HOST:$PORT). This will:
  - pause tracking of $CAMERA and drive the camera through several sweeps
  - write lens settings to Scenescape and results to $CONFIG
  - save fresh auto-calibrations as its home and restart $POSE several times
  - finish at the start position (pan=$START_PAN tilt=$START_TILT)
Config entry: $([[ $existing == null ]] && echo "new" || echo "existing, will be updated")
Backup and all measurements: $OUT
EOF
if [[ $YES -eq 0 ]]; then
  read -rp "Continue? [y/N] " answer
  [[ $answer == [yY]* ]] || exit 0
fi

DONE=0
restore() {
  [[ $DONE -eq 1 ]] && return
  echo -e "\nNot finished; restoring $CONFIG from $OUT/cameras.json.before" >&2
  cat "$OUT/cameras.json.before" > "$CONFIG"   # same inode: the container bind-mounts the file
  docker restart "$POSE" >/dev/null || true
}
trap restore EXIT

cfg --set onvif_host="\"$HOST\"" --set onvif_port="$PORT" --set track=false
restart_service

# --- 1. lens -----------------------------------------------------------------

if [[ $SKIP_LENS -eq 0 ]]; then
  log "1/4 Lens: AprilTag sweep around the start position"
  read -r pan_lo pan_hi tilt_lo tilt_hi < <(python3 -c "
import sys; p, t, sp, st = map(float, sys.argv[1:])
print(p - sp, p + sp, max(-1.0, t - st), min(1.0, t + st))" \
    "$START_PAN" "$START_TILT" "$LENS_PAN_SPAN" "$LENS_TILT_SPAN")
  in_pose "$REMOTE/collect_calibration_views.py" --camera-uid "$CAMERA" "${ONVIF[@]}" \
      --pan-range "$pan_lo" "$pan_hi" --tilt-range "$tilt_lo" "$tilt_hi" \
      --output "/tmp/views_$CAMERA.json" | tail -3
  relay "/tmp/views_$CAMERA.json"
  in_autocal "$REMOTE/calibrate_intrinsics.py" --camera-uid "$CAMERA" \
      --input "/tmp/views_$CAMERA.json" --apply --result-json "/tmp/lens_$CAMERA.json" \
      | grep -E 'Current|Fitted|distortion|reprojection|uncertainty|WARNING|Applied|resolution'
  docker cp "$AUTOCAL:/tmp/lens_$CAMERA.json" "$OUT/lens.json" >/dev/null
  if [[ $(json "$OUT/lens.json" 'd["poorly_constrained"]') == True && $ACCEPT_POOR_LENS -eq 0 ]]; then
    die "lens fit is poorly constrained; widen --lens-span or pass --accept-poor-lens"
  fi
  cfg --merge "$OUT/lens.json:config"
fi

# --- 2. scale ----------------------------------------------------------------

if [[ $SKIP_SCALE -eq 0 ]]; then
  log "2/4 Scale: texture sweep over pan ${SCALE_PAN_RANGE[*]}, tilt ${SCALE_TILT_RANGE[*]}"
  in_pose "$REMOTE/capture_ptz_sweep.py" --camera-uid "$CAMERA" "${ONVIF[@]}" \
      --pan-range "${SCALE_PAN_RANGE[@]}" --tilt-range "${SCALE_TILT_RANGE[@]}" \
      --output-dir "/tmp/ptz_sweep_$CAMERA" | grep -E 'sweep \(|Wrote'
  relay "/tmp/ptz_sweep_$CAMERA"
  in_autocal "$REMOTE/measure_ptz_scale.py" --camera-uid "$CAMERA" \
      --input-dir "/tmp/ptz_sweep_$CAMERA" --result-json "/tmp/scale_$CAMERA.json" \
      | grep -E '^(pan|tilt):|scale  |across travel|_scale'
  docker cp "$AUTOCAL:/tmp/scale_$CAMERA.json" "$OUT/scale.json" >/dev/null
  [[ $(json "$OUT/scale.json" 'len(d)') == 2 ]] \
    || die "couldn't measure both scales; adjust --scale-pan-range/--scale-tilt-range"
  # Only the magnitude is measured; the fit finds each sign (--try-sign-flips).
  cfg --merge "$OUT/scale.json" --unset pan_curve --unset tilt_curve \
      --unset pan_axis --unset pan_backlash_deg --unset tilt_backlash_deg
fi

# --- 3. model ----------------------------------------------------------------

for round in $(seq "$ROUNDS"); do
  log "3/4 Model: round $round/$ROUNDS (fresh home, measure, fit)"
  new_home
  measure_and_fit "round$round"
  cfg --merge "$OUT/fit_round$round.json:config"
done

# --- 4. verify ---------------------------------------------------------------

log "4/4 Verify: fresh home and a final measurement with the applied values"
new_home
measure_and_fit verify
park

DONE=1
log "Done"
python3 - "$OUT" "$ROUNDS" <<'PY'
import json, os, sys
out, rounds = sys.argv[1], int(sys.argv[2])
print(f"{'stage':<10} {'pan px':>8} {'tilt px':>8}   (mean error of the service's stored pose)")
for tag in [f"round{i}" for i in range(1, rounds + 1)] + ["verify"]:
  path = os.path.join(out, f"fit_{tag}.json")
  if os.path.exists(path):
    axes = json.load(open(path))["axes"]
    cell = lambda a: f"{axes[a]['service_px']:8.2f}" if a in axes else f"{'-':>8}"
    print(f"{tag:<10} {cell('pan')} {cell('tilt')}")
verify = json.load(open(os.path.join(out, "fit_verify.json")))
floor = {a: v["floor_px"] for a, v in verify["axes"].items()}
print("best achievable (floor): " + ", ".join(f"{a} {v:.2f} px" for a, v in floor.items()))
for warning in verify["warnings"]:
  print("WARNING:", warning)
PY
echo
echo "Config entry now in $CONFIG:"
python3 -c "import json,sys; e=[c for c in json.load(open(sys.argv[1]))['cameras'] if c['scene_camera_uid']==sys.argv[2]][0]; print(json.dumps(e, indent=2))" "$CONFIG" "$CAMERA"
echo "Measurements and backup: $OUT"
