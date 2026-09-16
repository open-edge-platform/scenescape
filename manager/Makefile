# SPDX-FileCopyrightText: (C) 2021 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE = intel/scenescape-manager
TEST_IMAGE = intel/scenescape-manager-test
TARGET = scenescape-manager-runtime
TEST_TARGET = scenescape-manager-test
USES_SCENE_COMMON = yes
SHELL = /bin/bash
CERTDOMAIN = scenescape.intel.com
JSLIBDIR = backend/manager/static
CURL_FLAGS = --connect-timeout 5 --max-time 120 --retry 5 --retry-delay 0
FORCE_VAAPI ?= 0
THREEJS_VERSION = 168
SECRETSDIR ?= ./secrets

# Actual calculated OpenCV.js SHA256 sum as of 26.02.2026
EXPECTED_OPENCV_SHA256 = 19b46167b59efbef9cc3836264b0b657110833e4b1df84282004b8b3141c048d

include ../common.mk

# Bake the build commit into the Manager image for the About modal.
GIT_COMMIT ?= $(shell git -C $(CURDIR)/.. rev-parse HEAD 2>/dev/null || echo unknown)
EXTRA_BUILD_ARGS += --build-arg GIT_COMMIT=$(GIT_COMMIT)

default: build-image

.PHONY: ui-install ui-build
ui-install:
	cd frontend && npm ci

ui-build:
	# Sync canonical --ss-* tokens into Django static (pages must not need Node).
	cp -f frontend/src/tokens/ss-tokens.css backend/manager/static/css/tokens.css
ifndef SKIP_UI
	cd frontend && npm ci && npm run build
else
	@echo "SKIP_UI=1 — skipping manager UI build (tokens still synced)"
endif

build-image: ui-build jslibraries jsm-examples remove-symlink Dockerfile

.PHONY: test-build
test-build: test/geckodriver.tar.gz
	$(MAKE) IMAGE="$(TEST_IMAGE)" TARGET="$(TEST_TARGET)" EXTRA_BUILD_ARGS="--build-arg TEST_USER=$(shell id -u) --build-arg GIT_COMMIT=$(GIT_COMMIT)"

# The 'remove-symlink' target removes a potentially dangling symlink to prevent build failures.
remove-symlink:
	rm -f ./backend/manager/secrets.py

.PHONY: clean-assets
clean-assets:
	rm -rf $(JSLIBDIR)/assets $(JSLIBDIR)/bootstrap $(JSLIBDIR)/examples \
	  $(JSLIBDIR)/bootstrap-4.6.1-dist.zip $(JSLIBDIR)/bootstrap-icons-1.3.0.zip

define JSMEXAMPLES
fonts/helvetiker_regular.typeface.json \
jsm/controls/OrbitControls.js \
jsm/controls/TransformControls.js \
jsm/environments/RoomEnvironment.js \
jsm/webxr/XRControllerModelFactory.js \
jsm/geometries/TextGeometry.js \
jsm/helpers/VertexNormalsHelper.js \
jsm/helpers/ViewHelper.js \
jsm/interactive/HTMLMesh.js \
jsm/interactive/InteractiveGroup.js \
jsm/libs/draco/draco_encoder.js \
jsm/libs/fflate.module.js \
jsm/libs/ktx-parse.module.js \
jsm/libs/mikktspace.module.js \
jsm/libs/motion-controllers.module.js \
jsm/libs/lil-gui.module.min.js \
jsm/libs/stats.module.js \
jsm/libs/zstddec.module.js \
jsm/loaders/GLTFLoader.js \
jsm/loaders/FontLoader.js \
jsm/renderers/CSS2DRenderer.js \
jsm/utils/BufferGeometryUtils.js \
jsm/utils/SkeletonUtils.js \
jsm/utils/WorkerPool.js \
jsm/webxr/VRButton.js
endef

JSMEXAMPLES := $(value JSMEXAMPLES)

define axios-asset-recipe =
	URL=https://cdn.jsdelivr.net/npm/axios/dist && PKG=$$(basename $@) \
	  && echo "$${URL}/$${PKG}" >> $(BUILD_DIR)/$(IMAGE)-downloaded-deps.txt \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG} \
	  && $(verify-web-asset)
endef

# Catches HTML error pages, plain-text 404s, and JSON error bodies CDNs return with a 200 status.
ERROR_BODY_PATTERN = <html\|<!doctype\|^404\|^not found$$\|"error"\|cannot get /\|access denied

define verify-web-asset =
	if [ ! -s $@ ]; then \
	  echo "ERROR: $@ is empty or does not exist" && rm -f $@ && exit 1; \
	fi && \
	if head -c 200 $@ | tr '[:upper:]' '[:lower:]' | grep -q '$(ERROR_BODY_PATTERN)'; then \
	  echo "ERROR: $@ looks like an error page, not the expected content" && rm -f $@ && exit 1; \
	fi
endef

jsm-examples: $(JSMEXAMPLES)

# Verification is inlined here (not $(verify-web-asset)) because $@ is the example's
# relative path, not its output path under $(JSLIBDIR)/examples.
$(JSMEXAMPLES):
	$(eval RELPATH=$@)
	if [ ! -f $(JSLIBDIR)/examples/$@ ] ; then \
	  URL=https://cdn.jsdelivr.net/npm/three@0.$(THREEJS_VERSION).0/examples/$(RELPATH) \
	  && echo "$${URL}" >> $(BUILD_DIR)/$(IMAGE)-downloaded-deps.txt \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $(JSLIBDIR)/examples/$@ \
	  $${URL} \
	  && sed -i -e "s,'three','/static/assets/three.module.js'," $(JSLIBDIR)/examples/$@ \
	  && if [ ! -s $(JSLIBDIR)/examples/$@ ]; then echo "ERROR: $(JSLIBDIR)/examples/$@ is empty" && rm -f $(JSLIBDIR)/examples/$@ && exit 1; fi \
	  && if head -c 200 $(JSLIBDIR)/examples/$@ | tr '[:upper:]' '[:lower:]' | grep -q '$(ERROR_BODY_PATTERN)'; then echo "ERROR: $(JSLIBDIR)/examples/$@ looks like an error page" && rm -f $(JSLIBDIR)/examples/$@ && exit 1; fi; \
	fi


# Download Javascript libraries
jslibraries: \
  $(JSLIBDIR)/assets/jquery-3.6.0.min.js                     \
  $(JSLIBDIR)/assets/snap.svg-min.js                         \
  $(JSLIBDIR)/assets/tether.min.js                           \
  $(JSLIBDIR)/assets/imagesloaded.pkgd.min.js                \
  $(JSLIBDIR)/assets/mqtt.min.js                             \
  $(JSLIBDIR)/bootstrap/css/bootstrap-icons.css              \
  $(JSLIBDIR)/assets/glfx.min.js                             \
  $(JSLIBDIR)/bootstrap/js/bootstrap.js                      \
  $(JSLIBDIR)/bootstrap/css/fonts/bootstrap-icons.woff       \
  $(JSLIBDIR)/assets/three.module.js                         \
  $(JSLIBDIR)/assets/ProjectedMaterial.module.js             \
  $(JSLIBDIR)/assets/opencv.js                               \
  $(JSLIBDIR)/assets/axios.min.js                            \
  $(JSLIBDIR)/assets/axios.min.js.map                        \
  $(JSLIBDIR)/assets/doxygen-awesome.css                     \
  $(JSLIBDIR)/assets/jszip.min.js                            \
  $(JSLIBDIR)/assets/socket.io.min.js                        \

$(JSLIBDIR)/assets/socket.io.min.js:
	URL=https://cdn.socket.io/4.5.4 && PKG=$$(basename $@) \
	  && echo "$${URL}/$${PKG}" >> $(BUILD_DIR)/$(IMAGE)-downloaded-deps.txt \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG} \
	  && $(verify-web-asset)

$(JSLIBDIR)/assets/jquery-3.6.0.min.js:
	URL=https://code.jquery.com && PKG=$$(basename $@) \
	  && echo "$${URL}/$${PKG}" >> $(BUILD_DIR)/$(IMAGE)-downloaded-deps.txt \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG} \
	  && $(verify-web-asset)

$(JSLIBDIR)/assets/snap.svg-min.js:
	URL=https://raw.githubusercontent.com/adobe-webplatform/Snap.svg/master/dist && PKG=$$(basename $@) \
	  && echo "$${URL}/$${PKG}" >> $(BUILD_DIR)/$(IMAGE)-downloaded-deps.txt \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG} \
	  && $(verify-web-asset)

$(JSLIBDIR)/assets/tether.min.js:
	URL=https://cdnjs.cloudflare.com/ajax/libs/tether/1.4.7/js && PKG=$$(basename $@) \
	  && echo "$${URL}/$${PKG}" >> $(BUILD_DIR)/$(IMAGE)-downloaded-deps.txt \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG} \
	  && $(verify-web-asset)

$(JSLIBDIR)/assets/imagesloaded.pkgd.min.js:
	URL=https://cdnjs.cloudflare.com/ajax/libs/jquery.imagesloaded/4.1.4 \
	  && PKG=$$(basename $@) \
	  && echo "$${URL}/$${PKG}" >> $(BUILD_DIR)/$(IMAGE)-downloaded-deps.txt \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG} \
	  && $(verify-web-asset)

$(JSLIBDIR)/assets/mqtt.min.js:
	URL=https://cdnjs.cloudflare.com/ajax/libs/mqtt/4.3.5 && PKG=$$(basename $@) \
	  && echo "$${URL}/$${PKG}" >> $(BUILD_DIR)/$(IMAGE)-downloaded-deps.txt \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG} \
	  && $(verify-web-asset)

$(JSLIBDIR)/assets/jszip.min.js:
	URL=https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1 && PKG=$$(basename $@) \
	  && echo "$${URL}/$${PKG}" >> $(BUILD_DIR)/$(IMAGE)-downloaded-deps.txt \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG} \
	  && $(verify-web-asset)

$(JSLIBDIR)/assets/axios.min.js:
	$(call axios-asset-recipe)

$(JSLIBDIR)/assets/axios.min.js.map:
	$(call axios-asset-recipe)

$(JSLIBDIR)/assets/glfx.min.js:
	URL=https://cdn.jsdelivr.net/npm/glfx@0.0.4 && PKG=$$(basename $@) \
	  && echo "$${URL}/$${PKG}" >> $(BUILD_DIR)/$(IMAGE)-downloaded-deps.txt \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG} \
	  && $(verify-web-asset)

$(JSLIBDIR)/bootstrap-4.6.1-dist.zip:
	VERSION=$$(echo $@ | sed -E -e 's/.*bootstrap-([0-9]+[.][0-9]+[.][0-9]+)-.*/\1/') \
	  URL=https://github.com/twbs/bootstrap/releases/download/v$${VERSION} \
	  PKG=$$(basename $@) \
	  && echo "$${URL}/$${PKG}" >> $(BUILD_DIR)/$(IMAGE)-downloaded-deps.txt \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG} \
	  && $(verify-web-asset)

$(JSLIBDIR)/bootstrap-icons-1.3.0.zip:
	URL=https://github.com/twbs/icons/releases/download/v1.3.0 && PKG=$$(basename $@) \
	  && echo "$${URL}/$${PKG}" >> $(BUILD_DIR)/$(IMAGE)-downloaded-deps.txt \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG} \
	  && $(verify-web-asset)

$(JSLIBDIR)/bootstrap/css/bootstrap-icons.css: $(JSLIBDIR)/bootstrap/css
	URL=https://cdn.jsdelivr.net/npm/bootstrap-icons@1.3.0/font && PKG=$$(basename $@) \
	  && echo "$${URL}/$${PKG}" >> $(BUILD_DIR)/$(IMAGE)-downloaded-deps.txt \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG} \
	  && $(verify-web-asset)

$(JSLIBDIR)/bootstrap/js/bootstrap.js: $(JSLIBDIR)/bootstrap-4.6.1-dist.zip
	BOOTSTRAPDIR=$$(dirname $(dir $@)) \
	  DISTROOT=$$(basename $< .zip) \
	  ; mkdir -p $${BOOTSTRAPDIR} \
		&& unzip -u -d $${BOOTSTRAPDIR} $< \
		&& rsync -aP --remove-source-files $${BOOTSTRAPDIR}/$${DISTROOT}/* $${BOOTSTRAPDIR}/. \
		&& rmdir $${BOOTSTRAPDIR}/$${DISTROOT}/* $${BOOTSTRAPDIR}/$${DISTROOT}
	touch $@

$(JSLIBDIR)/bootstrap/css/fonts/bootstrap-icons.woff: $(JSLIBDIR)/bootstrap-icons-1.3.0.zip
	FONTDIR=$(dir $@) \
	 ; mkdir -p $${FONTDIR} \
	   && unzip -u -d $${FONTDIR} -j $< \
			bootstrap-icons-1.3.0/fonts/\*
	touch $@

$(JSLIBDIR)/bootstrap/css: $(JSLIBDIR)/bootstrap/css/fonts/bootstrap-icons.woff

$(JSLIBDIR)/assets/three.module.js:
	URL=https://cdn.jsdelivr.net/npm/three@0.$(THREEJS_VERSION).0/build && PKG=$$(basename $@) \
	  && echo "$${URL}/$${PKG}" >> $(BUILD_DIR)/$(IMAGE)-downloaded-deps.txt \
	  && curl $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG} \
	  && $(verify-web-asset)

$(JSLIBDIR)/assets/ProjectedMaterial.module.js:
	URL=https://unpkg.com/three-projected-material/build && PKG=$$(basename $@) \
	  && echo "$${URL}/$${PKG}" >> $(BUILD_DIR)/$(IMAGE)-downloaded-deps.txt \
	  && curl $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG} \
	  &&  sed "s,'three','/static/assets/three.module.js'," $@ > temp.js && mv temp.js $@ \
	  && $(verify-web-asset)

# Using CDN as the official https://docs.opencv.org/4.10.0/opencv.js return 403 and seem to require a headless browser to download
$(JSLIBDIR)/assets/opencv.js:
	URL=https://cdn.jsdelivr.net/npm/@techstark/opencv-js@4.10.0-release.1/dist/opencv.js \
	  && echo "$${URL}" >> $(BUILD_DIR)/$(IMAGE)-downloaded-deps.txt \
	  && curl $(CURL_FLAGS) --location --create-dirs --output $@ $${URL} \
	  && ACTUAL_SHA256=$$(sha256sum $@ | awk '{print $$1}') \
	  && [ "$${ACTUAL_SHA256}" = "$(EXPECTED_OPENCV_SHA256)" ] \
	     || (echo "ERROR: SHA256 mismatch for $@: expected=$(EXPECTED_OPENCV_SHA256) actual=$${ACTUAL_SHA256}" && rm -f $@ && exit 1)

$(JSLIBDIR)/assets/doxygen-awesome.css:
	URL=https://raw.githubusercontent.com/jothepro/doxygen-awesome-css/main && PKG=$$(basename $@) \
	  && echo "$${URL}/$${PKG}" >> $(BUILD_DIR)/$(IMAGE)-downloaded-deps.txt \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG} \
	  && $(verify-web-asset)

django-secrets: $(SECRETSDIR)/django/secrets.py

# Generate secret keys for Django application
$(SECRETSDIR)/django/secrets.py:
	mkdir -p $(SECRETSDIR)/django
	echo -n SECRET_KEY= > $@
	python3 -c 'import secrets; print("\x27" + "".join([secrets.choice("abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)") for i in range(50)]) + "\x27")' >> $@
	echo "DATABASE_PASSWORD='$${DBPASS:-$$(openssl rand -base64 12)}'" >> $@
	chmod 0644 $@

test/geckodriver.tar.gz:
	@echo "Downloading geckodriver..."
	@set -e \
		; BASE_URL=https://github.com/mozilla/geckodriver/releases \
		; GVERSION=v0.36.0 \
		; mkdir -p test \
		; curl -fSL \
			"$${BASE_URL}/download/$${GVERSION}/geckodriver-$${GVERSION}-linux64.tar.gz" \
			--output "test/geckodriver.tar.gz"
