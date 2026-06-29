<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Controller Tools

## pose_evaluation/

Offline tools for evaluating and debugging person pose adjustment without
running the full controller stack (no MQTT, REST, or Django required).

### pose_adjustment_debug.py

Applies person pose adjustment to a detection NDJSON file and writes
adjusted results in the same format.

```bash
PYTHONPATH=controller/src:scene_common/src python3 \
    controller/tools/pose_evaluation/pose_adjustment_debug.py \
    --input detections.json --output adjusted.json
```

| Flag | Default | Description |
|------|---------|-------------|
| `--input` | (required) | Input NDJSON file (DL Streamer detection format) |
| `--output` | (required) | Output NDJSON file with adjusted bounding boxes |
| `--scene-name` | `debug` | Scene name for proportion cache keying |
| `--camera-id` | `debug` | Camera ID for proportion cache keying |

### visualize_pose_adjustment.py

Overlays original and adjusted bounding boxes on video frames.

```bash
python3 controller/tools/pose_evaluation/visualize_pose_adjustment.py \
    --video sample_data/video.mp4 \
    --original detections.json \
    --adjusted adjusted.json \
    --output visualized.mp4
```

| Flag | Default | Description |
|------|---------|-------------|
| `--video` | (required) | Input video file |
| `--original` | (required) | Original detections NDJSON (before adjustment) |
| `--adjusted` | (required) | Adjusted detections NDJSON (after adjustment) |
| `--output` | `visualized.mp4` | Output annotated video path |

Color coding: **Red** = original bbox, **Green** = adjusted bbox, **Cyan** = keypoints.
Detections are matched to video frames using their `timestamp` field (nanoseconds from video start).

### compare_pose_adjustment.py

Computes quantitative metrics comparing occluded (no adjustment), baseline
(no occlusion ground truth), and adjusted detections. Produces summary
statistics and plots.

```bash
python3 controller/tools/pose_evaluation/compare_pose_adjustment.py \
    --occluded detections.json \
    --baseline no_occlusion_detections.json \
    --adjusted adjusted.json \
    --output-dir comparison_results
```

| Flag | Default | Description |
|------|---------|-------------|
| `--occluded` | (required) | Detections with occlusion (no adjustment) |
| `--baseline` | (required) | Detections without occlusion (ground truth) |
| `--adjusted` | (required) | Detections after pose adjustment |
| `--output-dir` | `comparison_results` | Directory for output plots |

Output plots:
- `height_over_time.png` — bbox height across all three datasets
- `height_error.png` — error relative to baseline over time
- `error_distribution.png` — histogram of height errors
- `bottom_over_time.png` — bbox bottom edge (foot position)

### Input Format

All tools use NDJSON (one JSON object per line) in DL Streamer detection format:

```json
{"objects": [{"detection": {"bounding_box": {"x_min": ..., "x_max": ..., "y_min": ..., "y_max": ...}, "label": "person"}, "x": 100, "y": 50, "w": 200, "h": 400, "id": 1, "keypoints": [{"points": [{"index": 0, "x": 150, "y": 70, "confidence": 0.9}, ...], "semantic_tag": "Model0/body-pose/coco-17"}]}], "resolution": {"width": 1280, "height": 720}, "timestamp": 1700000000}
```

### Workflow

1. Generate detections (requires Docker + DL Streamer image + models):
   ```bash
   ./controller/tools/pose_evaluation/generate_detections.sh
   ```
2. Apply pose adjustment:
   ```bash
   PYTHONPATH=controller/src:scene_common/src python3 \
     controller/tools/pose_evaluation/pose_adjustment_debug.py \
     --input detections.json --output adjusted.json
   ```
3. Visualize:
   ```bash
   python3 controller/tools/pose_evaluation/visualize_pose_adjustment.py \
     --video sample_data/qcam2_occlusion_improved_less_occlusion_short.mp4 \
     --original detections.json --adjusted adjusted.json
   ```
4. Quantify (requires baseline without occlusion):
   ```bash
   python3 controller/tools/pose_evaluation/compare_pose_adjustment.py \
     --occluded detections.json --baseline no_occlusion_detections.json \
     --adjusted adjusted.json
   ```

### generate_detections.sh

Runs DL Streamer inference pipelines via Docker to produce detection
NDJSON files for both occluded and baseline (no occlusion) videos.

Prerequisites:
- `docker` installed and `intel/dlstreamer:latest` image pulled
- Models in `my_models/models/public/` (yolo11m-pose, mars-small128)
- Sample videos in `sample_data/` (qcam2_short.mp4, qcam2_occlusion_improved_less_occlusion_short.mp4)

```bash
./controller/tools/pose_evaluation/generate_detections.sh
```

Produces:
- `detections.json` — occluded video detections
- `no_occlusion_detections.json` — baseline detections (no occlusion)
- `occluded_output.mp4` / `no_occlusion_output.mp4` — annotated videos
