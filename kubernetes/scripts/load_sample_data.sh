#!/bin/bash

# Set default variables
TIMEOUT=300  # 5 minutes timeout
INTERVAL=5   # Check every 5 seconds
POD_SUFFIX="-init-sample-data"
LOCAL_DATA_PATH=${1:-"../sample_data"}  # First argument or default
POD_DATA_PATH=${2:-"/workspace/sample_data"}           # Second argument or default

echo "Will copy from ${LOCAL_DATA_PATH} to pod:${POD_DATA_PATH}"
echo "Waiting for pod with name ending in '${POD_SUFFIX}' to be ready..."

START_TIME=$(date +%s)

# Keep checking until pod exists and is ready
while true; do
  # Get the pod name that ends with the suffix
  POD_NAME=$(kubectl get pods --no-headers -o custom-columns=":metadata.name" | grep ".*${POD_SUFFIX}$" | head -n1)

  # Check if pod exists
  if [[ -n "${POD_NAME}" ]]; then
    # Check if the pod is running
    POD_STATUS=$(kubectl get pod ${POD_NAME} -o jsonpath='{.status.phase}')

    if [[ "${POD_STATUS}" == "Running" ]]; then
      # Check if container is ready
      READY_STATUS=$(kubectl get pod ${POD_NAME} -o jsonpath='{.status.containerStatuses[0].ready}')

      if [[ "${READY_STATUS}" == "true" ]]; then
        echo "Found pod ${POD_NAME} and it's ready"
        break
      else
        echo "Pod ${POD_NAME} is running but container is not ready yet"
      fi
    else
      echo "Pod ${POD_NAME} found but not running. Status: ${POD_STATUS}"
    fi
  else
    echo "No pod found with name ending in '${POD_SUFFIX}'"
  fi

  # Check for timeout
  CURRENT_TIME=$(date +%s)
  ELAPSED_TIME=$((CURRENT_TIME - START_TIME))
  if [[ ${ELAPSED_TIME} -ge ${TIMEOUT} ]]; then
    echo "Timeout waiting for pod with name ending in '${POD_SUFFIX}' to be ready"
    exit 1
  fi

  echo "Waiting for pod to be ready... (${ELAPSED_TIME}s elapsed)"
  sleep ${INTERVAL}
done

# Execute kubectl cp to the pod
echo "Copying data from ${LOCAL_DATA_PATH} to ${POD_NAME}:${POD_DATA_PATH}..."
kubectl cp "${LOCAL_DATA_PATH}" "${POD_NAME}:${POD_DATA_PATH}"

if [ $? -eq 0 ]; then
  echo "Data loaded successfully to ${POD_NAME}!"
  echo "1" >> data_loaded.flag
  kubectl cp data_loaded.flag "${POD_NAME}:${POD_DATA_PATH}/ready.flag"
  rm data_loaded.flag
else
  echo "Failed to copy data to pod ${POD_NAME}"
  exit 1
fi