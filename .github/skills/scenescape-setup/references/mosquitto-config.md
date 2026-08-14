<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Mosquitto Broker Config

The deployment uses `dlstreamer-pipeline-server/mosquitto/mosquitto-secure.conf`, which enables
**TLS on listener 1883** and TLS websockets on 1884. The content matches:

```
allow_anonymous true

listener 1883
keyfile /mosquitto/secrets/certs/scenescape-broker.key
certfile /mosquitto/secrets/certs/scenescape-broker.crt
tls_version tlsv1.3

listener 1884
cafile /mosquitto/secrets/certs/scenescape-ca.pem
keyfile /mosquitto/secrets/certs/scenescape-broker.key
certfile /mosquitto/secrets/certs/scenescape-broker.crt
protocol websockets
```

All MQTT clients (video-analytics, scene controller, analytics, web manager, verification
scripts) connect over TLS on port 1883 using the SceneScape CA certificate.

## Optional Mosquitto Password File

If you need a password file for a stricter broker configuration, generate it after running
`<deploy_dir>/secrets/generate_secrets.sh` by extracting credentials from the auth JSON files:

```bash
SECRETSDIR=<deploy_dir>/secrets
: > "$SECRETSDIR/mosquitto.passwd"
for AUTH in controller.auth browser.auth calibration.auth; do
  USER=$(python3 -c "import json; d=json.load(open('$SECRETSDIR/$AUTH')); print(d['user'])")
  PASS=$(python3 -c "import json; d=json.load(open('$SECRETSDIR/$AUTH')); print(d['password'])")
  docker container run --rm -v "$SECRETSDIR:/work" eclipse-mosquitto:2.0.22 \
    sh -lc "mosquitto_passwd -b /work/mosquitto.passwd '$USER' '$PASS'"
done
```
