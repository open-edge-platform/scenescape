#!/bin/bash

docker run --rm \
       -v ./harnesses:/workspace \
       -v ../../../tests/system/metric/test_data:/dataset \
       -w /dataset --entrypoint python \
       scenescape-controller:2026.0.0-dev \
       /workspace/poc_of_controller_harness.py

