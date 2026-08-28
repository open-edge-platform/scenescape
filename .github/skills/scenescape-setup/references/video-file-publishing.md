<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Local video → RTSP publishing

Load this when diagnosing file-backed camera RTSP failures (Step 7 `verify_rtsp`, MediaMTX 404,
ffmpeg publisher crash/restart loops), or when changing how `docker-compose.override.yml` is
generated. For gathering `--video-files` / `--video-dir` inputs, use
[video-file-input.md](./video-file-input.md) instead.

## Role in the deploy

DL Streamer pipelines always consume RTSP H.264
(`rtph264depay ! h264parse ! avdec_h264` — see [pipeline-config.md](./pipeline-config.md)).
Local files are not a second pipeline path; they are published into the same RTSP contract as live
cameras:

```
host video file
  → linuxserver/ffmpeg (looped, realtime)
  → bluenviron/mediamtx (hostname alias: mediaserver)
  → rtsp://mediaserver:8554/<camera_id>
  → DL Streamer / verify_rtsp / proxy bypass
```

MediaMTX is the broker only. It matches SceneScape sample compose
(`sample_data/compose/docker-compose-dl-streamer-example.yml` `mediaserver` + `queuing-cams`). This skill
does not own MediaMTX configuration beyond the default image and the `mediaserver` network alias.

## What bootstrap writes

`bootstrap_deploy.py` → `generate_video_file_override()` writes
`<deploy_dir>/docker-compose.override.yml` when `deploy-inputs.json` has `source_type: "file"`:

| Compose service | Image | Purpose |
| --- | --- | --- |
| `mediaserver` | `bluenviron/mediamtx:1.18.1` | RTSP server; alias `mediaserver` on `scenescape` |
| `video-file-<camera_id>` | `linuxserver/ffmpeg:version-8.1-cli` | One publisher **per camera** |

`docker compose` auto-merges the override with `docker-compose.yml` (no extra `-f`).
`parallel_warmup.sh` starts `mediaserver` and every service matching `video-file-*` when the
override exists.

## Codec policy (probe → copy or re-encode)

Implemented by `probe_video_codec()` / `rtsp_video_encode_args()` in `bootstrap_deploy.py`:

| Probed video codec | ffmpeg publish args | Why |
| --- | --- | --- |
| `h264` / `avc` / `avc1` | `-c copy` | Same as sample `queuing-cams`; remux only, stable |
| Anything else / probe failed | `-c:v libx264 -preset veryfast -an` | Force H.264 for the DL Streamer pipeline |

Probe order: host `ffprobe` if present, else
`docker run --entrypoint /usr/local/bin/ffprobe` with `FFMPEG_IMAGE`.
Container format (`.mp4`, `.ts`, …) does **not** decide the path — only the bitstream codec does.

Per-camera publishers exist because a **single** ffmpeg process with multiple `libx264` outputs
tends to die against MediaMTX (`Broken pipe` / `Conversion failed!`), which drops RTSP paths and
makes sequential `verify_rtsp` fail on later cameras (404 / no stream).

## Publisher command shape

```text
-nostdin -re -stream_loop -1 -i /videos/<camera_id>.<ext>
  -map 0:v <copy|-c:v libx264 -preset veryfast -an>
  -f rtsp -rtsp_transport tcp rtsp://mediaserver:8554/<camera_id>
```

- `-re` — realtime pacing (live-camera-like)
- `-stream_loop -1` — infinite loop (no one-shot mode)
- Host file bind-mounted read-only to `/videos/<camera_id>.<ext>`

## Warmup and verify

```bash
# Started by parallel_warmup when override exists:
docker compose up -d mediaserver video-file-<id> [...]

# Gate (Step 7):
bash scripts/verify_rtsp.sh <deploy_dir> \
  rtsp://mediaserver:8554/<id> [...]
```

Focused logs (do not dump full compose logs):

```bash
docker compose logs --tail 40 mediaserver video-file-<camera_id>
docker compose ps mediaserver video-file-<camera_id>
```

Healthy MediaMTX lines look like: `path <camera_id> stream is available and online, 1 track (H264)`.

## Common failures

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `404` / `no stream is available on path '<id>'` | Publisher not running, crashed, or still starting | Check `video-file-<id>` status/logs; wait for online path; re-run `verify_rtsp` |
| `Conversion failed!` / muxer `Broken pipe` with multi-cam `libx264` in one service | Legacy single `video-file-cams` multi-output encode | Regenerate override (per-cam services); `docker compose up -d --remove-orphans` |
| Orphan `video-file-cams` fighting paths | Old override service left after rename | `docker compose up -d --remove-orphans` and remove the orphan container |
| H.264 file still re-encoding | Probe failed (no ffprobe/docker) | Ensure Docker can run `FFMPEG_IMAGE`; regenerate override |
| Non-H.264 file fails downstream decode | Re-encode not applied / wrong override | Confirm override command contains `libx264`; recreate publishers |
| RTSP OK intermittently then dies ~1 file duration | Unstable publisher (CPU / old dual-encode) | Prefer `-c copy` when H.264; keep one process per camera |

Network: publishers and consumers must share the compose `scenescape` network (project name
typically `*_scenescape`). See also [runtime-verification.md](./runtime-verification.md).

## Out of scope

- Custom `mediamtx.yml`, auth, HLS, WebRTC, or multi-host MediaMTX topology
- MJPEG / USB cameras (separate source-discovery work)
- Mixing live RTSP and file cameras in one deployment
- GPU / bidirectional transcoding (edit the override manually if needed)

Switching a deploy from files back to live RTSP requires `--fresh` or deleting
`docker-compose.override.yml` so bootstrap stops regenerating publishers from `video_paths`.
