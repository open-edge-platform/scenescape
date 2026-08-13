<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Verify End-to-End Object Tracking

Happy path: `scripts/verify_tracking.sh <deploy_dir> <scene_uid>` (orchestrator step 13).

```bash
bash scripts/verify_tracking.sh <deploy_dir> <scene_uid> 120
```

Pass: ≥1 object in the `objects` array on `scenescape/regulated/scene/<scene_uid>`
(published by the **analytics** service).

## Troubleshooting

### 1. Analytics / scene controller logs (filtered)

```bash
cd <deploy_dir>
docker compose logs analytics --tail 50 | grep -iE 'error|mqtt|scene|regul'
docker compose logs scene --tail 50 | grep -iE 'scene|camera|calibrat|error|mqtt'
```

Confirm analytics is Up: `docker compose ps analytics`. Without it, the regulated topic stays empty.
### 2. Cameras registered

Use manager API or UI; see [scene-and-cameras.md](./scene-and-cameras.md).

### 3. Non-zero camera pose

All-zero `translation` causes the controller to ignore the camera.

### 4. Scene scale

Zero scale blocks regulated output — set scale in UI or PATCH the scene.

### 5. Raw detections

Subscribe to `scenescape/data/camera/+` (TLS template in [command-templates.md](./command-templates.md)).
If empty: run `python3 scripts/check_service_health.py --deploy-dir <deploy_dir> --service video-analytics --require-healthy --max-attempts 24 --interval 5`.

### 6. Controller loaded scene

```bash
docker compose logs scene | grep -E 'NEW SCENE|Subscribed to scenescape/data/camera'
```
