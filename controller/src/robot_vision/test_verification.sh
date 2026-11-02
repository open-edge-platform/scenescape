#!/bin/bash
set -e

REPO_ROOT="/home/elukasiuk/scenescape"
cd "$REPO_ROOT"

echo "=== STEP 0: Building with CMake ==="
cmake -S controller/src/robot_vision -B controller/src/robot_vision/build -G Ninja -DBUILD_TESTING=ON -DBUILD_PYTHON_BINDINGS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build controller/src/robot_vision/build -j$(nproc)

echo "=== Running baseline tests (before directory) ==="
mkdir -p controller/src/robot_vision/build/recordings/before
RV_SCENARIO_DIR=$PWD/controller/src/robot_vision/build/recordings/before controller/src/robot_vision/build/test/RobotVisionTests --gtest_filter='MotionScenarioTest.*'

echo "=== Running full test suite ==="
controller/src/robot_vision/build/test/RobotVisionTests

echo "=== Running after tests ==="
mkdir -p controller/src/robot_vision/build/recordings/after
RV_SCENARIO_DIR=$PWD/controller/src/robot_vision/build/recordings/after controller/src/robot_vision/build/test/RobotVisionTests --gtest_filter='MotionScenarioTest.*'

echo "=== Comparing before and after recordings ==="
diff -r controller/src/robot_vision/build/recordings/before controller/src/robot_vision/build/recordings/after || {
  echo "ERROR: Recordings differ! This indicates a change in behavior."
  exit 1
}

echo "=== All tests passed and recordings are identical! ==="
