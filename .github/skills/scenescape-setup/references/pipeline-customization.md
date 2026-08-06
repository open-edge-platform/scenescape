<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Pipeline customization via dlstreamer-coding-agent

Optional path inside bootstrap (step 6). Runs **only** when
`pipeline_customization_prompt` in `deploy-inputs.json` is non-empty.

## Do not reinvent DL Streamer pipeline authoring

Pipeline design, model prep, build/run, and proxy-input validation belong to the
upstream skill — **read and follow it**, do not copy its procedure into this repo:

- Skill: [dlstreamer-coding-agent](https://github.com/open-edge-platform/dlstreamer/tree/main/.github/skills/dlstreamer-coding-agent)
- Canonical clone path (if you have the dlstreamer repo locally):
  `<dlstreamer-checkout>/.github/skills/dlstreamer-coding-agent/SKILL.md`
- Prefer a local checkout when available; otherwise fetch that skill’s `SKILL.md`
  and its `references/` (especially `pipeline-construction.md` and
  `debugging-hints.md`) from the GitHub URL above.

That skill builds/validates a DL Streamer pipeline (often against a local sample
file via `filesrc`/`decodebin`). SceneScape then **only** adapts the proven
pipeline string into `pipeline-config.json`.

## When to use which skill

| Intent | Skill |
| --- | --- |
| Multi-camera SceneScape deploy (scene/spatial tracking, cross-camera alerts) with an optional custom vision pipeline | `scenescape-setup` (this skill), which **delegates** pipeline authoring to `dlstreamer-coding-agent` when a prompt is set |
| Standalone DL Streamer sample app / script with no SceneScape scene | `dlstreamer-coding-agent` alone |

## Agent procedure (when prompt is set)

Before finishing step 6 / before the orchestrator can pass bootstrap:

1. Load and follow **dlstreamer-coding-agent** with the user’s
   `pipeline_customization_prompt` (plus any KPI/device hints they gave).
2. Complete that skill’s validate step (its Step 5) against a proxy/sample
   input. Do not hand SceneScape an untested pipeline.
3. Write the handoff artifact (below). Fail the deploy if validation did not
   succeed — do not silently keep `adapt_pipeline_config.py` defaults.
4. Continue SceneScape bootstrap; `configure_pipeline.py` merges the artifact.

Empty / missing prompt → skip all of the above; defaults unchanged.

Ready-to-run prompts with downloadable Metro datasets:
[06-smart-parking-custom-pipeline.md](../example-prompts/06-smart-parking-custom-pipeline.md),
[07-smart-intersection-custom-pipeline.md](../example-prompts/07-smart-intersection-custom-pipeline.md).

## Handoff artifact

Path: `<deploy_dir>/pipeline-customization/result.json`

```json
{
  "pipeline": "<gstreamer pipeline string from dlstreamer-coding-agent>",
  "validation": {
    "ran_successfully": true,
    "fps": 18.5,
    "latency_ms": 40,
    "device": "CPU"
  },
  "metadatagenpolicy": "reidPolicy"
}
```

| Field | Required | Notes |
| --- | --- | --- |
| `pipeline` | yes | Single GST pipeline string the coding agent validated |
| `validation.ran_successfully` | yes | Must be `true` or configure fails |
| `validation.fps` / `latency_ms` / `device` | no | Include when measured |
| `metadatagenpolicy` | no | One of `detectionPolicy`, `detection3DPolicy`, `reidPolicy`, `classificationPolicy`, `ocrPolicy` |

## What scenescape-setup still does (`configure_pipeline.py`)

Structural merge **and conversion** into DL Streamer Pipeline Server + SceneScape
native plugins — **not** a second copy of dlstreamer-coding-agent:

1. Always rewrite the leading source to
   `rtspsrc location={rtsp_url} add-reference-timestamp-meta=true latency=200`.
2. Replace file/`decodebin` decode with the SceneScape RTSP H.264 chain when needed
   (`rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! video/x-raw,format=BGR`).
3. **Inject or rename** `sscape_timestamp_capture name=timesync` before the first
   inference element (`gvadetect` / `gvaclassify` / …).
4. Ensure `gvametaconvert add-tensor-data=true name=metaconvert` after inference.
5. **Inject** `sscape_post_inference_data_publish name=datapublisher` after metaconvert.
6. Strip UI sinks (`gvawatermark`, `autovideosink`, …) and old `gvapython` adapter
   pieces; append `gvametapublish name=destination … ! appsink sync=true`.
7. Validate `metadatagenpolicy` against SceneScape’s publish element; write per-camera
   `pipeline-config.json` entries with the DPS `parameters` schema.

Fail only when normalization cannot find inference elements or policy is invalid —
a typical coding-agent sample pipeline **without** SceneScape elements is converted,
not rejected.

## Standalone merge

```bash
python3 "$SKILL_DIR/scripts/configure_pipeline.py" \
  --deploy-dir <deploy_dir> \
  --from-deploy-inputs
```

Requires `pipeline-customization/result.json` when a prompt is set.
