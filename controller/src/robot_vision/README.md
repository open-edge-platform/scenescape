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

## Kalman filter settings

`TrackManagerConfig` passes three settings to `MultiModelKalmanEstimator.initialize()` for every new track. The Scene
Controller and the Tracker service do not read them from their configuration files: both use the production values
`kProduction*` in [TrackManager.hpp](include/rv/tracking/TrackManager.hpp) (`tracking.PRODUCTION_*` in Python).

| Python / C++ setting                                     | Production | Meaning                                                   |
| -------------------------------------------------------- | ---------- | --------------------------------------------------------- |
| `default_process_noise` / `mDefaultProcessNoise`         | `1e-4`     | Scale `q` of the process noise                            |
| `default_measurement_noise` / `mDefaultMeasurementNoise` | `0.2`      | Measurement noise `r`; initial variance of position, size |
| `init_state_covariance` / `mInitStateCovariance`         | `1.0`      | Initial velocity variance `p`; caps the other states      |

The state is x, y, vx, vy, ax, ay, z, vz, length, width, height, yaw and yaw rate; a detection measures x, y, z,
length, width, height and yaw. Units are m, rad and s.

**Process noise.** Before every predict, each motion model gets its own process noise from its velocity and the time
step `dt` (at least 1 ms), with `q_v = max(1000 * q, 1e-3)`:

- Position, z and size get no direct noise: the position uncertainty grows only through the velocity.
- Velocity: `q_v * (1 + speed) * dt` along the direction of motion, `q_v / 100 * dt` across it. Below 1 mm/s the
  along-track direction is world x.
- Vertical velocity: `q_v * dt` in every model, independent of the direction of motion.
- Acceleration: CA gets the same 2×2 block as the velocity.
- Turn rate: CTRV gets `q_v * dt`.
- Yaw: `q / 100 * dt`.
- A state the model resets to 0 (acceleration in CV and CTRV, turn rate in CV and CA) gets `1e-6 * dt`, which keeps the
  covariance positive definite. CP, which is not a production model, gets the velocity block on the acceleration and
  `q * dt` on the turn rate.

Because of the floor in `q_v`, every `q` up to `1e-6` gives the same velocity and turn-rate noise, and `q = 0` does not
turn the process noise off.

**Measurement noise.** The measurement noise covariance is `r` times the identity on the seven measured values. A
detection without a usable orientation does not observe yaw: its update leaves the yaw row out.

**Initial covariance.** The initial covariance is diagonal: `r` for x, y, z, length, width and height, `p` for vx, vy
and vz, and `min(p, cap)` for the rest, with caps of 0.1 for acceleration, 0.05 for yaw and 0.01 for yaw rate. A new
track starts at rest, so `p` sets how fast it picks up an object that enters already moving: with the production
`p = 1` a car entering at 8 m/s keeps one track through a 2 m Euclidean gate at 10 fps.

**Sigma points.** The unscented filter uses α = 1, β = 2 and κ = 3 − n for the n = 13 states. The sigma points then
sit at √3 σ, which matches a Gaussian's fourth moment along each axis; the centre weight is negative (−10/3), so the
predicted mean extrapolates from the centre point instead of averaging the points, and with β = 2 the covariance stays
positive semi-definite. Only CTRV is nonlinear. At 10 fps κ makes no measurable difference; with a turn-rate
uncertainty of 1 rad over one step CTRV's predicted mean speed is 1 % off the exact value, where κ = 0 is 41 % too
fast.

Earlier versions added `q` times the identity to all twelve states at every predict, independent of `dt`, and started
from `p` times the identity. Values tuned for them do not carry over.

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
