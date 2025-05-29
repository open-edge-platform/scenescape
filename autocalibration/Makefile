# Makefile for building the autocalibration component

IMAGE=scenescape-camcalibration
VERSION:=$(shell cat ./version.txt)

# Set default target
.PHONY: default

default: Dockerfile
	env BUILDKIT_PROGRESS=plain \
	docker build $(REBUILDFLAGS) \
	  --build-arg http_proxy=$(http_proxy) \
	  --build-arg https_proxy=$(https_proxy) \
	  --build-arg no_proxy=$(no_proxy) \
	  --build-arg CERTDOMAIN=$(CERTDOMAIN) \
	  --build-arg USER_ID=$$UID \
	  --rm -t $(IMAGE):$(VERSION) .. -f ./Dockerfile \
	&& docker tag $(IMAGE):$(VERSION) $(IMAGE):latest

.PHONY: rebuild
rebuild:
	$(MAKE) REBUILDFLAGS="--no-cache"
