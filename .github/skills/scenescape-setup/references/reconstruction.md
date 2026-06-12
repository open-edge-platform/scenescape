# 3D Reconstruction: Capture Frames and Finalize Scene

Scripts are in [`scripts/`](../scripts/). The orchestrator runs these in steps 9 and 11–12.

## 1. Capture calibration frames

```bash
python scripts/capture_calibration_frames.py \
    --deploy-dir <deploy_dir> \
    --cameras camera1 camera2 \
    --out-dir <deploy_dir>/calibration-frames
```

## 2. Reconstruct and finalize

```bash
python scripts/reconstruct_and_finalize.py \
    --deploy-dir <deploy_dir> \
    --frames-dir <deploy_dir>/calibration-frames \
    --cameras camera1 camera2 \
    --scene-name <scene_name>
```

Or `--scene-uid <uid>` for an existing scene.

## 3. Confirm controller subscription

```bash
docker compose logs scene --tail 30 | grep -E 'NEW SCENE|Subscribed to scenescape/data/camera'
```

## Notes

- Defaults: `--mapping-url https://localhost:8444/v1`, `--manager-url https://localhost`
- Auth: `secrets/supass` (Django superuser)
- Finalize promptly after reconstruction (mapping cache is ephemeral)
