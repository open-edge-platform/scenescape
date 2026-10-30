#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Fine-tune closed-set YOLOv8s on person+basketball, export OpenVINO FP16.
#
# Prerequisites: prepare_dataset.py has produced dataset/data.yaml
#
#   bash sample_data/demo_scenes/Basketball/models/finetune/train_and_export.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../.." && pwd)"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATASET="${YOLO_FT_DATASET:-${HERE}/dataset}"
DEST="${YOLO_FT_DEST:-${HERE}/../yolov8s-ft-person-basketball}"
VENV="${YOLO_FT_VENV:-/tmp/yolo-ft-venv}"
BASE="${YOLO_FT_BASE:-yolov8s.pt}"
EPOCHS="${YOLO_FT_EPOCHS:-60}"
IMGSZ="${YOLO_FT_IMGSZ:-640}"
BATCH="${YOLO_FT_BATCH:-8}"
DEVICE="${YOLO_FT_DEVICE:-cpu}"
RUN_NAME="${YOLO_FT_NAME:-bball_ft}"

unset ALL_PROXY all_proxy SOCKS_PROXY socks_proxy SOCKS5_PROXY socks5_proxy \
  GIT_HTTP_PROXY GIT_HTTPS_PROXY || true
if [[ -f "${ROOT}/.cursor_proxy.env" ]]; then
  # shellcheck disable=SC1091
  set -a && . "${ROOT}/.cursor_proxy.env" && set +a
fi
: "${HTTP_PROXY:=http://proxy-dmz.intel.com:911}"
: "${HTTPS_PROXY:=http://proxy-dmz.intel.com:912}"
: "${http_proxy:=${HTTP_PROXY}}"
: "${https_proxy:=${HTTPS_PROXY}}"
: "${NO_PROXY:=localhost,127.0.0.1,::1,.intel.com}"
: "${no_proxy:=${NO_PROXY}}"
export HTTP_PROXY HTTPS_PROXY http_proxy https_proxy NO_PROXY no_proxy

if [[ ! -f "${DATASET}/data.yaml" ]]; then
  echo "Missing ${DATASET}/data.yaml — run prepare_dataset.py first" >&2
  exit 1
fi

python3 -m venv "${VENV}"
"${VENV}/bin/pip" install -q --upgrade pip
"${VENV}/bin/pip" install -q ultralytics 'openvino>=2024.0'

echo "Training ${BASE} on ${DATASET} for ${EPOCHS} epochs (device=${DEVICE})"
"${VENV}/bin/yolo" detect train \
  model="${BASE}" \
  data="${DATASET}/data.yaml" \
  epochs="${EPOCHS}" \
  imgsz="${IMGSZ}" \
  batch="${BATCH}" \
  device="${DEVICE}" \
  project="${HERE}/runs" \
  name="${RUN_NAME}" \
  exist_ok=True \
  patience=20 \
  pretrained=True

BEST="${HERE}/runs/${RUN_NAME}/weights/best.pt"
if [[ ! -f "${BEST}" ]]; then
  echo "Missing ${BEST}" >&2
  exit 1
fi

echo "Exporting ${BEST} → OpenVINO FP16 at ${DEST}"
mkdir -p "${DEST}"
"${VENV}/bin/python" - <<PY
from pathlib import Path
import shutil
import openvino as ov
from ultralytics import YOLO

dest = Path("${DEST}")
dest.mkdir(parents=True, exist_ok=True)
model = YOLO("${BEST}")
export_dir = Path(model.export(format="openvino", imgsz=int("${IMGSZ}"), half=True, dynamic=False))
xmls = list(export_dir.glob("*.xml"))
if not xmls:
  raise SystemExit(f"no xml in {export_dir}")
core = ov.Core()
m = core.read_model(xmls[0])
out_xml = dest / "yolov8s-ft-person-basketball.xml"
ov.save_model(m, str(out_xml), compress_to_fp16=True)
shutil.rmtree(export_dir, ignore_errors=True)
print("IR", out_xml, "bin_MB", out_xml.with_suffix(".bin").stat().st_size / 1e6)
print("names", model.names)
PY

# 2-class model-proc (fine-tune head is person=0, basketball=1)
cat > "${DEST}/yolo-ft-person-basketball.json" <<'EOF'
{
  "json_schema_version": "2.2.0",
  "input_preproc": [
    {
      "params": {
        "resize": "aspect-ratio",
        "range": [0.0, 1.0]
      }
    }
  ],
  "output_postproc": [
    {
      "converter": "yolo_v8",
      "labels": ["person", "basketball"]
    }
  ]
}
EOF

cat > "${DEST}/metadata.yaml" <<EOF
description: 'Fine-tuned YOLOv8s person+basketball (OpenVINO FP16)'
base: ${BASE}
epochs: ${EPOCHS}
dataset: ${DATASET}
precision: FP16
best_pt: ${BEST}
EOF

echo "DONE: ${DEST}"
echo "Point basketball-config.json model= / model-proc= at this directory and recreate basketball-video."
