#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# check_lidar_object_counts.sh
#
# Compare object counts across the LiDAR detection pipeline for the
# "Lidar Intersection" scene:
#
#   1. scenescape/data/camera/lidar1-raw   (raw PointPillars output, unfiltered)
#   2. scenescape/data/camera/lidar1       (score-filtered publisher output)
#   3. scenescape/regulated/scene/<UID>    (controller → UI, rate+tracker-filtered)
#
# Usage:
#   ./tools/check_lidar_object_counts.sh [DURATION_SECS]
#
# Default DURATION_SECS = 30

DURATION=${1:-30}

BROKER_CONTAINER="scenescape-broker-1"
BROKER_HOST="localhost"
BROKER_PORT="1883"
SCENE_UID="a1b2c3d4-e5f6-4890-abcd-ef1234567890"  # Lidar Intersection

# Use TLS if cert is present, otherwise plain
CAFILE="/mosquitto/secrets/certs/scenescape-ca.pem"
if docker exec "${BROKER_CONTAINER}" test -f "${CAFILE}" 2>/dev/null; then
  MSUB="mosquitto_sub -h ${BROKER_HOST} -p ${BROKER_PORT} --cafile ${CAFILE} --insecure"
else
  MSUB="mosquitto_sub -h ${BROKER_HOST} -p ${BROKER_PORT}"
fi

echo "================================================================"
echo " LiDAR pipeline object-count consistency check"
echo " Scene:    Lidar Intersection (${SCENE_UID})"
echo " Duration: ${DURATION}s"
echo " Broker:   ${BROKER_CONTAINER} ${BROKER_HOST}:${BROKER_PORT}"
echo "================================================================"
echo ""

# ── collect samples in parallel ─────────────────────────────────────────────
TMPDIR_OUT=$(mktemp -d)
RAW_LOG="${TMPDIR_OUT}/lidar1-raw.jsonl"
CAM_LOG="${TMPDIR_OUT}/lidar1.jsonl"
REG_LOG="${TMPDIR_OUT}/regulated.jsonl"

echo "[+] Collecting ${DURATION}s of MQTT messages (3 topics in parallel)..."
echo "    • scenescape/data/camera/lidar1-raw"
echo "    • scenescape/data/camera/lidar1"
echo "    • scenescape/regulated/scene/${SCENE_UID}"
echo ""

# 1. lidar1-raw  (raw PointPillars detections, before score filter)
docker exec "${BROKER_CONTAINER}" \
  ${MSUB} -t "scenescape/data/camera/lidar1-raw" 2>/dev/null \
  > "${RAW_LOG}" &
PID_RAW=$!

# 2. lidar1  (score-filtered, publisher output to controller)
docker exec "${BROKER_CONTAINER}" \
  ${MSUB} -t "scenescape/data/camera/lidar1" 2>/dev/null \
  > "${CAM_LOG}" &
PID_CAM=$!

# 3. regulated for this specific scene only
docker exec "${BROKER_CONTAINER}" \
  ${MSUB} -t "scenescape/regulated/scene/${SCENE_UID}" 2>/dev/null \
  > "${REG_LOG}" &
PID_REG=$!

sleep "${DURATION}"
kill "${PID_RAW}" "${PID_CAM}" "${PID_REG}" 2>/dev/null
wait "${PID_RAW}" "${PID_CAM}" "${PID_REG}" 2>/dev/null

echo ""
echo "================================================================"
echo " Results"
echo "================================================================"

python3 - "${RAW_LOG}" "${CAM_LOG}" "${REG_LOG}" "${DURATION}" <<'PYEOF'
import sys, json, statistics, collections

raw_log    = sys.argv[1]
cam_log    = sys.argv[2]
reg_log    = sys.argv[3]
duration   = float(sys.argv[4])

# ── parse helpers ────────────────────────────────────────────────────────────
def parse_camera_topic(path):
    """data/camera/lidar1[-raw]: objects is a dict of {category: [list]}.
       Count total objects and per-category across frames."""
    counts = []
    by_cat = collections.defaultdict(list)
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            objs = d.get("objects", {})
            if isinstance(objs, dict):
                total = sum(len(v) for v in objs.values())
                counts.append(total)
                for cat, items in objs.items():
                    by_cat[cat].append(len(items))
            elif isinstance(objs, list):
                # Some publishers emit a flat list
                counts.append(len(objs))
                for obj in objs:
                    by_cat[obj.get("type", "unknown")].append(1)
    return counts, dict(by_cat)

def parse_regulated_topic(path):
    """regulated/scene/<uid>: objects is a list of tracked object dicts."""
    counts = []
    by_cat = collections.defaultdict(list)
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            objs = d.get("objects", [])
            if not isinstance(objs, list):
                continue
            counts.append(len(objs))
            cat_in_frame = collections.defaultdict(int)
            for obj in objs:
                cat_in_frame[obj.get("type", "unknown")] += 1
            for cat, n in cat_in_frame.items():
                by_cat[cat].append(n)
    return counts, dict(by_cat)

def summarise(label, counts, by_cat=None):
    if not counts:
        print(f"  {label}: NO DATA RECEIVED")
        return None
    mn  = statistics.mean(counts)
    med = statistics.median(counts)
    fps = len(counts) / duration
    print(f"  {label}:")
    print(f"    frames={len(counts)}  fps={fps:.1f}  "
          f"mean={mn:.1f}  median={med}  min={min(counts)}  max={max(counts)}")
    if by_cat:
        for cat, cc in sorted(by_cat.items()):
            if cc:
                print(f"      [{cat}] mean={statistics.mean(cc):.1f}  "
                      f"min={min(cc)}  max={max(cc)}")
    return mn

# ── stage 1: lidar1-raw ──────────────────────────────────────────────────────
print()
print("── [1] data/camera/lidar1-raw  (raw PointPillars, all scores) ───────")
raw_counts, raw_by_cat = parse_camera_topic(raw_log)
raw_mean = summarise("lidar1-raw", raw_counts, raw_by_cat)

# ── stage 2: lidar1 ──────────────────────────────────────────────────────────
print()
print("── [2] data/camera/lidar1      (score-filtered, publisher output) ───")
cam_counts, cam_by_cat = parse_camera_topic(cam_log)
cam_mean = summarise("lidar1", cam_counts, cam_by_cat)

# ── stage 3: regulated ───────────────────────────────────────────────────────
print()
print("── [3] regulated/scene/<uid>   (tracker+rate-limited, shown in UI) ──")
reg_counts, reg_by_cat = parse_regulated_topic(reg_log)
reg_mean = summarise("regulated", reg_counts, reg_by_cat)

# ── mismatch analysis ────────────────────────────────────────────────────────
print()
print("── Mismatch Analysis ────────────────────────────────────────────────")

def cmp(a_label, a_mean, b_label, b_mean):
    if a_mean is None or b_mean is None:
        print(f"  {a_label} → {b_label}: SKIP (no data)")
        return
    if a_mean == 0:
        print(f"  {a_label} → {b_label}: {a_label} has 0 objects, nothing to compare")
        return
    diff = a_mean - b_mean
    pct  = 100.0 * diff / a_mean
    flag = "⚠️  MISMATCH" if abs(pct) > 15 else "✅ OK"
    print(f"  {a_label} mean={a_mean:.1f}  →  {b_label} mean={b_mean:.1f}  "
          f"  diff={diff:+.1f} ({pct:+.0f}%)  {flag}")

cmp("lidar1-raw", raw_mean, "lidar1",    cam_mean)
cmp("lidar1",    cam_mean,  "regulated", reg_mean)
cmp("lidar1-raw", raw_mean, "regulated", reg_mean)

print()
print("  Pipeline stages:")
print("  lidar1-raw  → score filter (publisher)  → lidar1")
print("  lidar1      → tracker reliability gate  → data/scene/<uid>/<type>")
print("  data/scene  → regulated-rate limiter    → regulated (UI)")
print()
print("  Known causes of count reduction at each stage:")
print("  [raw→lidar1]    Score threshold in lidar_publisher (default ≥0.20).")
print("  [lidar1→reg]    Tracker needs ≥3 consecutive frames before 'reliable'.")
print("                  Objects unseen >0.333s are dropped (MAX_UNRELIABLE_TIME).")
print("                  regulated publishes at scene.regulated_rate (default 5 fps)")
print("                  so stale frames may show fewer objects than the live rate.")
print("  [raw→reg]       Combined effect of both filters above.")
print()
print("  Debug tip: docker logs -f scenescape-lidar-stream-1 2>&1 | grep -E 'raw|regulated|objects'")
PYEOF

echo ""
echo "[+] Raw JSONL files saved in: ${TMPDIR_OUT}"
echo "    lidar1-raw.jsonl  lidar1.jsonl  regulated.jsonl"
echo ""
echo "    Quick per-frame count from lidar1-raw:"
echo "    python3 -c \"import sys,json; [print(sum(len(v) for v in json.loads(l).get('objects',{}).values())) for l in open('${RAW_LOG}') if l.strip()]\""
