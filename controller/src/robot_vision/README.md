# Robot Vision

Algorithms for sensor fusion, environment perception, object detection and tracking in C++ with Python interface

[![Build](https://github.com/intel-innersource/applications.robotics.mobile.robot-vision/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/intel-innersource/applications.robotics.mobile.robot-vision/actions/workflows/ci.yml)

# Build Dependencies

```bash
sudo apt install build-essential pkg-config python3 python3-setuptools python3-wheel cmake python3-dev googletest libpython3-dev
```

# Install Dependencies

```bash
sudo apt install pybind11-dev libopencv-dev libeigen3-dev libpcl-dev libtbb-dev libomp-dev libgoogle-glog-dev libgflags-dev libatlas-base-dev libsuitesparse-dev
```

# Installation

```bash
python3 -m pip install build
python3 -m build --wheel
pip3 install dist/robot_vision-X.X.X-cpXX-cpXXm-linux_x86_64.whl
```

## Test scenario recordings

Tests that use `ScenarioRecorder` ([test/support/ScenarioRecorder.hpp](test/support/ScenarioRecorder.hpp)) write the
ground truth, detections, tracks and estimator steps of their runs as JSONL files when `RV_SCENARIO_DIR` is set, and
nothing otherwise. `MotionScenarioTests.cpp` and `AssociationScenarioTests.cpp` record all their scenarios.

1. Build the tests, with the build dependencies above:

   ```bash
   cmake -S . -B build -DBUILD_TESTING=ON -DBUILD_PYTHON_BINDINGS=OFF -DCMAKE_BUILD_TYPE=Release
   cmake --build build -j$(nproc)
   ```

2. Run them with recording on; each test writes `$RV_SCENARIO_DIR/<Suite>.<Test>/[<case>/]`:

   ```bash
   RV_SCENARIO_DIR=/tmp/rv-scenarios ./build/test/RobotVisionTests --gtest_filter='MotionScenarioTest.*'
   ```

To record another test, give the recorder the ground truth and pass it to the `FilterRun`, which then records every
detection and estimate:

```cpp
#include "support/ScenarioRecorder.hpp"

ScenarioRecorder recorder("turn");  // optional case name
recorder.truth(truth);              // object id 1, category from the truth Box (kCar, kPerson)
FilterRun run(productionConfig(), &recorder);
run.feed(observe(truth, camera));   // detections go under the Sensor id, "camera" unless Sensor{.id = ...}
run.coast(1.0);
```

For several objects, pass the same id to `truth()` and as the third `FilterRun` argument. The files are described in
[Input files](../../../tools/tracker/evaluation/visualization/README.md#input-files).

### Vertical motion and paired runs

`Trajectory::climb(vz, seconds)` and `segment(acceleration, yawRate, vz, seconds)` add a constant vertical rate per
segment (`speed` stays the horizontal speed), and `Sensor::zNoise` adds z noise without changing the x/y noise. A planar
case gets a 3D twin without changing its definition: `VerticalProfile().climb(...).apply(truth)` lays a vertical motion
over any truth, `atHeight(truth, z)` places it at a constant height. `runScenario` runs the filter and returns the
estimates and model probabilities; its `Sensor` is taken by value, so two runs with the same sensor see the same noise
(`seeded(sensor, seed)` repeats a scenario with other noise).

```cpp
const auto planar = Trajectory({.speed = 5.0, .box = kCar}).straight(2.0).turn(0.3, 6.0).sample(10.0);
const Sensor camera{.positionNoise = 0.3};
const auto flat = runScenario(planar, camera);
const auto climbing = runScenario(VerticalProfile().climb(0.5, 4.0).apply(planar), camera);  // 3rd argument: RunOptions
const auto metrics = climbing.metrics();             // horizontal/vertical max and rms error, final speed and vz error
const auto diff = maxDifference(flat, climbing);     // largest |x|, |y|, |z|, |vx|, |vy|, |vz|, |yaw|, |probability|
```

### Measurement noise R

`Sensor::positionCovariance` draws each detection's position error from a covariance and attaches a per-detection R
(`measurementNoiseCov`) to the detection. It replaces `positionNoise` and `zNoise`, which must stay 0. The covariance
comes from one of:

- `groundPlaneCamera(position, angularSigma)`: a camera at `position` (x, y, z; above the object) that projects the
  ground point, with an angular error of `angularSigma` [rad]. The error grows with range and is longest along the
  ground range; z is exact.
- `depthCamera(position, angularSigma, depthFraction)`: a camera that also estimates depth, with a sigma of
  `depthFraction` × range along the viewing ray and `angularSigma` × range across it; z is measured (`zMeasured`).
- `fixedCovariance(covariance)`: the same covariance for every detection.

The reported R has the position covariance multiplied by `reportedScale`, `sizeNoise²` for length, width and height,
and `yawNoise²` for orienting sensors. Every axis left with zero variance, e.g. z of a ground-plane camera, gets
`defaultNoise`, by default `kProductionMeasurementNoise` as in `productionConfig()`; set it to the config's
`mDefaultMeasurementNoise` when a test uses another value.

Two settings change only what the sensor reports, not the drawn error, so runs that differ only in them get the same
detection positions:

- `reported = false`: the detections carry no R, and the tracker uses its default R.
- `reportedScale`: how well the reported R matches the true error; it multiplies the reported position covariance, a
  variance. 1 is a calibrated sensor. Below 1 the sensor claims to be more precise than it is: 0.25 reports half the
  true sigma, so its detections pull the estimate too hard and get too tight a gate. Above 1 it claims to be less
  precise: its detections pull too weakly and get too wide a gate.

`Observation::trueCovariance` is the covariance the error was drawn from, also without R. Covariances are computed at
the true position; a production producer computes R at the noisy detection, which differs noticeably only close to the
sensor.

```cpp
Sensor camera{.positionCovariance = groundPlaneCamera({0.0, -12.0, 4.0}, 0.01)};  // 4 m high, 0.01 rad
auto withoutR = camera;
withoutR.positionCovariance->reported = false;
auto overconfident = camera;
overconfident.positionCovariance->reportedScale = 0.25;  // reports half the true sigma
const auto aware = runScenario(truth, camera);
const auto legacy = runScenario(truth, withoutR);              // same positions, default R
const auto miscalibrated = runScenario(truth, overconfident);  // same positions, R too small
```

### Plots and videos

See [Scenario Visualization](../../../tools/tracker/evaluation/visualization/README.md).

### Tracking metrics

HOTA, MOTA, IDF1 and the other TrackEval metrics can be computed for a recording with the TrackEval command line; see
[TrackEvalEvaluator](../../../tools/tracker/evaluation/evaluators/README.md#trackevalevaluator).

## Documentation

### Html documentation

Install necessary packages

```bash
pip3 install sphinx, sphinx-rtd-theme
```

then build the documentation with:

```bash
make docshtml
```

after that you can launch the doc server with

```bash
make docserve
```

To access the remote server from your windows machine, activate the port forwarding via ssh

```bash
ssh -N -f -L localhost:8000:localhost:8000 userid@machine
```

Access the documentation at http://localhost:8000

### PDF documentation

Install latexmk

```bash
sudo apt install latexmk
```

Call the make command

```bash
make docspdf
```

The pdf will be generated in docs/\_build/latex/robot_vision.pdf
