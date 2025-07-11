# Makefile for SceneScape Controller Go

.PHONY: all build clean test install docker fmt vet

# Go parameters
GOCMD = go
GOBUILD = $(GOCMD) build
GOCLEAN = $(GOCMD) clean
GOTEST = $(GOCMD) test
GOGET = $(GOCMD) get
GOMOD = $(GOCMD) mod

# Binary name and path
BINARY_NAME = controller
BINARY_UNIX = $(BINARY_NAME)_unix
CMD_PATH = ./cmd/controller

# Build flags
BUILD_FLAGS = -v
LDFLAGS = -w -s

# Default target
all: test build

# Tidy and download dependencies
deps:
	$(GOMOD) tidy
	$(GOMOD) download

# Build the application
build: deps
	$(GOBUILD) $(BUILD_FLAGS) -ldflags "$(LDFLAGS)" -o $(BINARY_NAME) $(CMD_PATH)

# Build for Linux
build-linux: deps
	CGO_ENABLED=1 GOOS=linux GOARCH=amd64 $(GOBUILD) $(BUILD_FLAGS) -ldflags "$(LDFLAGS)" -o $(BINARY_UNIX) $(CMD_PATH)

# Clean build artifacts
clean:
	$(GOCLEAN)
	rm -f $(BINARY_NAME)
	rm -f $(BINARY_UNIX)

# Run tests
test: deps
	$(GOTEST) -v ./...

# Run tests with coverage
test-coverage: deps
	$(GOTEST) -v -coverprofile=coverage.out ./...
	$(GOCMD) tool cover -html=coverage.out

# Format code
fmt:
	$(GOCMD) fmt ./...

# Run go vet
vet:
	$(GOCMD) vet ./...

# Run linter
lint:
	golangci-lint run

# Install dependencies
install-deps:
	$(GOGET) -u github.com/golangci/golangci-lint/cmd/golangci-lint

# Install the binary
install: build
	cp $(BINARY_NAME) /usr/local/bin/

# Build Docker image
docker:
	docker build -t scenescape-controller-go .

# Run Docker container
docker-run:
	docker run --rm -it \
		-v /run/secrets:/run/secrets:ro \
		scenescape-controller-go \
		--restauth /run/secrets/controller.auth

# Run the application locally
run: build
	./$(BINARY_NAME) --verbose

# Development build with debugging info
dev: deps
	$(GOBUILD) -gcflags="all=-N -l" -o $(BINARY_NAME) $(CMD_PATH)

# Cross-compilation targets
build-all: build-linux build-windows build-darwin

build-windows: deps
	CGO_ENABLED=0 GOOS=windows GOARCH=amd64 $(GOBUILD) $(BUILD_FLAGS) -ldflags "$(LDFLAGS)" -o $(BINARY_NAME).exe $(CMD_PATH)

build-darwin: deps
	CGO_ENABLED=0 GOOS=darwin GOARCH=amd64 $(GOBUILD) $(BUILD_FLAGS) -ldflags "$(LDFLAGS)" -o $(BINARY_NAME)_darwin $(CMD_PATH)

# Help target
help:
	@echo "Available targets:"
	@echo "  build        - Build the project (default with test)"
	@echo "  build-linux  - Build for Linux"
	@echo "  build-all    - Cross-compile for all platforms"
	@echo "  clean        - Clean build artifacts"
	@echo "  test         - Run tests"
	@echo "  test-coverage - Run tests with coverage report"
	@echo "  fmt          - Format source code"
	@echo "  vet          - Run go vet"
	@echo "  lint         - Run linter"
	@echo "  deps         - Download dependencies"
	@echo "  install      - Install binary to /usr/local/bin"
	@echo "  docker       - Build Docker image"
	@echo "  docker-run   - Run in Docker container"
	@echo "  run          - Run application locally"
	@echo "  dev          - Build with debugging info"
	@echo "  help         - Show this help"
