# Local video file input

Scope: local video file playback only — a single video file, a folder of recordings, or an
explicit list of file paths. **Not covered**: MJPEG and USB camera input; a separate
source-discovery service is planned to cover those, so this skill does not attempt them.

## How it works

DL Streamer Pipeline Server's generated pipelines (`pipeline-config.md`) always consume an RTSP
URL. Rather than adding a second, parallel pipeline-generation path, local video files are looped
through a small internal RTSP re-streamer so every later step (pipeline adaptation, RTSP
reachability check, proxy bypass) is unchanged from the live-camera path:

```
video file(s) --[ffmpeg, looped]--> mediamtx (rtsp://mediaserver:8554/<camera_id>) --> DL Streamer
```

`deploy_inputs.py` synthesizes `rtsp://mediaserver:8554/<camera_id>` as each file-backed camera's
`stream` and records the real host file path separately (`source_type: "file"`, `video_paths`).
`bootstrap_deploy.py` then writes `<deploy_dir>/docker-compose.override.yml` with:

- `mediaserver` — `bluenviron/mediamtx`, the same image/hostname the real `docker-compose.yml`
  uses for its own sample-data demo streams.
- `video-file-cams` — one `linuxserver/ffmpeg` process that loops (`-stream_loop -1 -re`) every
  configured file and transcodes it to H.264 over RTSP (`rtsp://mediaserver:8554/<camera_id>`),
  matching what the hand-authored pipeline in `pipeline-config.md` expects.

`docker compose` auto-merges `docker-compose.override.yml` with `docker-compose.yml` by default
(no `-f` flag needed), so `deploy_scenescape.sh`, `parallel_warmup.sh`, and `verify_rtsp.sh` all
work unmodified — `parallel_warmup.sh` just also starts `mediaserver`/`video-file-cams` early when
it detects the override file exists.

## Gathering inputs

Use exactly one of `--streams` (live RTSP), `--video-dir` (folder), or `--video-files` (explicit
list) — mixing local files with live RTSP cameras in the same deployment isn't supported.

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

- Every file is transcoded to H.264 (`libx264`, `veryfast` preset) so arbitrary source codecs work
  with the existing `rtph264depay ! h264parse ! avdec_h264` pipeline — this costs CPU per camera;
  a large folder of recordings means a correspondingly busy `video-file-cams` container.
  Bidirectional or GPU transcoding is not configured; add it manually in
  `docker-compose.override.yml` if throughput becomes a problem.
- Playback loops indefinitely (`-stream_loop -1`), matching how a live camera never "ends" —
  there is no finite-playback/one-shot mode.
- `--fresh` (or manually deleting `docker-compose.override.yml`) is required to switch a
  deployment from file-based back to live RTSP cameras, since the override file is only
  regenerated (or removed) by `bootstrap_deploy.py` reading the current `deploy-inputs.json`.
