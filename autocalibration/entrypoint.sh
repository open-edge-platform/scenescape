#!/bin/bash
set -e

rm -f /tmp/healthy

if [ "$SKIP_MODEL_DOWNLOAD" != "1" ]; then
    echo "Checking NetVLAD model..."
    python3 /usr/local/bin/download_models.py
fi

touch /tmp/healthy
exec "$@"