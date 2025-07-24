# Robot Vision Benchmarks

This directory contains performance benchmarks for the Robot Vision tracking components, specifically focusing on the `MultipleObjectTracker::track` method.

## Overview

This is a realistic benchmark focused on measuring the performance of people tracking scenarios:

- **50-people tracking**: Simulates realistic pedestrian tracking with human-like movement patterns, walking speeds, and dimensions

## Quick Start

### 1. Build Benchmarks

```bash
./build_benchmark.sh
```

### 2. Run Benchmarks

**Human-readable output:**

```bash
./run_benchmarks.sh
```

**JSON output for analysis:**

```bash
./run_benchmarks.sh --json
```

### 3. Compare Results

```bash
./compare_benchmarks.sh old_results.json new_results.json
```

## Prerequisites

The build script will automatically configure the project, but you may need to install dependencies:

**Ubuntu/Debian:**

```bash
sudo apt-get install cmake build-essential libbenchmark-dev
```

**macOS:**

```bash
brew install cmake google-benchmark
```

## Scripts

### build_benchmark.sh

Builds the benchmark executable from scratch:

- Cleans previous build
- Configures with Release mode and benchmarks enabled
- Builds the RobotVisionBenchmarks target

### run_benchmarks.sh

Runs the tracking benchmarks:

- **Default**: Human-readable console output
- **--json flag**: Saves results to `out/rv_benchmark_<git_hash>.json`

### compare_benchmarks.sh

Compares two benchmark result files:

- Uses Google Benchmark's official compare.py tool
- Shows performance differences between runs
- Automatically downloads comparison tools on first use

## Advanced Usage

### Manual Building

If you need custom build options:

```bash
cd /path/to/robot_vision
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_BENCHMARKS=ON
cmake --build . --target RobotVisionBenchmarks
```

### Direct Execution

```bash
# Run the benchmark directly
../build/benchmarks/RobotVisionBenchmarks

# Custom parameters
../build/benchmarks/RobotVisionBenchmarks --benchmark_repetitions=5
```
