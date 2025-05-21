.PHONY: all help build build-common docker-build clean clean-common

MICROSERVICES := webserver controller database broker model-installer autocalibration percebro dlstreamer-pipeline-server interface

COMMON_DIR := common

all: docker-build

help:
	@echo "Available targets:"
	@echo "  build           - Build all microservice software packages"
	@echo "  build-common    - Build common libraries/tools"
	@echo "  docker-build    - Build all Docker images"
	@echo "  clean           - Clean all build artifacts"
	@echo "  help            - Show this help message"

build: build-common $(addsuffix -build,$(MICROSERVICES))

build-common:
	@-$(MAKE) -C $(COMMON_DIR) build

%-build: build-common
	@-$(MAKE) -C $* build

docker-build: $(addsuffix -docker-build,$(MICROSERVICES))

%-docker-build: build
	@-$(MAKE) -C $* docker-build

%-clean:
	@-$(MAKE) -C $* clean

clean: clean-common $(addsuffix -clean,$(MICROSERVICES))

clean-common:
	@-$(MAKE) -C $(COMMON_DIR) clean

# Add more orchestration targets as needed, e.g.:
# test, lint, deploy, etc.
