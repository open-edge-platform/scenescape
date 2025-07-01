
# Performance tests

## Overview

There are 3 tests included:
+ Inference Performance: Runs the inference model(s) and checks obtained frame rate.
+ Inference Conformance: Runs the inference model(s) and verifies the output versus a pre-generated reference.
+ Scene Performance: Runs the result of the inference and processes the sensor data, displays obtained rate.


## How to run:

#### Inference Performance

Run the inference_performance script:

...
tests/perf_tests/tc_inference_performance.sh
...

#### Inference Conformance

Run the inference_conformance script:
...
tests/perf_tests/tc_inference_conformance.sh
...

#### Scene Performance


Run the scene_performane script:
...
tests/perf_tests/tc_scene_performance.sh
...

