# Makefile Standards for SceneScape

## Organization

### Directory Structure

Each service has its own Makefile:

```
scenescape/
├── Makefile              # Root orchestrator
├── common.mk             # Shared build logic
├── controller/
│   └── Makefile          # Controller-specific targets
├── manager/
│   └── Makefile          # Manager-specific targets
└── tests/
    ├── Makefile          # Test orchestrator
    └── Makefile.sscape   # SceneScape-specific test targets
```

### Common.mk Inclusion

Service Makefiles include `common.mk`:

```makefile
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

include ../common.mk

# Service-specific variables and targets
IMAGE_NAME := scenescape-controller
```

## Variables

### Naming Conventions

- **User-configurable**: `UPPER_CASE` with `?=` (default if not set)
- **Internal/derived**: `UPPER_CASE` with `:=` (immediate expansion)
- **Shell commands**: Use `$(shell ...)` for command output

```makefile
# User-configurable (can override)
JOBS ?= $(shell nproc)
BUILD_DIR ?= build
DOCKER_REGISTRY ?= localhost

# Internal/derived (computed once)
VERSION := $(shell cat version.txt)
TIMESTAMP := $(shell date +%Y%m%d-%H%M%S)
IMAGE_TAG := $(IMAGE_NAME):$(VERSION)

# Avoid recursive expansion (=) for expensive operations
```

### Assignment Operators

```makefile
# ?= Set if not already set (user can override)
PYTHON ?= python3

# := Immediate expansion (evaluated once)
CURRENT_DIR := $(shell pwd)

# = Recursive expansion (evaluated every use - use sparingly)
DYNAMIC = $(shell date)

# += Append to existing value
CFLAGS += -Wall -Wextra
```

### Common Variables

```makefile
# Directories
BUILD_DIR ?= build
SRC_DIR := src
TEST_DIR := tests

# Versioning
VERSION := $(shell cat version.txt)
BUILD_NUMBER ?= dev

# Docker
COMPOSE_PROJECT_NAME ?= scenescape
DOCKER_BUILDKIT ?= 1

# Tools
PYTHON ?= python3
DOCKER ?= docker
DOCKER_COMPOSE ?= docker compose

# Parallel builds
JOBS ?= $(shell nproc)
MAKEFLAGS += -j$(JOBS)
```

## Code Style

### Indentation

- Use **tabs** for indentation (Makefile standard)
- Commands in recipes must be indented with tabs

### Line Length

- Target: 80-100 characters for readability
- Use `\` for line continuation in long commands

## Phony Targets

### Declaration

Always declare phony targets:

```makefile
.PHONY: all build clean test help

all: build

build:
	@echo "Building..."

clean:
	rm -rf $(BUILD_DIR)

test:
	pytest $(TEST_DIR)

help:
	@echo "Available targets:"
	@echo "  build  - Build all components"
	@echo "  clean  - Remove build artifacts"
	@echo "  test   - Run tests"
```

### Standard Targets

Common phony targets in SceneScape:

```makefile
.PHONY: build build-core build-all build-experimental
.PHONY: rebuild rebuild-core
.PHONY: clean clean-secrets clean-build
.PHONY: test unit-tests functional-tests
.PHONY: lint lint-python lint-shell
.PHONY: install install-models
.PHONY: help
```

## Target Patterns

### Silent Commands

Use `@` prefix to suppress echo:

```makefile
build:
	@echo "Building $(IMAGE_NAME)..."
	docker build -t $(IMAGE_TAG) .
	@echo "Build complete"
```

### Error Handling

Use `-` prefix to ignore errors:

```makefile
clean:
	-rm -rf $(BUILD_DIR)     # Continue even if directory doesn't exist
	-docker rmi $(IMAGE_TAG) # Continue if image doesn't exist
```

### Sequential Execution

Use `;` or `&&` for multi-line shell commands:

```makefile
# Each line is a separate shell
install:
	cd $(SRC_DIR)
	pip install -r requirements.txt  # Wrong! Different shell

# Correct - same shell
install:
	cd $(SRC_DIR) && \
	pip install -r requirements.txt

# Or use semicolon
install:
	cd $(SRC_DIR); pip install -r requirements.txt
```

## Dependencies

### Prerequisites

```makefile
# Target depends on other targets
build: check-version validate-config
	docker build -t $(IMAGE_TAG) .

check-version:
	@test -f version.txt || (echo "version.txt not found" && exit 1)

validate-config:
	@echo "Validating configuration..."
```

### Order-Only Prerequisites

```makefile
# Create directory only if it doesn't exist (don't rebuild if timestamp changes)
build: | $(BUILD_DIR)
	docker build -t $(IMAGE_TAG) .

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)
```

### Wildcard Dependencies

```makefile
# Rebuild if any source file changes
build: $(wildcard src/**/*.py)
	docker build -t $(IMAGE_TAG) .
```

## Parallel Builds

### Job Control

```makefile
# Set parallel jobs
JOBS ?= $(shell nproc)
MAKEFLAGS += -j$(JOBS)

# Force sequential for specific targets
.NOTPARALLEL: sequential-target

sequential-target:
	command1
	command2
```

### Common.mk Pattern

```makefile
# common.mk - Shared parallel build logic
.PHONY: build-images
build-images: $(IMAGE_FOLDERS)
	@echo "All images built"

# Each image folder builds in parallel
$(IMAGE_FOLDERS):
	$(MAKE) -C $@ build
```

## Docker Integration

### Build Patterns

```makefile
# Standard Docker build
build:
	docker build \
		--build-arg VERSION=$(VERSION) \
		--build-arg BUILD_DATE=$(shell date -u +'%Y-%m-%dT%H:%M:%SZ') \
		-t $(IMAGE_TAG) \
		-f Dockerfile \
		.

# BuildKit with progress
build-verbose:
	DOCKER_BUILDKIT=1 BUILDKIT_PROGRESS=plain \
	docker build -t $(IMAGE_TAG) .
```

### Docker Compose

```makefile
# Start services
up:
	docker compose up -d

# Stop services
down:
	docker compose down

# Rebuild and restart
restart: down build up

# View logs
logs:
	docker compose logs -f $(SERVICE)
```

### Multi-stage Builds

```makefile
# Build dependencies separately
build-deps:
	docker build \
		--target dependencies \
		-t $(IMAGE_NAME)-deps:$(VERSION) \
		.

# Build final image
build: build-deps
	docker build \
		--cache-from $(IMAGE_NAME)-deps:$(VERSION) \
		-t $(IMAGE_TAG) \
		.
```

## Testing Targets

### Test Organization

```makefile
.PHONY: test unit-tests functional-tests integration-tests

# Run all tests
test: unit-tests functional-tests

# Unit tests
unit-tests:
	pytest $(TEST_DIR)/unit -v

# Functional tests (requires running containers)
functional-tests:
	pytest $(TEST_DIR)/functional -v --tb=short

# Integration tests
integration-tests:
	pytest $(TEST_DIR)/integration -v -s
```

### Test Configuration

```makefile
# Test with specific Python
PYTHON ?= python3
PYTEST := $(PYTHON) -m pytest

# Coverage
test-coverage:
	$(PYTEST) --cov=src --cov-report=html --cov-report=term

# Specific test
test-one:
	$(PYTEST) $(TEST_DIR)/$(TEST_FILE) -v -s
```

## Linting

### Dockerfile Linting

- **Linter**: hadolint
- **Command**:
  ```bash
  make lint-dockerfile    # Lint all Dockerfiles
  ```

### Multi-language

```bash
make lint-all             # Run all linters (Python, Shell, JS, Dockerfiles)
```

## Color Output

### ANSI Colors

```makefile
# Define color codes
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[0;33m
BLUE := \033[0;34m
RESET := \033[0m

# Use in targets
build:
	@echo "$(GREEN)Building $(IMAGE_NAME)...$(RESET)"
	docker build -t $(IMAGE_TAG) .
	@echo "$(GREEN)Build complete$(RESET)"

error:
	@echo "$(RED)Error: Build failed$(RESET)"
	exit 1
```

### Progress Indicators

```makefile
build-all:
	@echo "$(BLUE)Building core services...$(RESET)"
	$(MAKE) build-core
	@echo "$(GREEN)✓ Core services built$(RESET)"
	@echo "$(BLUE)Building experimental services...$(RESET)"
	$(MAKE) build-experimental
	@echo "$(GREEN)✓ All services built$(RESET)"
```

## Common Patterns

### Version Management

```makefile
# Read from file
VERSION := $(shell cat version.txt)

# Validate version format
check-version:
	@echo "Version: $(VERSION)"
	@echo $(VERSION) | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+' || \
		(echo "Invalid version format" && exit 1)

# Tag image with version
tag-version:
	docker tag $(IMAGE_NAME):latest $(IMAGE_NAME):$(VERSION)
```

### Dependency Management

```makefile
# Generate dependency list
deps:
	pip list --format=freeze > $(BUILD_DIR)/dependencies.txt

# Check for outdated packages
check-deps:
	pip list --outdated

# Update dependencies
update-deps:
	pip install --upgrade -r requirements.txt
```

### Clean Targets

```makefile
.PHONY: clean clean-build clean-pyc clean-test clean-all

clean: clean-build clean-pyc clean-test

clean-build:
	rm -rf $(BUILD_DIR)
	rm -rf dist
	rm -rf *.egg-info

clean-pyc:
	find . -type f -name '*.pyc' -delete
	find . -type d -name __pycache__ -delete

clean-test:
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -f .coverage

clean-all: clean
	docker system prune -af
```

### Installation Targets

```makefile
.PHONY: install install-dev install-test

install:
	pip install -r requirements-runtime.txt

install-dev: install
	pip install -r requirements-dev.txt

install-test: install-dev
	pip install -r requirements-test.txt
```

## Help Target

### Auto-generated Help

```makefile
.PHONY: help

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'

# Targets with help text
build: ## Build Docker image
	docker build -t $(IMAGE_TAG) .

test: ## Run tests
	pytest $(TEST_DIR)

clean: ## Remove build artifacts
	rm -rf $(BUILD_DIR)
```

### Categorized Help

```makefile
help:
	@echo "$(BLUE)SceneScape Makefile$(RESET)"
	@echo ""
	@echo "$(YELLOW)Build targets:$(RESET)"
	@echo "  build              - Build core services"
	@echo "  build-all          - Build all services"
	@echo "  rebuild            - Clean and rebuild"
	@echo ""
	@echo "$(YELLOW)Test targets:$(RESET)"
	@echo "  test               - Run all tests"
	@echo "  unit-tests         - Run unit tests"
	@echo "  functional-tests   - Run functional tests"
	@echo ""
	@echo "$(YELLOW)Clean targets:$(RESET)"
	@echo "  clean              - Remove build artifacts"
	@echo "  clean-all          - Remove all generated files"
```

## Error Handling

### Checking Prerequisites

```makefile
check-docker:
	@which docker > /dev/null || \
		(echo "$(RED)Error: docker not found$(RESET)" && exit 1)

check-compose:
	@docker compose version > /dev/null 2>&1 || \
		(echo "$(RED)Error: docker compose not available$(RESET)" && exit 1)

build: check-docker check-compose
	docker compose build
```

### Validating Environment

```makefile
check-env:
	@test -n "$(SUPASS)" || \
		(echo "$(RED)Error: SUPASS not set$(RESET)" && exit 1)
	@test -n "$(DATABASE_PASSWORD)" || \
		(echo "$(RED)Error: DATABASE_PASSWORD not set$(RESET)" && exit 1)

deploy: check-env
	docker compose up -d
```

## Anti-Patterns to Avoid

❌ **Don't use shell loops in Make**:

```makefile
# Bad - inefficient
build:
	for dir in controller manager; do \
		$(MAKE) -C $$dir build; \
	done

# Good - use Make's parallel execution
SERVICES := controller manager
build: $(SERVICES)

$(SERVICES):
	$(MAKE) -C $@ build
```

❌ **Don't hardcode paths**:

```makefile
# Bad
build:
	docker build -t scenescape-controller:2026.0.0 controller/

# Good
VERSION := $(shell cat version.txt)
build:
	docker build -t $(IMAGE_NAME):$(VERSION) $(IMAGE_DIR)/
```

❌ **Don't ignore errors silently**:

```makefile
# Bad - hides failures
test:
	-pytest $(TEST_DIR)

# Good - fail on error
test:
	pytest $(TEST_DIR)
```

❌ **Don't use recursive assignment for commands**:

```makefile
# Bad - runs date every time TIMESTAMP is used
TIMESTAMP = $(shell date +%s)

# Good - runs once
TIMESTAMP := $(shell date +%s)
```

## Performance Tips

### Minimize Shell Calls

```makefile
# Slower - multiple shell invocations
VERSION = $(shell cat version.txt)
BUILD_DATE = $(shell date)

# Faster - one invocation
METADATA := $(shell echo "$(shell cat version.txt) $(shell date)")
```

### Use .ONESHELL for Multi-line Commands

```makefile
.ONESHELL:
deploy:
	cd deployment
	./configure.sh
	./deploy.sh
```

### Avoid Redundant Prerequisites

```makefile
# Inefficient - rebuilds unnecessarily
build: clean
	docker build -t $(IMAGE_TAG) .

# Better - clean separately when needed
build:
	docker build -t $(IMAGE_TAG) .

rebuild: clean build
```

## Documentation

### Inline Comments

```makefile
# Build the controller service Docker image
# Requires: Docker, version.txt
# Outputs: controller image tagged with version
build-controller:
	docker build \
		--build-arg VERSION=$(VERSION) \
		-t scenescape-controller:$(VERSION) \
		controller/
```

### Target Descriptions

```makefile
# Build targets with ## comments for help
build-core: ## Build core services (controller, manager, autocalibration)
	$(MAKE) $(CORE_IMAGE_FOLDERS)

build-all: ## Build all services including experimental
	$(MAKE) $(IMAGE_FOLDERS) $(EXPERIMENTAL_FOLDERS)
```

## Testing

### Test Makefiles

```makefile
# Dry run to see commands
make -n build

# Debug Make variables
make build --debug=v

# Print specific variable
make print-VERSION

print-%:
	@echo '$*=$($*)'
```
