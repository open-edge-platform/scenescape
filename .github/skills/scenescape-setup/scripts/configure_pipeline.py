# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Merge a dlstreamer-coding-agent pipeline into SceneScape pipeline-config.json.

Pipeline authoring and proxy-input validation are owned by the upstream skill:
https://github.com/open-edge-platform/dlstreamer/tree/main/.github/skills/dlstreamer-coding-agent

This script:
  - no-ops when pipeline_customization_prompt is empty
  - reads <deploy_dir>/pipeline-customization/result.json written after that skill runs
  - rejects unvalidated handoffs
  - structurally normalizes for DL Streamer Pipeline Server + SceneScape native plugins:
      rtspsrc → (RTSP decode) → sscape_timestamp_capture → inference →
      gvametaconvert → sscape_post_inference_data_publish → gvametapublish → appsink

See references/pipeline-customization.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from adapt_pipeline_config import PIPELINE_PARAMETERS
from deploy_inputs import load_inputs

SUPPORTED_POLICIES = frozenset({
  "detectionPolicy",
  "detection3DPolicy",
  "reidPolicy",
  "classificationPolicy",
  "ocrPolicy",
})

RESULT_RELATIVE = Path("pipeline-customization") / "result.json"

RTSP_SOURCE = (
  "rtspsrc location={rtsp_url} add-reference-timestamp-meta=true latency=200"
)
TIMESYNC = "sscape_timestamp_capture name=timesync ntp-server=ntpserv"
METACONVERT = "gvametaconvert add-tensor-data=true name=metaconvert"
DATAPUBLISHER = "sscape_post_inference_data_publish name=datapublisher"
TERMINAL_PUBLISH = "gvametapublish name=destination method=file file-path=/dev/null"
TERMINAL_SINK = "appsink sync=true"

# Standard H.264 RTSP decode used by adapt_pipeline_config.py defaults.
RTSP_DECODE_CHAIN = [
  "rtph264depay",
  "h264parse",
  "avdec_h264",
  "videoconvert",
  "video/x-raw,format=BGR",
]

# Leading elements that belong to file/URI decode — drop when forcing RTSP.
_FILE_DECODE_ELEMENTS = frozenset({
  "filesrc",
  "urisourcebin",
  "uridecodebin",
  "uridecodebin3",
  "decodebin",
  "decodebin3",
  "parsebin",
})

# Inference / analytics elements whose outputs feed SceneScape metadata.
_INFERENCE_ELEMENTS = frozenset({
  "gvadetect",
  "gvaclassify",
  "gvainference",
  "gvatrack",
  "gvaattachroi",
  "gvawatermark",  # treated as post-inference UI; stripped separately
})

# Must not remain in a SceneScape DPS pipeline after normalization.
_DROP_ELEMENTS = frozenset({
  "gvawatermark",
  "gvapython",  # former sscape_adapter path
  "autovideosink",
  "xvimagesink",
  "ximagesink",
  "glimagesink",
  "gtksink",
  "fpsdisplaysink",
  "filesink",
  "fakesink",
  "appsink",
  "gvametapublish",
  "sscape_timestamp_capture",
  "sscape_post_inference_data_publish",
  "sscape_post_decode_timestamp_capture",
})


class PipelineCustomizationError(Exception):
  """Fail-fast error for customized pipeline mode."""


def _prompt_from_inputs(payload: dict[str, Any]) -> str:
  return str(payload.get("pipeline_customization_prompt") or "").strip()


def result_path(deploy_dir: Path) -> Path:
  return deploy_dir / RESULT_RELATIVE


def load_agent_result(path: Path) -> dict[str, Any]:
  if not path.is_file():
    raise PipelineCustomizationError(
      f"missing handoff artifact {path}; when pipeline_customization_prompt is set, "
      "follow the dlstreamer-coding-agent skill "
      "(https://github.com/open-edge-platform/dlstreamer/tree/main/.github/skills/"
      "dlstreamer-coding-agent), validate the pipeline, then write result.json"
    )
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
  except json.JSONDecodeError as exc:
    raise PipelineCustomizationError(f"invalid JSON in {path}: {exc}") from exc
  if not isinstance(data, dict):
    raise PipelineCustomizationError(f"{path} must contain a JSON object")
  return data


def require_validated_pipeline(response: dict[str, Any]) -> str:
  if response.get("error"):
    raise PipelineCustomizationError(
      f"pipeline customization error: {response['error']}"
    )
  validation = response.get("validation")
  if not isinstance(validation, dict):
    raise PipelineCustomizationError(
      "handoff missing validation summary; refusing to wire in an unvalidated pipeline "
      "(dlstreamer-coding-agent Step 5 must succeed first)"
    )
  if validation.get("ran_successfully") is not True:
    detail = validation.get("detail") or validation.get("error") or "ran_successfully is not true"
    raise PipelineCustomizationError(
      f"dlstreamer-coding-agent validation failed: {detail}"
    )
  pipeline = response.get("pipeline")
  if not isinstance(pipeline, str) or not pipeline.strip():
    raise PipelineCustomizationError("handoff missing a non-empty pipeline string")
  return pipeline.strip()


def split_pipeline(pipeline: str) -> list[str]:
  parts = [part.strip() for part in pipeline.split("!") if part.strip()]
  if not parts:
    raise PipelineCustomizationError("generated pipeline is empty")
  return parts


def join_pipeline(parts: list[str]) -> str:
  return " ! ".join(parts)


def element_factory(part: str) -> str:
  token = part.strip().split()[0] if part.strip() else ""
  if not token:
    raise PipelineCustomizationError(f"empty pipeline element: {part!r}")
  return token


def rewrite_source(parts: list[str], rtsp_url: str) -> list[str]:
  """Always force SceneScape's rtspsrc; coding agent often used filesrc/decodebin."""
  return [RTSP_SOURCE.format(rtsp_url=rtsp_url), *parts[1:]]


def strip_file_decode_prefix(parts: list[str]) -> list[str]:
  """Remove file/URI decodebin chain left after source rewrite."""
  out = [parts[0]]
  i = 1
  while i < len(parts) and element_factory(parts[i]) in _FILE_DECODE_ELEMENTS:
    i += 1
  out.extend(parts[i:])
  return out


def ensure_rtsp_decode(parts: list[str]) -> list[str]:
  """Ensure H.264 RTSP depay/decode before analytics (SceneScape default chain)."""
  factories = [element_factory(p) for p in parts]
  if "rtph264depay" in factories:
    return parts
  # Insert standard decode immediately after rtspsrc, then drop a redundant
  # videoconvert / BGR caps pair the coding agent often left after decodebin.
  rest = parts[1:]
  while rest and element_factory(rest[0]) in {"videoconvert"}:
    rest = rest[1:]
    if rest and element_factory(rest[0]).startswith("video/x-raw"):
      rest = rest[1:]
  return [parts[0], *RTSP_DECODE_CHAIN, *rest]


def strip_non_scenescape_tail(parts: list[str]) -> list[str]:
  """Drop UI sinks, old gvapython adapter, and any prior SceneScape tail elements."""
  kept: list[str] = []
  for part in parts:
    factory = element_factory(part)
    if factory in _DROP_ELEMENTS:
      continue
    # Drop bare gvametaconvert here only if we will re-add a canonical one later;
    # keep inference and decode pieces.
    kept.append(part)
  if len(kept) < 2:
    raise PipelineCustomizationError(
      "pipeline has no usable elements after stripping UI/sinks; "
      "expected inference elements from dlstreamer-coding-agent"
    )
  return kept


def find_inference_span(parts: list[str]) -> tuple[int, int]:
  """Return [start, end) indices of the primary inference block (gvadetect/etc.)."""
  start = None
  end = None
  for idx, part in enumerate(parts):
    factory = element_factory(part)
    if factory in _INFERENCE_ELEMENTS and factory != "gvawatermark":
      if start is None:
        start = idx
      end = idx + 1
  if start is None or end is None:
    raise PipelineCustomizationError(
      "cannot normalize: no DL Streamer inference element found "
      f"(expected one of {sorted(e for e in _INFERENCE_ELEMENTS if e != 'gvawatermark')})"
    )
  return start, end


def inject_timesync(parts: list[str], inference_start: int) -> list[str]:
  """Place sscape_timestamp_capture immediately before the first inference element."""
  # Remove any existing timesync (should already be stripped) and insert canonical.
  return [*parts[:inference_start], TIMESYNC, *parts[inference_start:]]


def normalize_metaconvert_part(part: str) -> str:
  factory = element_factory(part)
  if factory != "gvametaconvert":
    return part
  # Rebuild a canonical metaconvert, preserving extra properties except name/add-tensor-data.
  props = part[len(factory):].strip()
  props = re.sub(r"\bname=\S+", "", props)
  props = re.sub(r"\badd-tensor-data=\S+", "", props)
  props = re.sub(r"\s+", " ", props).strip()
  base = METACONVERT
  if props:
    return f"{base} {props}"
  return base


def inject_metaconvert_and_datapublish(parts: list[str], inference_end: int) -> list[str]:
  """After inference, keep/normalize gvametaconvert then force datapublisher."""
  head = parts[:inference_end]
  tail = parts[inference_end:]

  # Pull an existing gvametaconvert out of the tail (first only); drop extras.
  meta = None
  rest: list[str] = []
  for part in tail:
    if element_factory(part) == "gvametaconvert":
      if meta is None:
        meta = normalize_metaconvert_part(part)
      continue
    if element_factory(part) == "sscape_post_inference_data_publish":
      continue
    rest.append(part)

  if meta is None:
    meta = METACONVERT

  return [*head, meta, DATAPUBLISHER, *rest]


def append_terminal_sink(parts: list[str]) -> list[str]:
  # Remove any trailing sinks that slipped through, then append canonical pair.
  while parts and element_factory(parts[-1]) in {
    "appsink", "fakesink", "gvametapublish", "autovideosink", "xvimagesink",
  }:
    parts = parts[:-1]
  return [*parts, TERMINAL_PUBLISH, TERMINAL_SINK]


def assert_scenescape_shape(parts: list[str]) -> None:
  factories = [element_factory(p) for p in parts]
  if factories[0] != "rtspsrc":
    raise PipelineCustomizationError("normalization failed: pipeline must start with rtspsrc")
  if "add-reference-timestamp-meta=true" not in parts[0]:
    raise PipelineCustomizationError("rtspsrc must set add-reference-timestamp-meta=true")
  if TIMESYNC.split()[0] not in factories:
    raise PipelineCustomizationError("normalization failed: missing sscape_timestamp_capture")
  if "gvametaconvert" not in factories:
    raise PipelineCustomizationError("normalization failed: missing gvametaconvert")
  if DATAPUBLISHER.split()[0] not in factories:
    raise PipelineCustomizationError(
      "normalization failed: missing sscape_post_inference_data_publish"
    )
  if "gvametapublish" not in factories or "appsink" not in factories:
    raise PipelineCustomizationError("normalization failed: missing terminal publish/appsink")

  # Load-bearing names for DPS parameters schema.
  timesync = next(p for p in parts if element_factory(p) == "sscape_timestamp_capture")
  meta = next(p for p in parts if element_factory(p) == "gvametaconvert")
  publish = next(p for p in parts if element_factory(p) == "sscape_post_inference_data_publish")
  dest = next(p for p in parts if element_factory(p) == "gvametapublish")
  if "name=timesync" not in timesync:
    raise PipelineCustomizationError("sscape_timestamp_capture must use name=timesync")
  if "name=metaconvert" not in meta:
    raise PipelineCustomizationError("gvametaconvert must use name=metaconvert")
  if "name=datapublisher" not in publish:
    raise PipelineCustomizationError(
      "sscape_post_inference_data_publish must use name=datapublisher"
    )
  if "name=destination" not in dest:
    raise PipelineCustomizationError("gvametapublish must use name=destination")


def normalize_pipeline(pipeline: str, rtsp_url: str) -> str:
  """Convert a coding-agent pipeline into SceneScape DPS native-plugin form.

  Rewrites (not merely validates):
    - leading source → rtspsrc with SceneScape RTSP URL
    - file decodebin → RTSP H.264 decode chain when needed
    - inject/rename sscape_timestamp_capture name=timesync before inference
    - ensure gvametaconvert name=metaconvert after inference
    - inject sscape_post_inference_data_publish name=datapublisher
    - replace UI sinks with gvametapublish/appsink terminal
  """
  parts = split_pipeline(pipeline)
  parts = rewrite_source(parts, rtsp_url)
  parts = strip_file_decode_prefix(parts)
  parts = ensure_rtsp_decode(parts)
  parts = strip_non_scenescape_tail(parts)

  inference_start, inference_end = find_inference_span(parts)
  parts = inject_timesync(parts, inference_start)
  # Inference block shifted by +1 after timesync insert.
  inference_end += 1
  parts = inject_metaconvert_and_datapublish(parts, inference_end)
  parts = append_terminal_sink(parts)
  assert_scenescape_shape(parts)
  return join_pipeline(parts)


def resolve_policy(response: dict[str, Any], existing: str | None) -> str:
  policy = response.get("metadatagenpolicy")
  if policy is None or policy == "":
    return existing or "detectionPolicy"
  if not isinstance(policy, str) or policy not in SUPPORTED_POLICIES:
    raise PipelineCustomizationError(
      f"unsupported metadatagenpolicy {policy!r}; "
      f"valid: {sorted(SUPPORTED_POLICIES)}"
    )
  return policy


def apply_custom_pipeline(
  config: dict[str, Any],
  camera_ids: list[str],
  streams: list[str],
  response: dict[str, Any],
) -> dict[str, Any]:
  raw_pipeline = require_validated_pipeline(response)
  pipelines = config.setdefault("config", {}).setdefault("pipelines", [])
  by_name = {entry.get("name"): entry for entry in pipelines if isinstance(entry, dict)}

  for camera_id, rtsp_url in zip(camera_ids, streams):
    entry = by_name.get(camera_id)
    if entry is None:
      raise PipelineCustomizationError(
        f"pipeline-config.json has no entry for camera_id={camera_id!r}; "
        "run adapt_pipeline_config.py first"
      )
    normalized = normalize_pipeline(raw_pipeline, rtsp_url)
    entry["pipeline"] = normalized
    entry["parameters"] = PIPELINE_PARAMETERS
    payload = entry.setdefault("payload", {}).setdefault("parameters", {})
    existing_policy = payload.get("metadatagenpolicy")
    if isinstance(existing_policy, str):
      policy = resolve_policy(response, existing_policy)
    else:
      policy = resolve_policy(response, None)
    payload["metadatagenpolicy"] = policy
    payload["cameraid"] = camera_id
    payload.setdefault("ntp_config", "ntpserv")
    payload.setdefault("frame_ntp_config", False)
    payload.setdefault("detection_labels", "person")
  return config


def configure_pipeline(deploy_dir: Path, payload: dict[str, Any] | None = None) -> str:
  """Merge coding-agent handoff into pipeline-config.json when a prompt is present."""
  if payload is None:
    payload = load_inputs(deploy_dir)
  prompt = _prompt_from_inputs(payload)
  config_path = deploy_dir / "dlstreamer-pipeline-server" / "pipeline-config.json"

  if not prompt:
    return "pipeline customization skipped (no pipeline_customization_prompt)"

  if not config_path.is_file():
    raise PipelineCustomizationError(
      f"missing {config_path}; run adapt_pipeline_config.py before configure_pipeline.py"
    )

  response = load_agent_result(result_path(deploy_dir))
  config = json.loads(config_path.read_text(encoding="utf-8"))
  updated = apply_custom_pipeline(
    config,
    list(payload["camera_ids"]),
    list(payload["streams"]),
    response,
  )
  config_path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
  return f"pipeline customization applied for cameras={payload['camera_ids']}"


def main() -> None:
  parser = argparse.ArgumentParser(
    description=(
      "Merge dlstreamer-coding-agent handoff (pipeline-customization/result.json) "
      "into SceneScape pipeline-config.json with native-plugin normalization"
    ),
  )
  parser.add_argument("--deploy-dir", required=True, type=Path)
  parser.add_argument("--from-deploy-inputs", action="store_true",
                      help="Read deploy-inputs.json from deploy-dir (default)")
  parser.add_argument("--inputs-file", type=Path)
  parser.add_argument(
    "--result-file",
    type=Path,
    help="Override path to coding-agent handoff JSON "
         "(default: <deploy-dir>/pipeline-customization/result.json)",
  )
  args = parser.parse_args()

  if args.inputs_file is not None:
    payload = json.loads(args.inputs_file.read_text(encoding="utf-8"))
  else:
    payload = load_inputs(args.deploy_dir)

  if args.result_file is not None and _prompt_from_inputs(payload):
    expected = result_path(args.deploy_dir)
    if args.result_file.resolve() != expected.resolve():
      expected.parent.mkdir(parents=True, exist_ok=True)
      expected.write_text(args.result_file.read_text(encoding="utf-8"), encoding="utf-8")

  try:
    message = configure_pipeline(args.deploy_dir, payload)
  except PipelineCustomizationError as exc:
    print(f"ERROR: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc
  print(message)


if __name__ == "__main__":
  main()
