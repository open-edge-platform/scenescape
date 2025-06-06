#!/bin/bash

# Copyright (C) 2021-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

TEST_NAME="NEX-T10414"
echo "Executing: ${TEST_NAME}"

TESTBASE="tests/perf_tests/"
INPDIR="sample_data"
COMPOSEDIR="${TESTBASE}/compose"
YMLFILE="docker-compose-scene_performance.yml"

MODELS=${1:-retail}
EXTRA_ARGS=${2:-${EXTRA_ARGS}}

#Extract the Input files:
if [ ! -f ${INPDIR}/"apriltag-cam1.json" ] || [ ! -f ${INPDIR}/"apriltag-cam2.json" ] || [ ! -f ${INPDIR}/"apriltag-cam3.json" ];
then
  echo "Attempting to generate the input json files for this test."

  INFMODELS=${MODELS}

  if [[ "${MODELS}" == "all" ]]
  then
    INFMODELS='apriltag,retail+reid'
  elif [[ "${MODELS}" == "retailreid" ]]
  then
    INFMODELS='retail+reid'
  fi
  docker/scenescape-start --image scenescape-percebro --shell percebro/percebro -i sample_data/apriltag-cam1.mp4 --intrinsics {\"fov\":70} --mqttid camera1 -i sample_data/apriltag-cam2.mp4 --intrinsics {\"fov\":70} --mqttid camera2 -i sample_data/apriltag-cam3.mp4 --intrinsics {\"fov\":70} --mqttid camera3 -m ${INFMODELS} --debug --frames 1000 --preprocess
  echo "finished percebro execution"
fi

if [ ! -f ${INPDIR}/"apriltag-cam1.json" ] || [ ! -f ${INPDIR}/"apriltag-cam2.json" ] || [ ! -f ${INPDIR}/"apriltag-cam3.json" ];
then
  echo "Input json files for model ${MODELS} doesn't exist, or failed to be created!. Aborting."
  exit 1
fi

#Run the test...
EXTRA_ARGS=${EXTRA_ARGS} docker compose -f ${COMPOSEDIR}/${YMLFILE} --project-directory ${PWD} run test
RESULT=$?

if [[ $RESULT -eq 0 ]]
then
    echo "${TEST_NAME}: PASS"
else
    echo "${TEST_NAME}: FAIL"
fi

exit $RESULT

