#!/bin/bash

# this script should be executed from top level repo directory

mkdir -p ./output

docker run --rm \
  -u $(id -u):$(id -g) \
  -e PYTHONPATH="/" \
  -w / \
  -v ./output:/output \
  -v ./tests:/tests \
  --entrypoint pytest \
  scenescape-controller-test \
  -v \
  /tests/system/metric/tc_tracker_metric.py \
  --metric msoce \
  --camera_frame_rate 30 \
  --threshold 0 \
