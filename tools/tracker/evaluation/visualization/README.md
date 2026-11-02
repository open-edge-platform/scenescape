<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Scenario Visualization

Plots and short videos of tracker runs, to spot filter overshoot, jitter, and covariance or model-probability problems,
plus TrackEval metrics (HOTA, MOTA, IDF1).
The input is a robot-vision unit-test recording or an evaluation pipeline run.

## Guide

Run all commands from `tools/tracker/evaluation`.

1. Set up once: the `.venv` from [Installation](../README.md#installation), activated, and `ffmpeg` for MP4 videos
   (`sudo apt install ffmpeg`, or render GIFs with `--gif`).

2. Get a scenario directory `S` from either source.

   **Robot-vision tests**: record scenarios as described in [Test scenario recordings](../../../../controller/src/robot_vision/README.md#test-scenario-recordings),
   then pick one:

   ```bash
   S=/tmp/rv-scenarios/MotionScenarioTest.TracksMotionCases/sudden_stop
   ```

   **Evaluation pipeline**, with the Docker images from [Black-Box Evaluation Suite](../README.md#black-box-evaluation-suite).
   Any run directory works, also the ones `run_black_box_evaluation` writes:

   ```bash
   python -m pipeline_engine pipeline_configs/black_box_unity/black_box_tracker_service.yaml
   S=$(ls -d output/black-box-evaluation/*_Tracker-Service | tail -1)
   ```

3. Plot: one PNG per plot in `$S/plots/`, and TrackEval's files in `$S/metrics/`. With several directories, e.g.
   `$(dirname $S)/*`, `trackeval_comparison.png` in their common parent's `plots/` compares them.

   ```bash
   python visualization/plot_scenario.py $S
   ```

4. Render: `$S/videos/overview.mp4`, and `zoom_1.mp4` following ground-truth object `1` (`--zoom` also takes a track
   id).

   ```bash
   python visualization/render_video.py $S --zoom 1
   ```

## Reference

### Plots

| Plot                | Content                                                                                            |
| ------------------- | -------------------------------------------------------------------------------------------------- |
| `trajectory`        | Top-down view: ground truth, detections and tracks                                                 |
| `position_error`    | Total, along-track and cross-track error against the matched ground truth, ±2σ from P              |
| `speed_yaw`         | Speed, yaw and yaw rate: estimate vs truth and orienting detections                                |
| `altitude`          | z and vz of truth, detections and estimate; only for recordings with vertical motion               |
| `size`              | Length, width and height: estimate vs truth vs detections                                          |
| `model_probability` | Motion model probabilities per track                                                               |
| `std_dev`           | √diag P: position (x, y, z), velocity (vx, vy, vz), yaw, yaw rate and size (log scale)             |
| `trackeval`         | [TrackEval](../evaluators/README.md#trackevalevaluator) HOTA, DetA, AssA, LocA and TP/FN/FP over d |

Along-track and cross-track values are projected onto the ground truth's direction of motion; cross-track is positive
to the left. d is the position error TrackEval accepts at each similarity threshold α, d = 2 m · (1 − α); the
comparison shows HOTA and LocA over d and HOTA, MOTA, IDF1 and LocA per directory; its score axis extends below zero
for a negative MOTA. Plots without data, e.g. the estimator plots for pipeline runs, are skipped; a TrackEval failure
only skips the TrackEval plots, with a warning.

### Videos

- `overview`: the whole scene, ground-truth boxes (black, dashed) and track boxes with heading and trail. Objects
  without a size are points. For recordings with vertical motion it also shows two side views under the top-down view:
  the x–z view (looking along y) and the y–z view (looking along x). Each body is drawn as the extent of its box along
  that axis by its height, centred on z, with a z trail and a line at z = 0, so the difference between truth and track
  can be read in all three planes. The horizontal axes have the scale of the top-down view and the vertical axis is
  scaled to the heights, so the side views are not to scale. Planar recordings keep the top-down view only.
- `zoom_<ID>`: follows one object and adds the track's predicted position, an ellipse around it and its velocity arrow
  (1 s of motion). For tracker-level recordings (`AssociationScenarioTest`) the ellipse is the track's association
  gate: the χ² ellipse of the XY block of the predicted measurement covariance S (most probable model) for
  `position_mahalanobis`, without the `max_radius_m` ceiling, or a circle of `max_radius_m` for `euclidean`. Otherwise
  it is the 99% confidence ellipse of S.
- `zoom_<ID>_xz`, `zoom_<ID>_yz` (with `--zoom-side`): the x–z and y–z side views following the same object, one
  video per axis. Same box-by-height drawing as the overview side views, but true to scale (equal axes, window as in
  `--zoom-size`), centred on the object's (x or y, z), with all bodies' z trails and a line at z = 0. No gate ellipse
  or velocity arrow. An object without a z keeps the previous view.

### Options

| Option          | Tool  | Description                                                                                      |
| --------------- | ----- | ------------------------------------------------------------------------------------------------ |
| `--output DIR`  | both  | Output directory, default `$S/plots` or `$S/videos`; one directory only                          |
| `--fps N`       | both  | Frame rate for pairing tracks with ground truth and for TrackEval, default the ground-truth rate |
| `--plots A,B`   | plot  | Subset of the plots                                                                              |
| `--zoom ID`     | video | Ground-truth object id or track id to follow; repeatable                                         |
| `--speed F`     | video | Playback speed, default 1 (real time); at most 30 video frames per second                        |
| `--trail S`     | video | Trail length in seconds, default 2                                                               |
| `--zoom-size M` | video | Zoom window width in metres, default 4× the object's largest dimension, at least 4               |
| `--side-views M`| video | x–z and y–z views under the overview: `auto` (default, only with vertical motion), `always`, `never` |
| `--zoom-side`   | video | With `--zoom`, also write `zoom_<ID>_xz` and `zoom_<ID>_yz`, the side views following the object  |
| `--gif`         | video | GIF instead of MP4                                                                               |

### Input files

| Recorder file       | Pipeline run file            | Content                                                                                                                                         |
| ------------------- | ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `groundtruth.jsonl` | `dataset/ground_truth.jsonl` | [Ground truth](../README.md#ground-truth-format-canonical-jsonl); the recorder adds size, heading, velocity, etc.                               |
| `detections.jsonl`  | `harness/inputs.jsonl`       | [Input detections](../README.md#input-detection-format); only 3D detections are shown, in recordings only                                       |
| `tracks.jsonl`      | `harness/outputs.jsonl`      | [Tracker output](../README.md#tracker-output-format)                                                                                            |
| `estimator.jsonl`   | –                            | Per track a `config` line (with `association` for tracker-level runs), then per step model probabilities, state, P, predicted measurement and S |

Any file may be missing. Tracks are paired with ground-truth objects by position with `match_tracks()` from
[utils/tracks.py](../utils/tracks.py), so their ids may differ; frames count from the first track or ground-truth
sample, as in the evaluators. Recorder timestamps start at the `system_clock` epoch; the tools show seconds since the
first timestamp.

Detections are drawn only for recordings: the recorder writes them in scene coordinates (identity sensor pose) with the
ground-truth object id as detection id. A pipeline run's detections follow the camera-data schema, with frame-local ids
and positions in the sensor frame, so they are loaded (`Scenario.detections`, `detections_in_scene` is false) but not
drawn.

## Comparing two sets of recordings

To check whether a change, e.g. adding the z axis to the filter, altered the tracking accuracy, record the robot-vision
scenarios with both builds, each into its own directory (see
[Test scenario recordings](../../../../controller/src/robot_vision/README.md#test-scenario-recordings)), and compare
the two roots:

```bash
python visualization/compare_scenarios.py $BEFORE $AFTER [--warm-up S] [--fps N] [--rel-tol 0.05] [--abs-tol 0.01] \
  [--metrics A,B] [--fail-on-worse]
```

A scenario is a directory below a root that holds `groundtruth.jsonl`, named by its path relative to the root, e.g.
`MotionScenarioTest.TracksMotionCases/turn`. Scenarios present in both roots are compared, one table each; those present
in only one root, e.g. new tests, are listed after the tables. The last line counts the compared scenarios, the metric
values marked `WORSE` (and in how many scenarios) and those marked `better`.

Tracks are paired with ground truth as for the plots; rows before `--warm-up` seconds (default 2) and rows without
ground truth are ignored, so a recording shorter than that needs `--warm-up 0`; its metrics are `nan` otherwise, which
the table points out.

| Metric              | Content                                                                        |
| ------------------- | ------------------------------------------------------------------------------ |
| `horizontal_rms`    | RMS of the x/y position error [m]                                              |
| `horizontal_max`    | Largest x/y position error [m]                                                 |
| `vertical_rms`      | RMS of the z error [m]                                                         |
| `vertical_max`      | Largest z error [m]                                                            |
| `final_speed_error` | Horizontal speed error at the last row of each pair, mean over the pairs [m/s] |
| `final_vz_error`    | Vertical speed error at the last row of each pair, mean over the pairs [m/s]   |

All metrics are errors, so lower is better. `delta` is `after` − `before`. A value is marked `WORSE` when
`after > before · (1 + rel_tol) + abs_tol` and `better` when `after < before · (1 − rel_tol) − abs_tol`; the defaults
absorb noise from a few percent or a centimetre. A value that was computed before but is `nan` after (the track or the
ground truth is gone) is also `WORSE`; `nan` before is not judged. With `--fail-on-worse` the exit code is 1 if any
value is `WORSE`, for scripts. An empty common set of scenarios or a missing root is an error.

Only `groundtruth.jsonl` and `tracks.jsonl` are read, never `estimator.jsonl`, so recordings of builds with different
filter state sizes, e.g. 12 and 13 states, compare directly.

## Tests

```bash
pytest visualization -v
```

- [tests/fixtures/target_born_moving](tests/fixtures/target_born_moving): a recording, regenerated as in
  [Test scenario recordings](../../../../controller/src/robot_vision/README.md#test-scenario-recordings) with `--gtest_filter=MotionScenarioTest.TargetBornMovingAcquiresSpeed`.
  Its `detections.jsonl` and `tracks.jsonl` are validated against `tracker/schema/camera-data.schema.json` and
  `tracker/schema/scene-data.schema.json`.
