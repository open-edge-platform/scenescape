# Performance degradation system test

This test checks whether the system's performance holds up over a long run.

## Description

Starts Scenescape and every 60 seconds samples:

- MQTT message throughput (messages/sec across all topics)
- Host CPU and Memory usage
- REST API response latency (a `getScenes` round-trip)

Samples from a warm-up period are discarded. Once the configured run
duration elapses, the average of the first 5 remaining cycles (baseline) is
compared against the average of the last 5 cycles (trailing) for each
metric. The test fails if:

- MQTT throughput drops more than 20% relative to the baseline
- Host CPU usage grows more than 20% relative to the baseline
- Host Memory usage grows more than 10% relative to the baseline
- REST query time grows more than 200% relative to the baseline

The test also fails immediately if the MQTT broker connection is lost.

## How to run

Go to Scenescape directory, and execute the performance degradation test:

```bash
make SUPASS=admin123 run_performance_degradation_tests HOURS=2
```

If you already have the test `.venv` set up (created by `make setup-tests`),
you can invoke the test directly.

```bash
PERFORMANCE_HOURS=1 pytest tests/system/performance/test_sscape_performance_degradation.py
```
