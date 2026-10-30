<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# TrackNet basketball fill

Spatiotemporal **TrackNet**-style heatmap on three consecutive frames fills
YOLO misses during fast bounces. Published boxes keep the **last YOLO ball
size** (square) so frustum Gaussian depth is not skewed by tracker stretch.

## Pipeline role

```text
gvadetect (person + basketball) → … → BGR
  → sscape_tracknet_ball  (fill if no basketball ROI)
  → sscape_post_inference_data_publish
```

## Build IR

```bash
# Labels demos with YOLO FT (OpenVINO GPU in DLStreamer image), trains, exports
bash sample_data/demo_scenes/Basketball/models/tracknet/train_and_export.sh
```

Outputs `../tracknet-basketball/{tracknet_basketball.xml,.bin,metadata.json}`.

## Deploy

Already wired in `basketball-config.json` + compose mount. Recreate:

```bash
make basketball-video-source-down && make basketball-video-source-up
```

## Notes

- Do not commit `dataset/` or training venvs.
- `max-miss` (default 12) caps how long TrackNet may bridge without YOLO.
- Raise `threshold` if false balls appear; lower if bounce gaps remain.
