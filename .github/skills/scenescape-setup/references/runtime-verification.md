<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Runtime Verification and Troubleshooting

Load only when Step 7, Step 9, or Step 13 fails in [SKILL.md](../SKILL.md).

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
| `PermissionError` on `tls_set` / `ROOT_CA` | Host CA was `0600` and `video-analytics` runs as UID 1999. Run `python3 <skill-dir>/scripts/ensure_secret_perms.py --deploy-dir <deploy_dir>` (public `.pem`/`.crt` → `0644`), then `docker compose up -d --force-recreate video-analytics`. Do **not** rely on Compose secret `mode:` — it is ignored. The orchestrator runs this automatically before Steps 7 and 9. |
| `REST_SERVER_PORT environment variable not set` | Harmless if REST is unused; the skill compose template sets `REST_SERVER_PORT=8080` to silence it. Re-bootstrap or add that env var and recreate `video-analytics`. |
| RTSP connection errors          | Fix URL or network; re-run `verify_rtsp.sh`. For file-backed `mediaserver` / `video-file-*` publishers, see [video-file-publishing.md](./video-file-publishing.md). |
| Segfault with dual pipelines    | See repo `queuing-config-gpu.json` / sample compose (GPU/WSL2) — template issue only                                               |

Filtered logs only:

```bash
docker compose logs video-analytics --tail 30 2>&1 \
  | grep -E 'ERROR|Autostarted|RUNNING|model file|Segmentation|MQTT'
```

## Step 9 — Calibration MQTT

Happy path: `capture_calibration_frames.py` (orchestrator step 9).

Before capture, the orchestrator runs `ensure_secret_perms.py` and checks that
`video-analytics` can read `ROOT_CA` (recreating the service if modes changed). If
calibration times out with empty `calibration-frames/`, check video-analytics logs for
`PermissionError` on `tls_set` (table above) and confirm pipelines autostarted.

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
