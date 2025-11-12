#!/bin/bash

if [ -f .env ]; then
    set -a
    source .env 2>/dev/null
    set +a
fi

if [ -n "$PROFILE" ]; then
    ADDITIONAL_DOCKER_COMPOSE_ARGS="--profile $PROFILE"
else
    ADDITIONAL_DOCKER_COMPOSE_ARGS=""
fi

docker compose -f docker-compose-ppl.yaml down $ADDITIONAL_DOCKER_COMPOSE_ARGS
