# Copyright (C) 2021-2025 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

SHELL=/bin/bash
IMAGE=scenescape
VERSION:=$(shell cat ../version.txt)
CERTDOMAIN=scenescape.intel.com
SECRETSDIR=../secrets
MQTTUSERS="percebro.auth=cameras controller.auth=scenectrl browser.auth=webuser calibration.auth=calibration"
AUTHFILES=$(addprefix $(SECRETSDIR)/,$(shell echo $(MQTTUSERS) | sed -e 's/=[^ ]*//g'))
CURL_FLAGS=--connect-timeout 5 --max-time 120 --retry 5 --retry-delay 0
FORCE_VAAPI ?= 0
THREEJS_VERSION=168
IMAGES := $(IMAGE)-broker $(IMAGE)-model-installer
BROKER_LOG_FILE=$(BUILD_DIR)/$(IMAGE)-broker.log
MODEL_INSTALLER_LOG_FILE=$(BUILD_DIR)/$(IMAGE)-model-installer.log
BUILD_DIR ?= $(PWD)/build
$(shell mkdir -p $(BUILD_DIR))

# ANSI color codes
RED    := \033[0;31m
GREEN  := \033[0;32m
YELLOW := \033[0;33m
RESET  := \033[0m

default: broker model-installer-img install-models secrets

interface: Dockerfile-interface firefox-profile.tar geckodriver.tar.gz
	env BUILDKIT_PROGRESS=plain \
	  docker build $(REBUILDFLAGS) -f $< \
	    --build-arg http_proxy=$(http_proxy) \
	    --build-arg https_proxy=$(https_proxy) \
	    --build-arg no_proxy=$(no_proxy) \
	    --rm -t $(IMAGE)-interface:$(VERSION) .. -f ./Dockerfile-interface \
	&& docker tag $(IMAGE)-interface:$(VERSION) $(IMAGE)-interface:latest

broker: Dockerfile-broker
	@echo -e "$(GREEN)------- STARTING BUILD OF IMAGE: $(IMAGE)-broker:$(VERSION) -------$(RESET)"
	@{ \
	    set -e; \
	    set -o pipefail; \
	    if env BUILDKIT_PROGRESS=plain docker build $(REBUILDFLAGS) \
	        --build-arg http_proxy=$(http_proxy) \
	        --build-arg https_proxy=$(https_proxy) \
	        --build-arg no_proxy=$(no_proxy) \
	        --rm -t $(IMAGE)-broker:$(VERSION) \
	        -f ./Dockerfile-broker .. 2>&1 | tee $(BROKER_LOG_FILE); \
	    then \
	        docker tag $(IMAGE)-broker:$(VERSION) $(IMAGE)-broker:latest; \
	        echo -e "$(GREEN)------- BUILD OF IMAGE $(IMAGE)-broker:$(VERSION) COMPLETED SUCCESSFULLY -------$(RESET)"; \
	        echo "Log file created at $(BROKER_LOG_FILE)"; \
	    else \
	        echo -e "$(RED)------- BUILD OF IMAGE $(IMAGE)-broker:$(VERSION) FAILED. CHECK $(BROKER_LOG_FILE) FOR DETAILS. -------$(RESET)"; \
	        grep --color=auto -i -r "^error" $(BROKER_LOG_FILE); \
	        exit 1; \
	    fi \
	}

model-installer-img: Dockerfile-model-installer
	@echo -e "$(GREEN)------- STARTING BUILD OF IMAGE: $(IMAGE)-model-installer:$(VERSION) -------$(RESET)"
	@{ \
	    set -e; \
	    set -o pipefail; \
	    if env BUILDKIT_PROGRESS=plain docker build $(REBUILDFLAGS) \
	        --build-arg http_proxy=$(http_proxy) \
	        --build-arg https_proxy=$(https_proxy) \
	        --build-arg no_proxy=$(no_proxy) \
	        --rm -t $(IMAGE)-model-installer:$(VERSION) \
	        -f ./Dockerfile-model-installer .. 2>&1 | tee $(MODEL_INSTALLER_LOG_FILE); \
	    then \
	        docker tag $(IMAGE)-model-installer:$(VERSION) $(IMAGE)-model-installer:latest; \
	        echo -e "$(GREEN)------- BUILD OF IMAGE $(IMAGE)-model-installer:$(VERSION) COMPLETED SUCCESSFULLY -------$(RESET)"; \
	        echo "Log file created at $(MODEL_INSTALLER_LOG_FILE)"; \
	    else \
	        echo -e "$(RED)------- BUILD OF IMAGE $(IMAGE)-model-installer:$(VERSION) FAILED. CHECK $(MODEL_INSTALLER_LOG_FILE) FOR DETAILS. -------$(RESET)"; \
	        grep --color=auto -i -r "^error" $(MODEL_INSTALLER_LOG_FILE); \
	        exit 1; \
	    fi \
	}

sources: Dockerfile-sources
	env BUILDKIT_PROGRESS=plain \
	  docker build $(REBUILDFLAGS) -f $< \
	    --build-arg http_proxy=$(http_proxy) \
	    --build-arg https_proxy=$(https_proxy) \
	    --build-arg no_proxy=$(no_proxy) \
	    --rm -t $(IMAGE)-sources:$(VERSION) .. -f ./Dockerfile-sources \
	&& docker tag $(IMAGE)-sources:$(VERSION) $(IMAGE)-sources:latest

# To force a complete clean build, do:
#   make rebuild
rebuild:
	make -C $(DOCSDIR) clean
	IMAGES=$$(egrep -i '^FROM' Dockerfile* | awk '{print $$2}' \
	    | grep -v $(IMAGE) | sort -u) \
	  ; for i in $$IMAGES ; do docker pull $$i ; done
	make REBUILDFLAGS="--no-cache"

install-models: model-installer-img \
	; MODELS=--$${MODELS:-default} \
	; PRECISIONS=$${PRECISIONS:-FP32} \
	; cd .. \
	; mkdir -p models \
	; APPDIR=/workspace \
	; HOSTDIR=$$PWD \
	; IMAGE=$(IMAGE)-model-installer:latest \
	; docker run --rm -v $$HOSTDIR:$$APPDIR:z \
	             -e HTTP_PROXY=$$http_proxy \
	             -e HTTPS_PROXY=$$https_proxy \
	             -e http_proxy=$$http_proxy \
	             -e https_proxy=$$https_proxy \
	             -u $$UID \
	             -l user=$$USER $$IMAGE \
	             /workspace/docker/install-omz-models $$MODELS --precisions $$PRECISIONS

../docker-compose.yml: ../sample_data/docker-compose-example.yml
	sed -e "s/image: scenescape\(-.*\)\?/image: $(IMAGE)\1:$(VERSION)/" $< > $@

secrets: certificate django-secrets authfiles
	chmod go-rwx $(SECRETSDIR)

certificate:
	CERTDOMAIN=$(CERTDOMAIN) make -C ../certificates

geckodriver.tar.gz:
	set -e \
	  ; BASE_URL=https://github.com/mozilla/geckodriver/releases \
	  ; GVERSION=$$(curl -sL -o /dev/null -w '%{url_effective}' \
	                "$${BASE_URL}/latest" \
	                | sed -e 's,.*/,,') \
	  ; curl --output $@ \
	          -sL \
	         "$${BASE_URL}/download/$${GVERSION}/geckodriver-$${GVERSION}-linux64.tar.gz" \
	  ;

django-secrets: $(SECRETSDIR)/django/secrets.py

$(SECRETSDIR)/django/secrets.py:
	mkdir -p $(SECRETSDIR)/django
	echo -n SECRET_KEY= > $@
	python3 -c 'import secrets; print("\x27" + "".join([secrets.choice("abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)") for i in range(50)]) + "\x27")' >> $@
	echo "DATABASE_PASSWORD='$${DBPASS:-$$(openssl rand -base64 12)}'" >> $@
	chmod 0600 $@

%.auth:
	set -e; \
	MQTTUSERS=$(MQTTUSERS); \
	for uid in $${MQTTUSERS}; do \
	    JSONFILE=$${uid%=*}; \
	    USERPASS=$${uid##*=}; \
	    case $${USERPASS} in \
	        *:* ) ;; \
	        * ) USERPASS=$${USERPASS}:$$(openssl rand -base64 12); \
	    esac; \
	    USER=$${USERPASS%:*}; \
	    PASS=$${USERPASS##*:}; \
	    if [ $(SECRETSDIR)/$${JSONFILE} = $@ ]; then \
	        echo '{"user": "'$${USER}'", "password": "'$${PASS}'"}' > $@; \
	        chmod 0600 $@; \
	    fi; \
	done

authfiles: $(AUTHFILES)

.PHONY: list-dependencies
list-dependencies:
	@mkdir -p $(BUILD_DIR)
	@for image in $(IMAGES); do \
		if [[ -z $$(docker images | grep "^$$image" | grep $(VERSION)) ]]; then \
		  echo "Error: the image $$image:$(VERSION) does not exist! Cannot generate dependency list."; \
		  echo "Please build the image first."; \
		  exit 1; \
		fi; \
		RUNTIME_OS_IMAGE="ubuntu:22.04"; \
		if [ "$$image" = "scenescape-model-installer" ]; then \
			RUNTIME_OS_IMAGE="openvino/ubuntu22_dev:2024.6.0"; \
		elif [ "$$image" = "scenescape-broker" ]; then \
			RUNTIME_OS_IMAGE="debian:stable-slim"; \
		fi; \
		docker run --rm $$RUNTIME_OS_IMAGE dpkg -l | awk '{ print $$2, $$3, $$4 }' > $(BUILD_DIR)/system-packages.txt || echo "Failed to run dpkg on $$RUNTIME_OS_IMAGE"; \
		docker run --rm --entrypoint dpkg $$image:$(VERSION) -l | awk '$$1 == "ii" { print $$2, $$3, $$4 }' > $(BUILD_DIR)/$$image-packages.txt || echo "Failed to run dpkg on $$image:$(VERSION)"; \
		grep -Fxv -f $(BUILD_DIR)/system-packages.txt $(BUILD_DIR)/$$image-packages.txt > $(BUILD_DIR)/$$image-apt-deps.txt; \
		rm -rf $(BUILD_DIR)/system-packages.txt $(BUILD_DIR)/$$image-packages.txt; \
		echo "OS dependencies listed in $(BUILD_DIR)/$$image-apt-deps.txt"; \
		if [ "$$image" != "scenescape-broker" ]; then \
			docker run --rm $$RUNTIME_OS_IMAGE pip freeze --all > $(BUILD_DIR)/base-pip-packages.txt || echo "Failed to run pip on $$RUNTIME_OS_IMAGE"; \
			docker run --rm --entrypoint pip $$image:$(VERSION) freeze --all > $(BUILD_DIR)/$$image-pip-packages.txt || echo "Failed to run pip on $$image:$(VERSION)"; \
			grep -Fxv -f $(BUILD_DIR)/base-pip-packages.txt $(BUILD_DIR)/$$image-pip-packages.txt > $(BUILD_DIR)/$$image-pip-deps.txt; \
			rm -rf $(BUILD_DIR)/base-pip-packages.txt $(BUILD_DIR)/$$image-pip-packages.txt; \
			echo "Python dependencies listed in $(BUILD_DIR)/$$image-pip-deps.txt"; \
		fi; \
	done
