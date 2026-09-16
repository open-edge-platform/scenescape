<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Local video file input

Scope: gathering local video file playback inputs — a single video file, a folder of recordings,
or an explicit list of file paths. **Not covered**: MJPEG and USB camera input; a separate
source-discovery service is planned to cover those, so this skill does not attempt them.

Publishing those files into MediaMTX/RTSP (codec probe, `-c copy` vs `libx264`, per-camera
ffmpeg services, warmup/verify, publisher troubleshooting) lives in
[video-file-publishing.md](./video-file-publishing.md). Load that reference for Step 7 file-backed
RTSP failures or override generation changes; keep this file for Step 1 input gathering.

## How it works (summary)

DL Streamer Pipeline Server's generated pipelines (`pipeline-config.md`) always consume an RTSP
URL. Local video files are looped through an internal RTSP re-streamer so every later step
(pipeline adaptation, RTSP reachability check, proxy bypass) is unchanged from the live-camera
path:

```
video file(s) --[ffmpeg, looped]--> mediamtx (rtsp://mediaserver:8554/<camera_id>) --> DL Streamer
```

`deploy_inputs.py` synthesizes `rtsp://mediaserver:8554/<camera_id>` as each file-backed camera's
`stream` and records the real host file path separately (`source_type: "file"`, `video_paths`).
`bootstrap_deploy.py` then writes `<deploy_dir>/docker-compose.override.yml` — details in
[video-file-publishing.md](./video-file-publishing.md).

## Gathering inputs

Use exactly one of `--streams` (live RTSP), `--video-dir` (folder), or `--video-files` (explicit
list) — mixing local files with live RTSP cameras in the same deployment isn't supported.

**Video given as a remote URL (e.g. a GitHub link) instead of a local path**: `--video-files`
requires real local paths that exist on disk, so download each one first. GitHub `blob` URLs are
HTML pages, not the raw file — convert `github.com/<org>/<repo>/blob/<ref>/<path>` to
`raw.githubusercontent.com/<org>/<repo>/<ref>/<path>` before downloading:

```bash
mkdir -p <deploy_dir>/videos
curl -L -o <deploy_dir>/videos/<camera_id>.mp4   https://raw.githubusercontent.com/<org>/<repo>/<ref>/<path-to-file>
```

Do this — and show the exact command(s) you used/would use — for every camera before calling
`deploy_inputs.py write --video-files`; never pass a `blob` URL or any other remote URL directly
to `--video-files`.

**A folder of recordings** (`camera_ids` auto-derived from filenames, sorted):

```bash
python3 <skill-dir>/scripts/deploy_inputs.py write \
  --deploy-dir <deploy_dir> \
  --scene-name <scene_name> \
  --video-dir /path/to/recordings \
  --skill-dir <skill-dir>
```

**An explicit list of files** (optionally pair with `--camera-ids` in the same order; otherwise
also auto-derived):

```bash
python3 <skill-dir>/scripts/deploy_inputs.py write \
  --deploy-dir <deploy_dir> \
  --scene-name <scene_name> \
  --camera-ids <id> [<id> ...] \
  --video-files /path/to/cam1.mp4 [/path/to/cam2.mp4 ...] \
  --skill-dir <skill-dir>
```

Supported extensions: `.mp4`, `.mkv`, `.avi`, `.mov`, `.ts`, `.webm`, `.mpg`, `.mpeg`, `.m4v`.

Then read back the synthesized `camera_ids`/`streams` and pass those to the orchestrator (it only
accepts `--streams`/`--camera-ids`, not `--video-dir`/`--video-files`, since Step 1 already
persisted the file metadata):

```bash
python3 <skill-dir>/scripts/deploy_inputs.py read --deploy-dir <deploy_dir>
# {"scene_name": "...", "camera_ids": [...], "streams": ["rtsp://mediaserver:8554/...", ...], ...}

bash <skill-dir>/scripts/deploy_scenescape.sh \
  --deploy-dir <deploy_dir> --skill-dir <skill-dir> \
  --scene-name <scene_name> \
  --camera-ids <ids from the read-back JSON> \
  --streams <streams from the read-back JSON>
```

## Notes / limitations

- Codec/publish behavior: [video-file-publishing.md](./video-file-publishing.md).
- Playback loops indefinitely (`-stream_loop -1`), matching how a live camera never "ends" —
  there is no finite-playback/one-shot mode.
- `--fresh` (or manually deleting `docker-compose.override.yml`) is required to switch a
  deployment from file-based back to live RTSP cameras, since the override file is only
  regenerated (or removed) by `bootstrap_deploy.py` reading the current `deploy-inputs.json`.
