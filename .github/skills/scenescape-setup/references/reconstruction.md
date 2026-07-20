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

## Supplementing with a walk-through video

If the user has a pre-recorded walk-through video of the space (recorded while walking through it
with a phone/camera), pass it with `--video-file` to add extra frames for reconstruction coverage
on top of the per-camera calibration frames:

```bash
python scripts/reconstruct_and_finalize.py \
    --deploy-dir <deploy_dir> \
    --frames-dir <deploy_dir>/calibration-frames \
    --cameras camera1 camera2 \
    --scene-name <scene_name> \
    --video-file <path-to-walkthrough.mp4>
```

Frames extracted from the video are not tied to a `camera_id`, so they only improve mesh geometry
coverage — camera auto-calibration still comes from the per-camera `--frames-dir` images as usual.
Accepted formats: `.mp4`, `.mov`, `.mkv`, `.webm`, `.avi`. The mapping service extracts keyframes
from the video automatically (no extra flags needed); a longer or higher-motion video takes more
processing time but is still bounded by the same finalize-mesh poll timeout (~15 minutes).

## 3. Confirm controller subscription

```bash
docker compose logs scene --tail 30 | grep -E 'NEW SCENE|Subscribed to scenescape/data/camera'
```

## Notes

- Defaults: `--mapping-url https://localhost:8444/v1`, `--manager-url https://localhost`
- Auth: `secrets/supass` (Django superuser)
- Finalize promptly after reconstruction (mapping cache is ephemeral)
