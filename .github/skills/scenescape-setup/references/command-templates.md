<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Runtime Command Templates

Use these reusable commands in setup verification steps.

## Determine SceneScape Network Name

```bash
NET_NAME=$(docker network ls --format '{{.Name}}' | grep '_scenescape$' | head -1)
```

## RTSP Gate Check

```bash
docker container run --rm --network "$NET_NAME" \
  linuxserver/ffmpeg:version-8.1-cli \
  -nostdin -v error -rtsp_transport tcp \
  -i '<rtsp_url>' \
  -t 5 -f null -
echo "EXIT:$?"
```

## MQTT Subscribe (TLS 1883)

The broker uses `mosquitto-secure.conf` with TLS on listener 1883. Mount the SceneScape CA and
use `--insecure` because the broker certificate is issued for `broker.scenescape.intel.com`.

```bash
docker container run --rm --network <project>_scenescape \
  -v <deploy_dir>/secrets/certs/scenescape-ca.pem:/ca.pem:ro \
  eclipse-mosquitto:2.0.22 \
  mosquitto_sub -h broker.scenescape.intel.com -p 1883 \
  --cafile /ca.pem --insecure \
  -t '<topic>' -C 1 -W 120
```

## MQTT Publish (TLS 1883)

```bash
docker container run --rm --network <project>_scenescape \
  -v <deploy_dir>/secrets/certs/scenescape-ca.pem:/ca.pem:ro \
  eclipse-mosquitto:2.0.22 \
  mosquitto_pub -h broker.scenescape.intel.com -p 1883 \
  --cafile /ca.pem --insecure \
  -t '<topic>' -m '<payload>'
```
