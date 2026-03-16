#!/bin/bash

FILE="/etc/docker/daemon.json"
TMP_FILE=$(mktemp)

# Create file if it doesn't exist
if [ ! -f "$FILE" ]; then
  echo '{"features": {"containerd-snapshotter": true}}' > "$FILE"
  exit 0
fi

# Merge or add the features field
python3 -c "
import json, sys
f = '$FILE'
with open(f) as infile:
  data = json.load(infile)
data.setdefault('features', {})['containerd-snapshotter'] = True
with open('$TMP_FILE', 'w') as outfile:
  json.dump(data, outfile, indent=2)
"

sudo mv "$TMP_FILE" "$FILE"
sudo systemctl daemon-reload
sudo systemctl restart docker
