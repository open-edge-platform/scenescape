# Robot Vision Benchmarks

Performance benchmarks for `MultipleObjectTracker::track` (Scene Controller / Tracker shared kernel).

## Peak FPS

`peak_fps = 1 / mean_seconds_per_track_call` (real time, one category worker). Time-chunking at rate `R` stays backlog-free only if mean latency < `1/R`.

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

| Flag | Default | Meaning |
| --- | --- | --- |
| `--people N[,N...]` | `50` | Object counts to sweep |
| `--cameras N[,N...]` | `1,2` | Camera counts (detections split round-robin) |
| `--association-config path.json` | unset | If omitted, uses default `track(objects, ts, score)` path. JSON: `method`, `gate_probability`, `max_radius_m` |

Example production association config: `configs/association_production.json`.

## Before/after a git change

Build and run the same CLI in two worktrees (or commits). Compare JSON with `compare_benchmarks.sh`. Do not bake Euclid-vs-Mahalanobis special cases into the tool beyond the optional config file.

## Scripts

- `build_benchmark.sh` — Release build with `-DBUILD_BENCHMARKS=ON`
- `run_benchmark.sh` — Runs harness; `--json` writes `out/rv_benchmark_<git>_<tag>.json`
- `compare_benchmarks.sh` — Google Benchmark `compare.py`

## Prerequisites

- `cmake`, `libbenchmark-dev` (or Homebrew `google-benchmark`)
- OpenCV / robot_vision build deps
