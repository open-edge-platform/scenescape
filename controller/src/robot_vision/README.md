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

To record association, run the full tracker with `TrackerRun` ([test/support/TrackerRun.hpp](test/support/TrackerRun.hpp)).
It calls `MultipleObjectTracker::track()` once per frame like the Tracker Service, with production filter and track
lifecycle settings, and records the detections and the reliable tracks under their tracker ids. Each track's estimator
config holds the association gate, which the zoom videos draw:

```cpp
#include "support/ScenarioRecorder.hpp"

ScenarioRecorder recorder(std::string(association.method));
recorder.truth(person1, 1);
recorder.truth(person2, 2);
auto observations = observe(person1, camera, 1);  // detections carry their ground-truth object id
const auto more = observe(person2, camera, 2);
observations.insert(observations.end(), more.begin(), more.end());
TrackerRun run(positionMahalanobisAssociation(), 10.0, productionTrackerConfig(), &recorder);  // or euclideanAssociation()
run.play(sampleTimes(person1), withoutBetween(observations, 5.0, 5.8));  // a frame per time; no detections 5 s-5.8 s
run.identityErrors({1, 2});  // 0 when every object kept one track of its own
```

`AssociationScenarioTests.cpp` records every scenario with both methods, in `<case>` directories named after the
method, so the two runs can be compared side by side.

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
