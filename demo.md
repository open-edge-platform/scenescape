make init-secrets          # only if manager/secrets doesn't already exist
make build-core
make docker-compose.yml DLSTREAMER_DOCKER_COMPOSE_FILE=./sample_data/compose/docker-compose-ptz-demo.yml
make .env
SUPASS=<your-password> docker compose --profile controller up -d
