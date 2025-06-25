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

IMAGE = scenescape-manager
RUNTIME_OS_IMAGE = ubuntu:22.04
TARGET = manager-runtime
SHELL = /bin/bash
CERTDOMAIN = scenescape.intel.com
JSLIBDIR = src/static
CURL_FLAGS = --connect-timeout 5 --max-time 120 --retry 5 --retry-delay 0
FORCE_VAAPI ?= 0
THREEJS_VERSION = 168
SECRETSDIR ?= ./secrets

include ../common.mk

default: build-image

build-image: jslibraries jsm-examples Dockerfile

.PHONY: test-build
test-build: test/geckodriver.tar.gz
	$(MAKE) IMAGE="scenescape-manager-test" TARGET="manager-test"

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
jsm/utils/BufferGeometryUtils.js \
jsm/utils/SkeletonUtils.js \
jsm/utils/WorkerPool.js \
jsm/webxr/VRButton.js
endef

JSMEXAMPLES := $(value JSMEXAMPLES)

define axios-asset-recipe =
	URL=https://cdn.jsdelivr.net/npm/axios/dist && PKG=$$(basename $@) \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG}
endef

jsm-examples: $(JSMEXAMPLES)

$(JSMEXAMPLES):
	$(eval RELPATH=$@)
	if [ ! -f $(JSLIBDIR)/examples/$@ ] ; then \
	  curl -f $(CURL_FLAGS) --location --create-dirs --output $(JSLIBDIR)/examples/$@ \
	  https://cdn.jsdelivr.net/npm/three@0.$(THREEJS_VERSION).0/examples/$(RELPATH) \
	  && sed -i -e "s,'three','/static/assets/three.module.js'," $(JSLIBDIR)/examples/$@; \
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

$(JSLIBDIR)/assets/jquery-3.6.0.min.js:
	URL=https://code.jquery.com && PKG=$$(basename $@) \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG}

$(JSLIBDIR)/assets/snap.svg-min.js:
	URL=https://raw.githubusercontent.com/adobe-webplatform/Snap.svg/master/dist && PKG=$$(basename $@) \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG}

$(JSLIBDIR)/assets/tether.min.js:
	URL=https://cdnjs.cloudflare.com/ajax/libs/tether/1.4.7/js && PKG=$$(basename $@) \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG}

$(JSLIBDIR)/assets/imagesloaded.pkgd.min.js:
	URL=https://cdnjs.cloudflare.com/ajax/libs/jquery.imagesloaded/4.1.4 \
	  && PKG=$$(basename $@) \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG}

$(JSLIBDIR)/assets/mqtt.min.js:
	URL=https://cdnjs.cloudflare.com/ajax/libs/mqtt/4.3.5 && PKG=$$(basename $@) \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG}

$(JSLIBDIR)/assets/axios.min.js:
	$(call axios-asset-recipe)

$(JSLIBDIR)/assets/axios.min.js.map:
	$(call axios-asset-recipe)

$(JSLIBDIR)/assets/glfx.min.js:
	URL=https://cdn.jsdelivr.net/npm/glfx@0.0.4 && PKG=$$(basename $@) \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG}

$(JSLIBDIR)/bootstrap-4.6.1-dist.zip:
	VERSION=$$(echo $@ | sed -E -e 's/.*bootstrap-([0-9]+[.][0-9]+[.][0-9]+)-.*/\1/') \
	  URL=https://github.com/twbs/bootstrap/releases/download/v$${VERSION} \
	  PKG=$$(basename $@) \
	  ; curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG}

$(JSLIBDIR)/bootstrap-icons-1.3.0.zip:
	URL=https://github.com/twbs/icons/releases/download/v1.3.0 && PKG=$$(basename $@) \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG}

$(JSLIBDIR)/bootstrap/css/bootstrap-icons.css: $(JSLIBDIR)/bootstrap/css
	URL=https://cdn.jsdelivr.net/npm/bootstrap-icons@1.3.0/font && PKG=$$(basename $@) \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG}

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
	  && curl $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG}

$(JSLIBDIR)/assets/ProjectedMaterial.module.js:
	URL=https://unpkg.com/three-projected-material/build && PKG=$$(basename $@) \
	  && curl $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG} \
	  &&  sed "s,'three','/static/assets/three.module.js'," $@ > temp.js && mv temp.js $@

$(JSLIBDIR)/assets/opencv.js:
	URL=https://docs.opencv.org/4.10.0 && PKG=$$(basename $@) \
	  && curl $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG}

$(JSLIBDIR)/assets/doxygen-awesome.css:
	URL=https://raw.githubusercontent.com/jothepro/doxygen-awesome-css/main && PKG=$$(basename $@) \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG}

django-secrets: $(SECRETSDIR)/django/secrets.py

$(SECRETSDIR)/django/secrets.py:
	mkdir -p $(SECRETSDIR)/django
	echo -n SECRET_KEY= > $@
	python3 -c 'import secrets; print("\x27" + "".join([secrets.choice("abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)") for i in range(50)]) + "\x27")' >> $@
	echo "DATABASE_PASSWORD='$${DBPASS:-$$(openssl rand -base64 12)}'" >> $@
	chmod 0600 $@

test/geckodriver.tar.gz:
	@echo "Downloading geckodriver..."
	@set -e \
		; BASE_URL=https://github.com/mozilla/geckodriver/releases \
		; GVERSION=$$(curl -sL -o /dev/null -w '%{url_effective}' \
			"$${BASE_URL}/latest" \
			| sed -e 's,.*/,,') \
		; mkdir -p test \
		; curl -sL \
			"$${BASE_URL}/download/$${GVERSION}/geckodriver-$${GVERSION}-linux64.tar.gz" \
			--output "test/geckodriver.tar.gz"
