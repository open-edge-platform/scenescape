#!/bin/bash

set -e

mkdir -p logs
cp docker-compose-percebro-$1.yml docker-compose.yml
echo "Logging to logs/run-percebro-perf-test-$1.log"
docker compose up > logs/run-percebro-perf-test-$1.log 2>&1
