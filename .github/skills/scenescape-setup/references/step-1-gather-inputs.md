<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Step 1 — Gather inputs (required)

Read for every **new** deployment before writing `deploy-inputs.json`. (Fast Path skips this
when inputs are unchanged — see [fast-path.md](./fast-path.md).)

Ask the user for every new deployment:

| Input        | Rules                                                                                                |
| ------------ | ---------------------------------------------------------------------------------------------------- |
| `deploy_dir` | Writable directory for generated files                                                               |
| `streams`    | One RTSP/RTSPS URL per camera, user-provided, in order — **or** local video files/folder (see below) |
| `camera_ids` | Unique IDs (no `/`), same order as `streams`                                                         |
| `scene_name` | Human-readable scene name chosen by the user                                                         |
| `mapping`    | Scene map source: `reconstruction` (default), floor blueprint, `.glb`/`.ply` mesh, or geospatial     |
| `glb_file`   | Required if `mapping` is pre-made GLB mesh; not needed for default auto-reconstruction               |
| `camera_json`| Required for automated setup with pre-made GLB mesh; omit to use manual Web UI camera calibration     |

Validate: `len(streams) == len(camera_ids)`, ≥1 camera, `camera_ids` are unique (no duplicates,
no `/`), valid RTSP URLs. State explicitly in your response that this uniqueness check was
performed before writing `deploy-inputs.json` — `deploy_inputs.py` also re-validates it, but
call it out for the user.

## `mapping` choices

- **`reconstruction` (default / no answer)**: proceed as documented below — the orchestrator's
  steps 9 and 11–13 capture calibration frames, auto-generate the map, and auto-calibrate camera
  poses. If the user also has a pre-recorded walk-through video of the space, it can be included
  at step 11–12 for extra reconstruction coverage (camera auto-calibration is unaffected) — see
  [reconstruction.md](./reconstruction.md#supplementing-with-a-walk-through-video).
- **Blueprint image, GLB/PLY mesh, or geospatial map**: this skips automatic camera-pose
  estimation, so the user must calibrate cameras **manually** via the web UI afterward — unless
  a pre-calibrated `camera_json` file is supplied along with `glb_file`. Confirm if manual
  calibration is accepted or if `camera_json` is provided, then follow
  [scene-map-alternatives.md](./scene-map-alternatives.md), which covers running only
  `--phase bootstrap`/`--phase calibrate`, computing pixels-per-meter for a blueprint, creating
  the scene via REST, and registering cameras (automatically if `camera_json` is present or
  manually via Web UI).

## Persist before automation

Use `python3` by default. Do not substitute a virtualenv interpreter path unless you have
confirmed that path exists on disk.

```bash
python3 <skill-dir>/scripts/deploy_inputs.py write \
  --deploy-dir <deploy_dir> \
  --scene-name <scene_name> \
  --camera-ids <id> [<id> ...] \
  --streams <rtsp_url> [<rtsp_url> ...] \
  --mapping <reconstruction|blueprint|glb|geospatial> \
  [--glb-file <path_to_glb>] \
  [--camera-json <path_to_camera_json>] \
  --skill-dir <skill-dir>
```

Writes `<deploy_dir>/deploy-inputs.json` — the source of truth for all later steps. Pipeline
adaptation reads RTSP URLs from the downloaded template entry per camera; it does not hardcode
simulator hostnames or camera names.

**No live RTSP cameras available?** If the user instead has a folder of recorded video files, or
an explicit list of video file paths, use `--video-dir`/`--video-files` in place of `--streams` —
see [video-file-input.md](./video-file-input.md). This covers local file playback only; MJPEG and
USB camera input are out of scope pending a separate source-discovery service. File →
MediaMTX/RTSP publishing (codec probe, publishers, Step 7 diagnosis) is
[video-file-publishing.md](./video-file-publishing.md) — load it on file-backed RTSP failures,
not during routine Step 1.
