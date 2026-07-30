# docker-compose.yml Template

Write this file to `<deploy_dir>/docker-compose.yml`. Replace `${SECRETSDIR}` with the
absolute path to `<deploy_dir>/secrets` (or pass it as an env var).

```yaml
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

name: scenescape

networks:
  scenescape:

secrets:
  root-cert:
    file: ${SECRETSDIR}/certs/scenescape-ca.pem
  web-cert:
    file: ${SECRETSDIR}/certs/scenescape-web.crt
  web-key:
    file: ${SECRETSDIR}/certs/scenescape-web.key
  reid-client-cert:
    file: ${SECRETSDIR}/certs/scenescape-reid.crt
  reid-client-key:
    file: ${SECRETSDIR}/certs/scenescape-reid.key
  django:
    file: ${SECRETSDIR}/django/secrets.py
  controller.auth:
    file: ${SECRETSDIR}/controller.auth
  browser.auth:
    file: ${SECRETSDIR}/browser.auth
  calibration.auth:
    file: ${SECRETSDIR}/calibration.auth
  autocalibration-cert:
    file: ${SECRETSDIR}/certs/scenescape-autocalibration.crt
  autocalibration-key:
    file: ${SECRETSDIR}/certs/scenescape-autocalibration.key
  mapping-cert:
    file: ${SECRETSDIR}/certs/scenescape-mapping.crt
  mapping-key:
    file: ${SECRETSDIR}/certs/scenescape-mapping.key

x-proxy-env: &proxy_env
  http_proxy: ${http_proxy}
  https_proxy: ${https_proxy}
  no_proxy: ${no_proxy:+${no_proxy},}.scenescape.intel.com
  HTTP_PROXY: ${http_proxy}
  HTTPS_PROXY: ${https_proxy}
  NO_PROXY: ${no_proxy:+${no_proxy},}.scenescape.intel.com

services:
  ntpserv:
    image: dockurr/chrony:4.8
    networks:
      scenescape:
    restart: unless-stopped
    environment:
      - NTP_DIRECTIVES=local stratum 10
    healthcheck:
      test:
        - CMD
        - sh
        - -c
        - "chronyc tracking | grep -E 'Stratum[[:space:]]+:[[:space:]]+([1-9]|1[0-6])[[:space:]]*$' || exit 1"
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s

  broker:
    image: eclipse-mosquitto:2.0.22
    configs:
      - source: mosquitto-secure
        target: /mosquitto/config/mosquitto.conf
    volumes:
      - ${SECRETSDIR}:/mosquitto/secrets:ro
    networks:
      scenescape:
        aliases:
          - broker.scenescape.intel.com
    environment:
      <<: *proxy_env
    restart: always

  pgserver:
    image: postgres:17.6
    environment:
      POSTGRES_USER: scenescape
      POSTGRES_PASSWORD: ${DATABASE_PASSWORD}
      POSTGRES_DB: scenescape
      <<: *proxy_env
    networks:
      - scenescape
    volumes:
      - vol-db:/var/lib/postgresql/data
    restart: always
    healthcheck:
      test:
        [
          "CMD-SHELL",
          "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB -h localhost -p 5432",
        ]
      interval: 2s
      timeout: 3s
      retries: 30
      start_period: 5s

  web:
    image: scenescape-manager:latest
    init: true
    networks:
      scenescape:
        aliases:
          - web.scenescape.intel.com
    depends_on:
      pgserver:
        condition: service_healthy
      broker:
        condition: service_started
      init-models:
        condition: service_completed_successfully
    ports:
      - "443:443"
    command: >
      webserver
      --dbtype postgres
      --broker broker.scenescape.intel.com
      --brokerauth /run/secrets/browser.auth
      --brokerrootcert /run/secrets/certs/scenescape-ca.pem
    healthcheck:
      test: 'curl --insecure -s https://localhost:443/api/v1/health | python3 -c ''import json,sys; data=json.load(sys.stdin); raise SystemExit(0 if data.get("ready") is True else 1)'''
      interval: 10s
      timeout: 120s
      retries: 10
      start_period: 10s
    environment:
      SUPASS: ${SUPASS}
      DBHOST: pgserver
      DBPORT: 5432
      DATABASE_PASSWORD: ${DATABASE_PASSWORD}
      BROKER: broker.scenescape.intel.com
      BROKERAUTH: /run/secrets/browser.auth
      BROKERROOTCERT: /run/secrets/certs/scenescape-ca.pem
      <<: *proxy_env
    volumes:
      - vol-media:/workspace/media
    secrets:
      - source: root-cert
        target: certs/scenescape-ca.pem
      - source: web-cert
        target: certs/scenescape-web.crt
      - source: web-key
        target: certs/scenescape-web.key
      - source: django
        target: django/secrets.py
      - browser.auth
      - calibration.auth
      - controller.auth
    restart: always

  scene:
    image: scenescape-controller:latest
    init: true
    networks:
      scenescape:
    depends_on:
      web:
        condition: service_healthy
      broker:
        condition: service_started
      ntpserv:
        condition: service_started
    environment:
      <<: *proxy_env
    command: >
      --restauth /run/secrets/controller.auth
      --brokerauth /run/secrets/controller.auth
      --broker broker.scenescape.intel.com
      --ntp ntpserv
    configs:
      - source: tracker-config
        target: /home/scenescape/SceneScape/tracker-config.json
      - source: reid-config
        target: /home/scenescape/SceneScape/reid-config.json
    volumes:
      - vol-media:/home/scenescape/SceneScape/media
    secrets:
      - source: root-cert
        target: certs/scenescape-ca.pem
      - source: django
        target: django/secrets.py
      - controller.auth
      - source: reid-client-key
        target: certs/scenescape-reid.key
      - source: reid-client-cert
        target: certs/scenescape-reid.crt
    restart: always

  video-analytics:
    image: intel/dlstreamer-pipeline-server:2026.2.0-20260728-weekly-ubuntu24
    networks:
      scenescape:
    depends_on:
      broker:
        condition: service_started
      ntpserv:
        condition: service_started
    environment:
      MQTT_HOST: broker.scenescape.intel.com
      MQTT_PORT: 1883
      ROOT_CA: /run/secrets/certs/scenescape-ca.pem
      # Keep mediaserver out of proxies by default; user-provided RTSP hosts are appended via .env.
      <<: *proxy_env
      no_proxy: mediaserver,${no_proxy:+${no_proxy},}broker.scenescape.intel.com,.scenescape.intel.com
      NO_PROXY: mediaserver,${no_proxy:+${no_proxy},}broker.scenescape.intel.com,.scenescape.intel.com
    volumes:
      - ./dlstreamer-pipeline-server/pipeline-config.json:/home/pipeline-server/config.json:ro
      - vol-models:/home/pipeline-server/models:ro
      # Native GST plugins (sscape_timestamp_capture / sscape_post_inference_data_publish)
      # must live on the GStreamer python plugin path — not under /home/pipeline-server/user_scripts.
      - ./dlstreamer-pipeline-server/user_scripts/gstplugins/sscape_post_decode_timestamp_capture.py:/opt/intel/dlstreamer/gstreamer/lib/gstreamer-1.0/python/sscape_post_decode_timestamp_capture.py
      - ./dlstreamer-pipeline-server/user_scripts/gstplugins/sscape_post_inference_data_publish.py:/opt/intel/dlstreamer/gstreamer/lib/gstreamer-1.0/python/sscape_post_inference_data_publish.py
      - ./dlstreamer-pipeline-server/user_scripts/gstplugins/sscape_policies.py:/opt/intel/dlstreamer/gstreamer/lib/gstreamer-1.0/python/sscape_policies.py
      - ./dlstreamer-pipeline-server/user_scripts/gstplugins/sscape_3d_detector.py:/opt/intel/dlstreamer/gstreamer/lib/gstreamer-1.0/python/sscape_3d_detector.py
      - ./dlstreamer-pipeline-server/model-proc-files:/home/pipeline-server/model-proc-files:ro
    secrets:
      - source: root-cert
        target: certs/scenescape-ca.pem
    tmpfs:
      - /var/cache/pipeline_root:mode=01777
    restart: unless-stopped

  init-models:
    image: alpine:latest
    user: root
    volumes:
      - vol-models:/models
    command: chown -R 1000:1000 /models
    restart: "no"

  mapping-init:
    image: alpine:3.23
    profiles:
      - mapping
    user: root
    volumes:
      - vol-mapping-model-weights:/workspace/model_weights
      - vol-mapping-torch-cache:/workspace/.cache/torch
      - vol-mapping-hf-cache:/workspace/.cache/huggingface
    command: >
      sh -c "chown -R 1001:1001 /workspace/model_weights /workspace/.cache/torch /workspace/.cache/huggingface"
    restart: "no"

  mapping:
    image: scenescape-mapping-${MAPPING_MODEL:-mapanything}:${VERSION:-latest}
    profiles:
      - mapping
    init: true
    user: "1001:1001"
    networks:
      scenescape:
        aliases:
          - mapping.scenescape.intel.com
    ports:
      - "8444:8444"
    depends_on:
      mapping-init:
        condition: service_completed_successfully
    environment:
      MAPPING_CPU_SEC_PER_FRAME: 10
      GUNICORN_TIMEOUT: 300
      PYTHONDONTWRITEBYTECODE: 1
      <<: *proxy_env
    volumes:
      - vol-mapping-model-weights:/workspace/model_weights
      - vol-mapping-torch-cache:/workspace/.cache/torch
      - vol-mapping-hf-cache:/workspace/.cache/huggingface
    secrets:
      - source: mapping-cert
        target: certs/scenescape-mapping.crt
      - source: mapping-key
        target: certs/scenescape-mapping.key
      - source: root-cert
        target: certs/scenescape-ca.pem
    healthcheck:
      test:
        ["CMD", "curl", "-k", "-I", "-s", "https://localhost:8444/v1/health"]
      interval: 15s
      timeout: 60s
      retries: 20
      start_period: 120s
    restart: unless-stopped

configs:
  mosquitto-secure:
    file: ./dlstreamer-pipeline-server/mosquitto/mosquitto-secure.conf
  tracker-config:
    file: ./controller/tracker-config.json
  reid-config:
    file: ./controller/reid-config.json

volumes:
  vol-db:
  vol-media:
  vol-models:
  vol-mapping-model-weights:
    driver: local
  vol-mapping-torch-cache:
    driver: local
  vol-mapping-hf-cache:
    driver: local
```

## Environment Variables

Create `<deploy_dir>/.env` (or export before `docker compose up`):

```bash
SECRETSDIR=$(pwd)/secrets
DATABASE_PASSWORD=$(python3 -c "
import re
txt = open('secrets/django/secrets.py').read()
print(re.search(r\"DATABASE_PASSWORD='([^']+)'\", txt).group(1))
")
SUPASS=$(cat secrets/supass)
VERSION=latest
MAPPING_MODEL=mapanything
UID=$(id -u)
GID=$(id -g)
```

`write_deployment_env.py` (Step 6) writes `VERSION` and `MAPPING_MODEL` automatically.
Mapping runs as UID **1001** inside the container; `mapping-init` fixes volume ownership
before the mapping service starts.
