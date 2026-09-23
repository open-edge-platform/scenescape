make init-secrets          # only if manager/secrets doesn't already exist
make build-all

# Render ptz-config.json / ptz-config-gpu.json from their .template files with
# the RTSP camera credentials (never commit the rendered files - they're gitignored).
# If a username/password contains ':', '@', or '/', percent-encode it first.
RTSP_CAM1_USER=<cam1-user> RTSP_CAM1_PASS=<cam1-pass> \
RTSP_CAM2_USER=<cam2-user> RTSP_CAM2_PASS=<cam2-pass> \
RTSP_CAM3_USER=<cam3-user> RTSP_CAM3_PASS=<cam3-pass> \
  ./dlstreamer-pipeline-server/render-ptz-config.sh

make docker-compose.yml DLSTREAMER_DOCKER_COMPOSE_FILE=./sample_data/compose/docker-compose-ptz-demo.yml
make .env
SUPASS=<your-password> docker compose --profile controller --profile mapping up -d
