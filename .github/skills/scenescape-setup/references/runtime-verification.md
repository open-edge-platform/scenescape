<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Runtime Verification and Troubleshooting

Load only when Step 7 or Step 9 fails in [SKILL.md](../SKILL.md).

## Step 7 — RTSP and pipeline

```bash
cd <deploy_dir>
bash scripts/verify_rtsp.sh <deploy_dir> <rtsp_url> [<rtsp_url> ...]
python3 scripts/check_service_health.py \
  --deploy-dir <deploy_dir> \
  --service video-analytics \
  --require-healthy \
  --max-attempts 24 \
  --interval 5
```

RTSP simulators (MediaMTX, `queuing-cams`) must run on a network reachable from
`<project>_scenescape`. Connect orphaned containers if needed:

```bash
NET=$(docker network ls --format '{{.Name}}' | grep '_scenescape$' | head -1)
docker network connect "$NET" <mediaserver-container> 2>/dev/null || true
```

### Common video-analytics failures

| Symptom                         | Fix                                                                                                                                |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `model file ... does not exist` | Re-run `python3 scripts/download_model.py <deploy_dir>` (drives the `intel/model-download` container's REST API), then `bash scripts/check_detection_models.sh`, then `docker compose up -d video-analytics`. Alternatively, from a full SceneScape repo checkout: `make -C model_download install-models COMPOSE_PROJECT_NAME=<name>`. |
| RTSP connection errors          | Fix URL or network; re-run `verify_rtsp.sh`                                                                                        |
| Segfault with dual pipelines    | See repo `queuing-config-gpu.json` / sample compose (GPU/WSL2) — template issue only                                               |

Filtered logs only:

```bash
docker compose logs video-analytics --tail 30 2>&1 \
  | grep -E 'ERROR|Autostarted|RUNNING|model file|Segmentation|MQTT'
```

## Step 9 — Calibration MQTT

Happy path: `capture_calibration_frames.py` (orchestrator step 9).

Manual TLS subscribe/publish templates: [command-templates.md](./command-templates.md).

Pass: JPEG on `scenescape/image/calibration/camera/<camera_id>` with keys `id`, `timestamp`,
`image`; base64 decodes to `FFD8FF … FFD9`.

## Step 10 — Mapping

```bash
python3 scripts/check_service_health.py \
  --deploy-dir <deploy_dir> \
  --service mapping \
  --require-healthy \
  --url https://localhost:8444/v1/health \
  --insecure \
  --expect-status healthy \
  --expect-bool model_loaded=true \
  --max-attempts 30 \
  --interval 10
docker compose logs mapping --tail 50
```

Permission errors on Hugging Face cache:

```bash
docker compose --profile mapping run --rm mapping-init
docker compose --profile mapping restart mapping
```
