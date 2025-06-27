#!/bin/bash

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

trap test_int INT

function test_int() {
  echo "Interrupting test"
  docker compose ${COMPOSE_FLAGS} --project-directory ${PWD} --project-name ${PROJECT} down
  rm -rf ${DBROOT}/{db,media,migrations}
  docker network rm ${PROJECT}-${NETWORK}
  [ -n "${COMPOSE_DELETE}" ] && rm -f ${COMPOSE_DELETE}
  echo "Test aborted"
  exit 1
}

function wait_for_container()
{
  CONTAINERNAME=$1
  WAITFORSTRING=${2:-"Container is ready"}
  MAX_WAIT=${3:-"60"}
  CUR_WAIT=0
  CONTAINER_READY=0
  while [ -z "$(docker ps -q -f name=^/${CONTAINERNAME}$ )" ]
  do
    sleep 1
    CUR_WAIT=$(( $CUR_WAIT+1 ))
    if [[ $CUR_WAIT -ge $MAX_WAIT ]]
    then
      echo "Error: Failed to start ${CONTAINERNAME} container."
      return 1
    fi
  done

  while true
  do
    if docker logs ${CONTAINERNAME} 2>&1 | grep -q "${WAITFORSTRING}"
    then
      CONTAINER_READY=1
      break
    fi
    sleep 1
    CUR_WAIT=$(( $CUR_WAIT+1 ))
    if [[ $CUR_WAIT -ge $MAX_WAIT ]]
    then
      echo "Error: Failed detecting start of container $CONTAINERNAME. ${CUR_WAIT} ${MAX_WAIT} ${WAITFORSTRING}"
      return 1
    fi
  done
}
