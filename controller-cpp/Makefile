# Makefile for SceneScape Controller C++

.PHONY: all build clean install test docker

# Build configuration
BUILD_DIR = build
CMAKE_FLAGS = -DCMAKE_BUILD_TYPE=Release

# Default target
all: build

# Create build directory and configure
configure:
	mkdir -p $(BUILD_DIR)
	cd $(BUILD_DIR) && cmake $(CMAKE_FLAGS) ..

# Build the project
build: configure
	cd $(BUILD_DIR) && make -j$(shell nproc)

# Clean build artifacts
clean:
	rm -rf $(BUILD_DIR)

# Install the binary
install: build
	cd $(BUILD_DIR) && make install

# Run tests
test: build
	cd $(BUILD_DIR) && ctest --output-on-failure

# Build debug version
debug:
	mkdir -p $(BUILD_DIR)-debug
	cd $(BUILD_DIR)-debug && cmake -DCMAKE_BUILD_TYPE=Debug .. && make -j$(shell nproc)

# Format code
format:
	find src include -name "*.cpp" -o -name "*.h" | xargs clang-format -i

# Static analysis
analyze:
	cd $(BUILD_DIR) && scan-build make

# Build Docker image
docker:
	docker build -t scenescape-controller-cpp .

# Run Docker container
docker-run:
	docker run --rm -it \
		-v /run/secrets:/run/secrets:ro \
		scenescape-controller-cpp \
		--restauth /run/secrets/controller.auth

# Help target
help:
	@echo "Available targets:"
	@echo "  build     - Build the project (default)"
	@echo "  clean     - Clean build artifacts"
	@echo "  install   - Install the binary"
	@echo "  test      - Run tests"
	@echo "  debug     - Build debug version"
	@echo "  format    - Format source code"
	@echo "  analyze   - Run static analysis"
	@echo "  docker    - Build Docker image"
	@echo "  docker-run - Run in Docker container"
	@echo "  help      - Show this help"
