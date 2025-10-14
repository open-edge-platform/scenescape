#!/bin/bash
set -euo pipefail
echo "Starting model installation with MODEL_TYPE=${MODEL_TYPE}, PRECISIONS=${MODEL_PRECISIONS}, MODEL_PROC=${MODEL_PROC}"
# Build arguments for install-omz-models
ARGS=""
case "${MODEL_TYPE}" in
  "default")
    ARGS="--default"
    ;;
  "ocr")
    ARGS="--ocr"
    ;;
  "all")
    ARGS="--all"
    ;;
  *)
    echo "Unknown MODEL_TYPE: ${MODEL_TYPE}. Using default."
    ARGS="--default"
    ;;
esac
ARGS="${ARGS} --precisions ${MODEL_PRECISIONS}"
# Add model_proc flag if enabled
if [ "${MODEL_PROC}" = "true" ]; then
  ARGS="${ARGS} --model_proc"
fi
echo "Running: python install-omz-models ${ARGS}"
python install-omz-models ${ARGS}
echo "Copying config files..."
python copy-config-files /workspace ${MODEL_DIR}
echo "Model installation completed successfully"
echo "Models installed in: ${MODEL_DIR}"
ls -la "${MODEL_DIR}" || true
