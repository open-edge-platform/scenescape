<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Scenario Visualization

Plots and short videos of the motion scenarios recorded by the robot-vision unit tests, to spot filter overshoot,
jitter, and covariance or model-probability problems at a glance. The same tools also work on real tracker output from
the evaluation pipeline.

Fixes are diagnosed and verified in unit tests; these tools are for looking at the results.

## Workflow

1. Record scenarios from the robot-vision unit tests.
2. Plot a scenario directory: `plot_scenario.py`.
3. Render videos of it: `render_video.py`.

### 1. Record scenarios

Tests in [controller/src/robot_vision/test](../../../../controller/src/robot_vision/test) record their runs with
`ScenarioRecorder` ([support/ScenarioRecorder.hpp](../../../../controller/src/robot_vision/test/support/ScenarioRecorder.hpp))
when the `RV_SCENARIO_DIR` environment variable is set; without it they write nothing. `MotionScenarioTests.cpp`
records all its scenarios.

```bash
# Tracker build (as in CI)
RV_SCENARIO_DIR=/tmp/rv-scenarios make -C tracker test-robot-vision

# or a local robot_vision build, filtered
cd controller/src/robot_vision
cmake -S . -B build -DBUILD_TESTING=ON -DBUILD_PYTHON_BINDINGS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
RV_SCENARIO_DIR=/tmp/rv-scenarios ./build/test/RobotVisionTests --gtest_filter='MotionScenarioTest.*'
```

Each run writes `$RV_SCENARIO_DIR/<Suite>.<Test>/[<case>/]` and overwrites earlier files. To record another test, wrap
its truth, detections and filter run:

```cpp
#include "support/ScenarioRecorder.hpp"

ScenarioRecorder recorder("turn");   // case name, optional; no-op unless RV_SCENARIO_DIR is set
recorder.truth(truth);               // object id 1; category from the truth Box (kCar, kPerson)
FilterRun run(productionConfig(), &recorder);
run.feed(recorder.detections(observe(truth, camera), "camera"));
run.coast(1.0);                      // coasts are recorded too
```

For several objects, pass the object id to `truth()` and `detections()`, and the track id to `FilterRun`.

### 2. Plot

From `tools/tracker/evaluation`, with its `.venv` (see [Installation](../README.md#installation)):

```bash
python visualization/plot_scenario.py /tmp/rv-scenarios/MotionScenarioTest.TracksMotionCases/turn
```

| Option         | Description                                                                    |
| -------------- | ------------------------------------------------------------------------------ |
| `--output DIR` | Output directory, default `<scenario dir>/plots`                               |
| `--plots A,B`  | Subset of the plots below                                                      |
| `--fps N`      | Frame rate for pairing tracks with ground truth, default the ground-truth rate |

One PNG per plot, with one colour per track:

| Plot                | Content                                                                                                     |
| ------------------- | ----------------------------------------------------------------------------------------------------------- |
| `trajectory`        | Top-down view: ground truth, detections and tracks                                                          |
| `position_error`    | Total, along-track and cross-track error against the matched ground truth, with ±2σ from the covariance `P` |
| `speed_yaw`         | Speed, yaw and yaw rate: estimate vs truth, detection yaw from orienting sensors                            |
| `size`              | Length, width and height: estimate vs truth vs detections                                                   |
| `model_probability` | Motion model probabilities per track                                                                        |
| `std_dev`           | Standard deviations √diag `P`: position, velocity, yaw, yaw rate and size (log scale)                       |

The along-track and cross-track errors and their σ are the error and the 2×2 position block of `P` projected onto the
direction of motion of the ground truth; cross-track is positive to the left. Plots without data are skipped, e.g.
`model_probability` and `std_dev` for real tracker output.

### 3. Render videos

```bash
python visualization/render_video.py /tmp/rv-scenarios/MotionScenarioTest.TracksMotionCases/sudden_stop --zoom 1
```

| Option          | Description                                                                        |
| --------------- | ---------------------------------------------------------------------------------- |
| `--zoom ID`     | Ground-truth object id or track id to follow; repeatable, one video each           |
| `--speed F`     | Playback speed relative to real time, default 1; the video has at most 30 fps      |
| `--trail S`     | Trail length in seconds, default 2                                                 |
| `--zoom-size M` | Zoom window width in metres, default 4× the object's largest dimension, at least 4 |
| `--gif`         | GIF instead of MP4 (no `ffmpeg` needed)                                            |
| `--output DIR`  | Output directory, default `<scenario dir>/videos`                                  |
| `--fps N`       | Frame rate for pairing tracks with ground truth, default the ground-truth rate     |

- `overview.mp4`: the whole scene with ground-truth boxes (black, dashed) and track boxes (position, size and heading)
  with trails. Objects without a size are drawn as points.
- `zoom_<ID>.mp4`: a camera following one object, showing the same plus the track's predicted position, the χ² gate
  ellipse (p = 0.99, as the production association gate) from the predicted measurement covariance `S`, and its velocity
  arrow (distance covered in 1 s).

MP4 output needs `ffmpeg` on the `PATH`.

## Scenario directory

| File                | Content                                                                                                                                                                                                                                                 |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `groundtruth.jsonl` | [Ground Truth Format](../README.md#ground-truth-format-canonical-jsonl), with optional `size`, `rotation` (heading), `velocity` and `truth` (`speed`, `yaw_rate`, `acceleration`)                                                                       |
| `detections.jsonl`  | [Input Detection Format](../README.md#input-detection-format) with 3D detections (`translation`, `size`, `rotation` from orienting sensors); detection ids are ground-truth object ids                                                                  |
| `tracks.jsonl`      | [Tracker Output Format](../README.md#tracker-output-format), the estimate after every filter step                                                                                                                                                       |
| `estimator.jsonl`   | `config` line per track (motion models, noise settings, UKF parameters, transition matrix, state names), then a `step` line per filter step: model probabilities `mu`, state `x`, covariance `P`, predicted measurement `z_pred` and its covariance `S` |

Any file may be missing. Timestamps count from the `system_clock` epoch; the tools show seconds since the first one.
Tracks are paired with ground-truth objects by position with `match_tracks()` from [utils/tracks.py](../utils/tracks.py)
(at least 10 shared frames), so the ids may differ.

To plot real tracker output, put the evaluation pipeline outputs under the expected names:

```bash
mkdir -p /tmp/real-run
ln -s <run>/harness/outputs.jsonl /tmp/real-run/tracks.jsonl
ln -s <run>/dataset/ground_truth.jsonl /tmp/real-run/groundtruth.jsonl
python visualization/plot_scenario.py /tmp/real-run
```

## Tests

```bash
pytest visualization -v
```

- [tests/fixtures/target_born_moving](tests/fixtures/target_born_moving): recorder output of
  `MotionScenarioTest.TargetBornMovingAcquiresSpeed`; regenerate it with the recording command above and
  `--gtest_filter=MotionScenarioTest.TargetBornMovingAcquiresSpeed`.
- [tests/schema/camera-data.schema.json](tests/schema/camera-data.schema.json): copy of `tracker/schema/camera-data.schema.json`
  with 3D detections from branch `ITEP-97104_tracker_3d_detections`; replace it with the tracker schema once that is merged.
