# Robot Vision Benchmarks

Performance benchmarks for `MultipleObjectTracker::track` (Scene Controller / Tracker shared kernel).

## Workload

People walk persistently across a 50 m x 50 m area (0.5-2.0 m/s, random heading drift). Without `--association-config` the tracker's default `track(objects, ts, score)` path is used; otherwise the configured association method applies (see below). The tracker and people are reset every 100 frames.

| Benchmark         | `track()` calls per frame | Matches                                   |
| ----------------- | ------------------------- | ----------------------------------------- |
| `BM_TimeChunking` | 1 (all cameras batched)   | Tracker Service, Controller time-chunking |
| `BM_Immediate`    | 1 per camera (staggered)  | Controller Immediate mode                 |

Camera layout (`overlap` argument):

- `overlap:0` — each person is seen by exactly one camera (round-robin split).
- `overlap:1` — every camera sees every person with 0.1 m per-camera position noise (multi-camera fusion path). Only registered for 2+ cameras.

## Peak FPS

`peak_fps = 1 / mean_seconds_per_frame` (real time, one category worker), where a frame is one `track()` call in `BM_TimeChunking` and one `track()` call per camera in `BM_Immediate`. Time-chunking at rate `R` stays backlog-free only if mean latency < `1/R`.

## Quick start

```bash
# Ubuntu/Debian
sudo apt-get install -y cmake build-essential libbenchmark-dev

./build_benchmark.sh
./run_benchmark.sh
./run_benchmark.sh --json --association-config configs/association_production.json
./compare_benchmarks.sh out/baseline.json out/contender.json
```

## CLI

Harness flags (parsed before Google Benchmark flags):

| Flag                             | Default | Meaning                                                                                                       |
| -------------------------------- | ------- | ------------------------------------------------------------------------------------------------------------- |
| `--people N[,N...]`              | `50`    | Object counts to sweep                                                                                        |
| `--cameras N[,N...]`             | `1,2`   | Camera counts to sweep                                                                                        |
| `--overlap 0\|1[,...]`           | `0,1`   | Camera layouts to sweep (see above)                                                                           |
| `--association-config path.json` | unset   | If omitted, uses default `track(objects, ts, score)` path. JSON: `method`, `gate_probability`, `max_radius_m` |

Example production association config: `configs/association_production.json`.

Use `--benchmark_filter=BM_Immediate` (or `BM_TimeChunking`) to run one mode.

## Before/after a git change

Build and run the same CLI in two worktrees (or commits). Compare JSON with `compare_benchmarks.sh`. Do not bake Euclid-vs-Mahalanobis special cases into the tool beyond the optional config file.

## Scripts

- `build_benchmark.sh` — Release build with `-DBUILD_BENCHMARKS=ON` and Python bindings disabled (pybind11 is not required)
- `run_benchmark.sh` — Runs harness; `--json` writes `out/rv_benchmark_<git>_<tag>.json`
- `compare_benchmarks.sh` — Google Benchmark `compare.py`

## Prerequisites

- `cmake`, `libbenchmark-dev` (or Homebrew `google-benchmark`)
- OpenCV / robot_vision build deps
