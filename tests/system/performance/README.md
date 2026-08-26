# Performance degradation system test

This test checks whether the system's performance holds up over a long run.

## Description

Starts Scenescape and every 60 seconds samples:

- MQTT message throughput (messages/sec across all topics)
- CPU and Memory usage of the deployment's containers.
- REST API response latency (5 `getScenes` round-trips per cycle, to build a
  latency distribution rather than a single sample)

Samples from a warm-up period are discarded. The test watches for the
distinct ways a long run can go wrong:

1. **Liveness** — the test fails if throughput falls below 1 msg/sec in any
   cycle. The demo plays a fixed video loop, so throughput has a known,
   stable floor.
2. **Variability growth** — the post-warmup samples are split into an early
   half and a late half; the standard deviation of MQTT throughput, CPU, and
   Memory usage is compared per half. The test fails if any metric's
   variability (swing from its own average) grows more than 50% from the
   early half to the late half, indicating the system is becoming less
   stable the longer it runs.
3. **Saturation** — checked live, every cycle: if CPU or Memory usage stays at
   or above 90% for 3 consecutive cycles at any point in the run,
   the test aborts immediately as a crash-risk signal, rather than waiting
   for the run to finish or the process to actually die.
4. **Memory trend** — a least-squares trend is fitted to memory usage and
   extrapolated 24 hours ahead; the test fails if it would cross the 90%
   saturation ceiling. Trends that rise less than 1 percentage point across the run
   itself are treated as drift and ignored.
5. **REST response-time guarantees** — p50 and p99 latency are computed over
   the whole run and checked against absolute SLA ceilings. The p99
   (tail latency) of the early half of the run is also compared against the
   late half; the test fails if tail latency grows more than 100% over the
   run. p99.9 is reported but only enforced on runs long enough to produce
   1000 latency samples (roughly 3.5 hours), below which a "p99.9" is just
   the largest value observed.

The statistical checks require at least 40 post-warmup samples, so the run
must be at least roughly 45 minutes long. Below that the test fails.

The test also fails if the MQTT broker connection is lost.

## How to run

Go to Scenescape directory, and execute the performance degradation test:

```bash
make SUPASS=admin123 run_performance_degradation_test HOURS=2
```

If you already have the test `.venv` set up (created by `make setup-tests`),
you can invoke the test directly.

```bash
PERFORMANCE_HOURS=1 pytest tests/system/performance/test_sscape_performance_degradation.py
```
