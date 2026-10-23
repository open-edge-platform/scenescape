<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Scenario Visualization

Plots and short videos of tracker runs, to spot filter overshoot, jitter, and covariance or model-probability problems.
The input is a robot-vision unit-test recording or an evaluation pipeline run.

## Guide

Run all commands from `tools/tracker/evaluation`.

1. Set up once: the `.venv` from [Installation](../README.md#installation), activated, and `ffmpeg` for MP4 videos
   (`sudo apt install ffmpeg`, or render GIFs with `--gif`).

2. Get a scenario directory `S` from either source.

   **Robot-vision tests**, with the build dependencies from
   [controller/src/robot_vision/README.md](../../../../controller/src/robot_vision/README.md). Tests that use
   `ScenarioRecorder` write `$RV_SCENARIO_DIR/<Suite>.<Test>/[<case>/]` when the variable is set:

   ```bash
   RV=../../../controller/src/robot_vision
   cmake -S $RV -B $RV/build -DBUILD_TESTING=ON -DBUILD_PYTHON_BINDINGS=OFF -DCMAKE_BUILD_TYPE=Release
   cmake --build $RV/build -j$(nproc)
   RV_SCENARIO_DIR=/tmp/rv-scenarios $RV/build/test/RobotVisionTests --gtest_filter='MotionScenarioTest.*'
   S=/tmp/rv-scenarios/MotionScenarioTest.TracksMotionCases/sudden_stop
   ```

   **Evaluation pipeline**, with the Docker images from [Black-Box Evaluation Suite](../README.md#black-box-evaluation-suite).
   Any run directory works, also the ones `run_black_box_evaluation` writes:

   ```bash
   python -m pipeline_engine pipeline_configs/black_box_unity/black_box_tracker_service.yaml
   S=$(ls -d output/black-box-evaluation/*_Tracker-Service | tail -1)
   ```

3. Plot: one PNG per plot in `$S/plots/`.

   ```bash
   python visualization/plot_scenario.py $S
   ```

4. Render: `$S/videos/overview.mp4`, and `zoom_1.mp4` following ground-truth object `1` (`--zoom` also takes a track
   id).

   ```bash
   python visualization/render_video.py $S --zoom 1
   ```

## Recording another test

Give the recorder the ground truth and pass it to the `FilterRun`, which then records every detection and estimate.
The recorder writes nothing unless `RV_SCENARIO_DIR` is set.

```cpp
#include "support/ScenarioRecorder.hpp"

ScenarioRecorder recorder("turn");  // optional case name
recorder.truth(truth);              // object id 1, category from the truth Box (kCar, kPerson)
FilterRun run(productionConfig(), &recorder);
run.feed(observe(truth, camera));   // detections go under the Sensor id, "camera" unless Sensor{.id = ...}
run.coast(1.0);
```

For several objects, pass the same id to `truth()` and as the third `FilterRun` argument.

## Reference

### Plots

| Plot                | Content                                                                               |
| ------------------- | ------------------------------------------------------------------------------------- |
| `trajectory`        | Top-down view: ground truth, detections and tracks                                    |
| `position_error`    | Total, along-track and cross-track error against the matched ground truth, ±2σ from P |
| `speed_yaw`         | Speed, yaw and yaw rate: estimate vs truth and orienting detections                   |
| `size`              | Length, width and height: estimate vs truth vs detections                             |
| `model_probability` | Motion model probabilities per track                                                  |
| `std_dev`           | √diag P: position, velocity, yaw, yaw rate and size (log scale)                       |

Along-track and cross-track values are projected onto the ground truth's direction of motion; cross-track is positive
to the left. Plots without data, e.g. the estimator plots for pipeline runs, are skipped.

### Videos

- `overview`: the whole scene, ground-truth boxes (black, dashed) and track boxes with heading and trail. Objects
  without a size are points.
- `zoom_<ID>`: follows one object and adds the track's predicted position, its χ² gate ellipse (p = 0.99, as in
  production association) from the predicted measurement covariance S, and its velocity arrow (1 s of motion).

### Options

| Option          | Tool  | Description                                                                        |
| --------------- | ----- | ---------------------------------------------------------------------------------- |
| `--output DIR`  | both  | Output directory, default `$S/plots` or `$S/videos`                                |
| `--fps N`       | both  | Frame rate for pairing tracks with ground truth, default the ground-truth rate     |
| `--plots A,B`   | plot  | Subset of the plots                                                                |
| `--zoom ID`     | video | Ground-truth object id or track id to follow; repeatable                           |
| `--speed F`     | video | Playback speed, default 1 (real time); at most 30 video frames per second          |
| `--trail S`     | video | Trail length in seconds, default 2                                                 |
| `--zoom-size M` | video | Zoom window width in metres, default 4× the object's largest dimension, at least 4 |
| `--gif`         | video | GIF instead of MP4                                                                 |

### Input files

| Recorder file       | Pipeline run file            | Content                                                                                                           |
| ------------------- | ---------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `groundtruth.jsonl` | `dataset/ground_truth.jsonl` | [Ground truth](../README.md#ground-truth-format-canonical-jsonl); the recorder adds size, heading, velocity, etc. |
| `detections.jsonl`  | `harness/inputs.jsonl`       | [Input detections](../README.md#input-detection-format); only 3D detections are shown                             |
| `tracks.jsonl`      | `harness/outputs.jsonl`      | [Tracker output](../README.md#tracker-output-format)                                                              |
| `estimator.jsonl`   | –                            | Per track a `config` line, then per filter step model probabilities, state, P, predicted measurement and S        |

Any file may be missing. Tracks are paired with ground-truth objects by position with `match_tracks()` from
[utils/tracks.py](../utils/tracks.py), so their ids may differ. Recorder timestamps start at the `system_clock` epoch;
the tools show seconds since the first timestamp.

## Tests

```bash
pytest visualization -v
```

- [tests/fixtures/target_born_moving](tests/fixtures/target_born_moving): a recording, regenerated with guide step 2 and
  `--gtest_filter=MotionScenarioTest.TargetBornMovingAcquiresSpeed`.
- [tests/schema/camera-data.schema.json](tests/schema/camera-data.schema.json): copy of
  `tracker/schema/camera-data.schema.json` with 3D detections from branch `ITEP-97104_tracker_3d_detections`; replace it
  with the tracker schema once that is merged.
