#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Build OpenVINO FP16 YOLO-World IR for DLStreamer gvadetect (person + basketball).
#
# Default (no usable HF OpenVINO YOLO-World IR): Ultralytics yolov8s-worldv2
# with classes {person, basketball} → OpenVINO export (half=True) →
# compress_to_fp16 → DEST/*.xml|.bin
#
# Optional override if an OpenVINO IR snapshot appears on HF later:
#   YOLO_WORLD_HF_REPO=<org/name> bash prepare_yolo_world.sh
#
# Uses corporate proxy from repo .cursor_proxy.env when present.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
DEST="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/yolov8s-worldv2-person-basketball"
VENV="${YOLO_WORLD_VENV:-/tmp/yolo-world-venv}"
HF_REPO="${YOLO_WORLD_HF_REPO:-}"
CLASSES="${YOLO_WORLD_CLASSES:-person,basketball}"

# Corporate DMZ proxy (do not keep Cursor sandbox 127.0.0.1 / SOCKS proxies).
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
echo "Using HTTPS_PROXY=${HTTPS_PROXY}"

python3 -m venv "${VENV}"
"${VENV}/bin/pip" install -q --upgrade pip
"${VENV}/bin/pip" install -q 'huggingface_hub>=0.23' ultralytics 'openvino>=2024.0'

mkdir -p "${DEST}"

if [[ -n "${HF_REPO}" ]]; then
  echo "Downloading OpenVINO YOLO-World from Hugging Face: ${HF_REPO}"
  "${VENV}/bin/python" - <<PY
from pathlib import Path
import shutil
from huggingface_hub import snapshot_download

dest = Path("${DEST}")
tmpdir = Path(snapshot_download(repo_id="${HF_REPO}"))
# Accept either flat IR or nested */*.xml
xmls = sorted(tmpdir.rglob("*.xml"))
if not xmls:
  raise SystemExit(f"No OpenVINO .xml found under {tmpdir}")
xml = xmls[0]
bin_path = xml.with_suffix(".bin")
if not bin_path.is_file():
  raise SystemExit(f"Missing weights next to {xml}")
dest.mkdir(parents=True, exist_ok=True)
for stale in dest.glob("*.xml"):
  stale.unlink(missing_ok=True)
for stale in dest.glob("*.bin"):
  stale.unlink(missing_ok=True)
shutil.copy2(xml, dest / "yolov8s-worldv2-person-basketball.xml")
shutil.copy2(bin_path, dest / "yolov8s-worldv2-person-basketball.bin")
print("HF IR installed from", xml)
PY
else
  echo "Converting Ultralytics yolov8s-worldv2 → OpenVINO FP16 (person, basketball)"
  "${VENV}/bin/python" - <<PY
from pathlib import Path
import shutil
import openvino as ov
from ultralytics import YOLOWorld

dest = Path("${DEST}")
classes = [c.strip() for c in "${CLASSES}".split(",") if c.strip()]
dest.mkdir(parents=True, exist_ok=True)

model = YOLOWorld("yolov8s-worldv2.pt")
model.set_classes(classes)
pt = dest.parent / "yolov8s-worldv2-person-basketball.pt"
model.save(str(pt))
# Prefer native FP16 export; compress if the export stays FP32.
export_dir = Path(model.export(format="openvino", imgsz=640, half=True, dynamic=False))
xmls = list(export_dir.glob("*.xml"))
if not xmls:
  raise SystemExit(f"OpenVINO export produced no xml under {export_dir}")
core = ov.Core()
m = core.read_model(xmls[0])
out_xml = dest / "yolov8s-worldv2-person-basketball.xml"
ov.save_model(m, str(out_xml), compress_to_fp16=True)
# Drop temporary export tree / pt (regenerable)
shutil.rmtree(export_dir, ignore_errors=True)
pt.unlink(missing_ok=True)
print("OpenVINO FP16 IR at", out_xml)
print("names", model.names)
PY
fi

# Ensure model-proc sits beside the IR (compose bind-mounts this directory)
PROC_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/yolo-world-person-basketball.json"
if [[ -f "${PROC_SRC}" ]]; then
  cp -f "${PROC_SRC}" "${DEST}/yolo-world-person-basketball.json"
elif [[ ! -f "${DEST}/yolo-world-person-basketball.json" ]]; then
  cat > "${DEST}/yolo-world-person-basketball.json" <<'EOF'
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
fi

echo "DONE: ${DEST} (use with gvadetect device=GPU in basketball-config.json)"
