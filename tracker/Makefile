
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

MQTT_CAMERA_TOPIC ?= scenescape/data/camera/atag-qcam1
MQTT_TRACKER_TOPIC ?= scenescape/data/tracker/unregulated_tracks
EXPECTED_MESSAGES ?= 4

# Default tracker config file (single defaults file)
TRACKER_CONFIG ?= config/config.json

# K6 load test configuration
MQTT_HOST ?= ssl://broker.scenescape.intel.com
MQTT_PORT ?= 1883
CAMERA_ID_PREFIX ?= atag-qcam
CAMERA_COUNT ?= 4
CAMERA_FPS ?= 15
OBJECT_COUNT ?= 100
TEST_DURATION ?= 5m
# TLS variables for secure MQTT (optional)
CA_ROOT ?= /home/jdanieck/repos/scenescape/manager/secrets/certs/scenescape-ca.pem
CLIENT_CERT_PATH ?= /home/jdanieck/repos/scenescape/manager/secrets/certs/scenescape-broker.crt
CLIENT_KEY_PATH ?= /home/jdanieck/repos/scenescape/manager/secrets/certs/scenescape-broker.key

# Build targets:
#   build-release - Optimized release build (smallest binary, for deployment)
#   build-debug   - Debug build with symbols (largest binary, for debugging)
#   build-profile - Release with debug symbols (for profiling/flame graphs)

# Source files for formatting
SRC_FILES := $(shell find src inc -type f \( -name "*.cpp" -o -name "*.h" \))

.PHONY: clean clean-images build-release build-debug build-profile run run-debug run-profile compose-build compose-up compose-down mqtt-publish mqtt-subscribe e2e-test format format-check check-k6 check-perf check-flamegraph install-perf install-flamegraph load-test jaeger-ui generate-certs clean-certs generate-env unit-test

clean: clean-images clean-certs
	rm -rf build-release build-debug build-profile
	rm -f compile_commands.json

clean-images:
	@echo "Invalidating Docker images built by compose (no volumes removed)..."
	-@docker compose down --rmi local --remove-orphans >/dev/null 2>&1 || true
	@echo "✓ Docker images invalidated"

generate-certs:
	@if [ ! -d certs ]; then \
		echo "Generating SSL certificates for testing..."; \
		./scripts/generate-test-certs.sh; \
		echo "✓ Certificates generated in certs/"; \
		make generate-env; \
	else \
		echo "✓ Certificates already exist in certs/"; \
	fi

clean-certs:
	@echo "Removing generated certificates and .env file..."
	rm -rf certs
	rm -f .env
	@echo "✓ Certificates cleaned"

# Generate .env with quoted PEM variables (newlines escaped as \n)
generate-env:
	@if [ -d certs ]; then \
		echo "Generating .env with quoted PEM variables..."; \
		CA_PEM=$$(awk 'BEGIN{ORS="\\n"} {print}' certs/ca.crt); \
		SRV_CERT_PEM=$$(awk 'BEGIN{ORS="\\n"} {print}' certs/server.crt); \
		SRV_KEY_PEM=$$(awk 'BEGIN{ORS="\\n"} {print}' certs/server.key); \
		CLI_CERT_PEM=$$(awk 'BEGIN{ORS="\\n"} {print}' certs/client.crt); \
		CLI_KEY_PEM=$$(awk 'BEGIN{ORS="\\n"} {print}' certs/client.key); \
		{ \
			printf "MQTT_CA_CERT_PEM=\"%s\"\n" "$$CA_PEM"; \
			printf "MQTT_SERVER_CERT_PEM=\"%s\"\n" "$$SRV_CERT_PEM"; \
			printf "MQTT_SERVER_KEY_PEM=\"%s\"\n" "$$SRV_KEY_PEM"; \
			printf "MQTT_CLIENT_CERT_PEM=\"%s\"\n" "$$CLI_CERT_PEM"; \
			printf "MQTT_CLIENT_KEY_PEM=\"%s\"\n" "$$CLI_KEY_PEM"; \
		} > .env; \
		echo "✓ Wrote .env with quoted PEM variables"; \
	else \
		echo "✗ certs/ directory missing. Run 'make generate-certs' first."; \
		exit 1; \
	fi

conan:
	pip3 install conan --break-system-packages
	conan profile detect --force

dependencies-release: conan
	conan install . --output-folder=build-release --build=missing -c tools.system.package_manager:mode=install

dependencies-debug: conan
	conan install . --output-folder=build-debug --build=missing -s build_type=Debug -c tools.system.package_manager:mode=install

dependencies-profile: conan
	conan install . --output-folder=build-profile --build=missing -s build_type=RelWithDebInfo -c tools.system.package_manager:mode=install

build-release: dependencies-release
	mkdir -p build-release
	cd build-release && cmake .. -DCMAKE_TOOLCHAIN_FILE=conan_toolchain.cmake -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTS=OFF -DCMAKE_EXPORT_COMPILE_COMMANDS=ON && cmake --build .
	strip build-release/tracker
	strip build-release/robot_vision/libRobotVision.so
	@if [ ! -L compile_commands.json ]; then \
		ln -sf build-release/compile_commands.json compile_commands.json; \
		echo "Created symlink: compile_commands.json -> build-release/compile_commands.json"; \
	fi

build-debug: dependencies-debug
	mkdir -p build-debug
	cd build-debug && cmake .. -DCMAKE_TOOLCHAIN_FILE=conan_toolchain.cmake -DCMAKE_BUILD_TYPE=Debug -DBUILD_TESTS=ON -DCMAKE_EXPORT_COMPILE_COMMANDS=ON && cmake --build .
	@if [ ! -L compile_commands.json ]; then \
		ln -sf build-debug/compile_commands.json compile_commands.json; \
		echo "Created symlink: compile_commands.json -> build-debug/compile_commands.json"; \
	fi

build-profile: dependencies-profile
	mkdir -p build-profile
	cd build-profile && cmake .. -DCMAKE_TOOLCHAIN_FILE=conan_toolchain.cmake -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBUILD_TESTS=OFF -DCMAKE_CXX_FLAGS="-fno-omit-frame-pointer" -DCMAKE_EXPORT_COMPILE_COMMANDS=ON && cmake --build .
	@if [ ! -L compile_commands.json ]; then \
		ln -sf build-profile/compile_commands.json compile_commands.json; \
		echo "Created symlink: compile_commands.json -> build-profile/compile_commands.json"; \
	fi
	@echo ""
	@echo "Profile build complete! To generate flame graphs:"
	@echo "  1. Run with perf: perf record -F 99 -g ./build-profile/tracker"
	@echo "  2. Generate FlameGraph: perf script | FlameGraph/stackcollapse-perf.pl | FlameGraph/flamegraph.pl > flame.svg"
	@echo "  Or use: make run-profile"

run-release: build-release
	# Local run: connect to local broker without SSL; override scenes path
	LD_LIBRARY_PATH=$$(find ~/.conan2/p -name "*.so*" -type f | xargs dirname | sort -u | paste -sd: -):$$LD_LIBRARY_PATH \
		MQTT_BROKER_HOST=localhost \
		MQTT_BROKER_PORT=1883 \
		MQTT_SSL=0 \
		SCENES_FILE=config/scenes-load-test.json \
		./build-release/tracker --config $(TRACKER_CONFIG)

run-debug: build-debug
	# Local run: connect to local broker without SSL; override scenes path
	LD_LIBRARY_PATH=$$(find ~/.conan2/p -name "*.so*" -type f | xargs dirname | sort -u | paste -sd: -):$$LD_LIBRARY_PATH \
		MQTT_BROKER_HOST=localhost \
		MQTT_BROKER_PORT=1883 \
		MQTT_SSL=0 \
		SCENES_FILE=config/scenes-load-test.json \
		./build-debug/tracker --config $(TRACKER_CONFIG)

run-profile: build-profile check-perf check-flamegraph
	@echo "Running with perf profiling (requires sudo)..."
	@echo "Press Ctrl+C to stop and generate flame graph"
	@PERF_BIN=$$(command -v perf 2>/dev/null || echo ""); \
	if [ -f ~/bin/perf ]; then \
		PERF_BIN=~/bin/perf; \
	elif [ -f /usr/lib/linux-tools-6.8.0-90/perf ]; then \
		PERF_BIN=/usr/lib/linux-tools-6.8.0-90/perf; \
	fi; \
	echo "Using perf: $$PERF_BIN"; \
	LIB_PATH=$$(find ~/.conan2/p -name "*.so*" -type f | xargs dirname | sort -u | paste -sd: -); \
	sudo LD_LIBRARY_PATH=$$LIB_PATH:$$LD_LIBRARY_PATH $$PERF_BIN record -F 99 -g -o perf.data -- ./build-profile/tracker --config $(TRACKER_CONFIG) || true
	@echo ""
	@if [ ! -f perf.data ]; then \
		echo "⚠ No perf.data file found. Profiling may have failed."; \
		exit 1; \
	fi
	@echo "Generating flame graph..."
	@PERF_BIN=$$(command -v perf 2>/dev/null || echo ""); \
	if [ -f ~/bin/perf ]; then \
		PERF_BIN=~/bin/perf; \
	elif [ -f /usr/lib/linux-tools-6.8.0-90/perf ]; then \
		PERF_BIN=/usr/lib/linux-tools-6.8.0-90/perf; \
	fi; \
	if [ -d FlameGraph ]; then \
		sudo $$PERF_BIN script -i perf.data | FlameGraph/stackcollapse-perf.pl | FlameGraph/flamegraph.pl > flame.svg && \
		echo "✓ Flame graph generated: flame.svg" && \
		echo "  View with: xdg-open flame.svg"; \
	else \
		echo "⚠ FlameGraph not found. Install with: make install-flamegraph"; \
		echo "Then manually generate: sudo $$PERF_BIN script -i perf.data | FlameGraph/stackcollapse-perf.pl | FlameGraph/flamegraph.pl > flame.svg"; \
	fi

compose-build:
	DOCKER_BUILDKIT=1 docker compose --profile tracker build

compose-up-tracker: generate-certs
	docker compose --profile tracker up -d
compose-up-infrastructure: generate-certs
	docker compose --profile infra up -d

compose-down:
	docker compose down --volumes --remove-orphans

mqtt-publish-sample:
	@TIMESTAMP=$$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ"); \
	cat test/data/detection-message-1.json | sed "s/\"timestamp\": \"[^\"]*\"/\"timestamp\": \"$$TIMESTAMP\"/g" | docker exec -i mqtt-broker mosquitto_pub -h localhost -t "$(MQTT_CAMERA_TOPIC)" -l
	@sleep 0.2
	@TIMESTAMP=$$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ"); \
	cat test/data/detection-message-3.json | sed "s/\"timestamp\": \"[^\"]*\"/\"timestamp\": \"$$TIMESTAMP\"/g" | docker exec -i mqtt-broker mosquitto_pub -h localhost -t "$(MQTT_CAMERA_TOPIC)" -l
	@sleep 0.2
	@TIMESTAMP=$$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ"); \
	cat test/data/detection-message-4.json | sed "s/\"timestamp\": \"[^\"]*\"/\"timestamp\": \"$$TIMESTAMP\"/g" | docker exec -i mqtt-broker mosquitto_pub -h localhost -t "$(MQTT_CAMERA_TOPIC)" -l
	@sleep 0.2
	@TIMESTAMP=$$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ"); \
	cat test/data/detection-message-2.json | sed "s/\"timestamp\": \"[^\"]*\"/\"timestamp\": \"$$TIMESTAMP\"/g" | docker exec -i mqtt-broker mosquitto_pub -h localhost -t "$(MQTT_CAMERA_TOPIC)" -l

mqtt-publish-load: check-k6
	@echo "Running k6 load test with $(OBJECT_COUNT) objects..."
	@export MQTT_HOST=$(MQTT_HOST) \
		MQTT_PORT=$(MQTT_PORT) \
		CAMERA_ID_PREFIX=$(CAMERA_ID_PREFIX) \
		CAMERA_COUNT=$(CAMERA_COUNT) \
		CAMERA_FPS=$(CAMERA_FPS) \
		OBJECT_COUNT=$(OBJECT_COUNT) \
		DEFAULT_TEST_DURATION=$(TEST_DURATION) \
		CA_ROOT=$(CA_ROOT) \
		CLIENT_CERT_PATH=$(CLIENT_CERT_PATH) \
		CLIENT_KEY_PATH=$(CLIENT_KEY_PATH); \
	cd test && k6 run generate-detections.js

mqtt-subscribe:
	docker exec -it mqtt-broker mosquitto_sub -h localhost -t "$(MQTT_TRACKER_TOPIC)" -v

format:
	@echo "Formatting source files with clang-format..."
	@clang-format -i $(SRC_FILES)
	@echo "✓ Formatting complete"

format-check:
	@echo "Checking code formatting..."
	@if ! clang-format --dry-run --Werror $(SRC_FILES) 2>&1; then \
		echo "✗ Formatting issues found. Run 'make format' to fix them."; \
		exit 1; \
	else \
		echo "✓ All files are properly formatted"; \
	fi

check-k6:
	@command -v k6 > /dev/null || { echo "Error: k6 not installed. Install from https://k6.io/docs/get-started/installation/"; exit 1; }
	@echo "✓ k6 is installed"

check-perf:
	@if perf --version > /dev/null 2>&1; then \
		echo "✓ perf is installed ($$(perf --version))"; \
	elif [ -f ~/bin/perf ]; then \
		echo "✓ perf is installed (~/bin/perf)"; \
	elif [ -f /usr/lib/linux-tools-6.8.0-90/perf ]; then \
		echo "✓ perf found at /usr/lib/linux-tools-6.8.0-90/perf"; \
		echo "⚠ Note: Using perf from different kernel version"; \
	else \
		echo "Error: perf not found."; \
		echo "Options:"; \
		echo "  1. Install from packages: sudo apt-get install linux-tools-generic linux-tools-$$(uname -r)"; \
		echo "  2. Build from source: make install-perf"; \
		echo ""; \
		exit 1; \
	fi

install-perf:
	@echo "Building perf from kernel source..."
	@echo "Installing build dependencies..."
	sudo apt-get install -y flex bison libelf-dev libdw-dev libaudit-dev \
		libunwind-dev libslang2-dev libperl-dev python3-dev binutils-dev \
		libnuma-dev liblzma-dev libzstd-dev libcap-dev libbabeltrace-dev \
		systemtap-sdt-dev libtraceevent-dev git || true
	@echo ""
	@echo "Cloning kernel source (shallow clone)..."
	rm -rf /tmp/linux-perf
	git clone --depth 1 https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git /tmp/linux-perf
	@echo ""
	@echo "Building perf (minimal build, skipping optional features)..."
	cd /tmp/linux-perf/tools/perf && \
		make -j$$(nproc) \
		NO_LIBPYTHON=1 \
		NO_LIBPERL=1 \
		NO_JVMTI=1 \
		NO_LIBPFM4=1 \
		NO_LIBDEBUGINFOD=1 \
		NO_LIBBPF=1 \
		NO_LIBCRYPTO=1
	@echo ""
	@echo "Installing perf to ~/bin..."
	mkdir -p ~/bin
	cp /tmp/linux-perf/tools/perf/perf ~/bin/
	@echo ""
	@echo "✓ perf installed to ~/bin/perf"
	@~/bin/perf --version
	@echo ""
	@echo "Add ~/bin to your PATH if not already present:"
	@echo "  echo 'export PATH=\$$HOME/bin:\$$PATH' >> ~/.bashrc"
	@echo "  source ~/.bashrc"
	@echo ""
	@echo "To use it now: export PATH=\$$HOME/bin:\$$PATH"
	@echo ""
	@rm -rf /tmp/linux-perf
	@echo "✓ Cleaned up temporary files"

install-flamegraph:
	@if [ -d FlameGraph ]; then \
		echo "⚠ FlameGraph already exists"; \
		exit 0; \
	fi
	@echo "Cloning FlameGraph repository..."
	git clone https://github.com/brendangregg/FlameGraph.git
	@echo ""
	@echo "✓ FlameGraph installed to ./FlameGraph"
	@echo "Scripts available:"
	@echo "  - stackcollapse-perf.pl"
	@echo "  - flamegraph.pl"

check-flamegraph:
	@if [ ! -d FlameGraph ]; then \
		echo "⚠ FlameGraph not found."; \
		echo "Install with: make install-flamegraph"; \
		echo ""; \
	fi

load-test: check-k6 generate-certs
	@echo "Running pytest-orchestrated load test..."
	@export MQTT_HOST=$(MQTT_HOST) \
		MQTT_PORT=$(MQTT_PORT) \
		CAMERA_ID_PREFIX=$(CAMERA_ID_PREFIX) \
		CAMERA_COUNT=$(CAMERA_COUNT) \
		CAMERA_FPS=$(CAMERA_FPS) \
		OBJECT_COUNT=$(OBJECT_COUNT) \
		TEST_DURATION=$(TEST_DURATION) \
		KEEP_CONTAINERS=false; \
	cd test && pytest test_tracker_metrics.py -v -s

.PHONY: unit-test
unit-test: build-debug
	cd build-debug && ctest --output-on-failure
