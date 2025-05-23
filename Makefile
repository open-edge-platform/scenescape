.PHONY: all precheck docs certificates docker autocalibration controller percebro build run stop test clean help clean-artifacts

help:
	@echo "Available targets:"
	@echo "  help            Show this help message"
	@echo "  precheck        Run pre-deployment checks and password handling"
	@echo "  build           Build all components (sequential except autocalibration, controller, percebro in parallel)"
	@echo "  compose         Generate docker-compose.yml"
	@echo "  docs            Clean docs"
	@echo "  certificates    Build certificates (requires .env)"
	@echo "  docker          Build docker images (requires .env)"
	@echo "  autocalibration Build autocalibration docker image"
	@echo "  controller      Build controller docker image"
	@echo "  percebro        Build percebro docker image"
	@echo "  run             Start the stack using docker compose"
	@echo "  stop            Stop the stack"
	@echo "  test            Run inference performance test"
	@echo "  clean           Clean all build artifacts and .env"
	@echo "  clean-artifacts Remove all generated and build artifacts"

# Run all steps: precheck, build, test, and run
all: precheck build test run

# Run pre-deployment checks and password handling
precheck:
	./scripts/precheck.sh

# Build steps
build:
	$(MAKE) compose
	$(MAKE) docs
	$(MAKE) certificates
	$(MAKE) docker
	$(MAKE) -j autocalibration controller percebro

docs:
	make -C docs clean

certificates: .env
	. $(CURDIR)/.env && make -C certificates CERTPASS="$$CERTPASS"

docker: .env
	. $(CURDIR)/.env && make -C docker DBPASS="$$DBPASS"

autocalibration:
	make -C autocalibration/docker

controller:
	make -C controller/docker

percebro:
	make -C percebro/docker

compose: 
	rm -f docker-compose.yml
	make -C docker ../docker-compose.yml

run:
	. $(CURDIR)/.env && env SUPASS="$$SUPASS" docker compose up -d


# Stop the stack
stop:
	docker compose down

# Test inference performance
test:
	./scripts/test_inference.sh

clean: clean-artifacts
	rm -f .env
	make -C docs clean
	make -C certificates clean
	make -C docker clean
	make -C autocalibration/docker clean
	make -C controller/docker clean
	make -C percebro/docker clean

clean-artifacts:
	rm -f admin-pass.txt
	rm -f apriltag-cam[0-9].json
	rm -rf autocalibration/scene_common
	rm -rf controller/scene_common
	rm -rf controller/utils
	rm -rf datasets
	rm -rf db
	rm -f db.sqlite3
	rm -f db-backup-*
	rm -rf docker/.mosquitto-go-auth-build
	rm -rf docker/editor
	rm -f docker/geckodriver.tar.gz
	rm -rf docker/jslibs
	rm -rf docker/l_openvino*
	rm -f docker/LICENSE
	rm -rf docker/mosquitto-go-auth
	rm -f docker-compose.yml
	rm -rf kubernetes/setup/
	rm -rf media
	rm -rf migrations
	rm -rf models
	rm -rf percebro/scene_common
	rm -rf percebro/utils
	rm -rf pvd-mqtt/detect
	rm -f sample_data/xREF_*
	rm -rf secrets
	rm -f sscape/migrations/[0-9][0-9][0-9][0-9]_*.py
	rm -f sscape/secrets.py
	rm -rf sscape/static/assets
	rm -rf sscape/static/bootstrap
	rm -rf sscape/static/examples
	rm -rf test_data
	rm -rf test_reports/
	rm -f tests/perf_tests/input/*.json

.env:
	@test -f .env || (echo "Missing .env file, run 'make precheck' first." && exit 1)