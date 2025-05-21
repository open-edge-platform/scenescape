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
VERSION:=$(shell cat ../sscape/version.txt)
CERTDOMAIN=scenescape.intel.com
SECRETSDIR=../secrets
DBDIR=../db
MIGRATIONSDIR=../migrations
MEDIADIR=../media
DOCSDIR=../docs
DATASETS=../datasets
USERVIDEODIR=../videos
JSLIBDIR=jslibs
MQTTUSERS="percebro.auth=cameras controller.auth=scenectrl browser.auth=webuser calibration.auth=calibration"
AUTHFILES=$(addprefix $(SECRETSDIR)/,$(shell echo $(MQTTUSERS) | sed -e 's/=[^ ]*//g'))
CURL_FLAGS=--connect-timeout 5 --max-time 120 --retry 5 --retry-delay 0
FORCE_VAAPI ?= 0
THREEJS_VERSION=168

define axios-asset-recipe =
	URL=https://cdn.jsdelivr.net/npm/axios/dist && PKG=$$(basename $@) \
	  && curl -f $(CURL_FLAGS) --location --create-dirs --output $@ $${URL}/$${PKG}
endef

-include Makefile.sscapefiles Makefile.editorfiles Makefile.jsmexamples Makefile.scenecommonfiles

default: scenescape interface broker install-models scene_common

scenescape: Makefile.sscapefiles SceneScape.tar scene_common.tar Dockerfile \
	scenescape-init secrets jslibraries jsm-examples editor-files \
	cJSON.bundle open_model_zoo.bundle database-dirs user-dirs
	env BUILDKIT_PROGRESS=plain \
	  docker build $(REBUILDFLAGS) \
	    --build-arg http_proxy=$(http_proxy) \
	    --build-arg https_proxy=$(https_proxy) \
	    --build-arg no_proxy=$(no_proxy) \
	    --build-arg CERTDOMAIN=$(CERTDOMAIN) \
	    --build-arg USER_ID=$$UID \
	    --build-arg FORCE_VAAPI=$(FORCE_VAAPI) \
	    --rm -t $(IMAGE):$(VERSION) . \
	&& docker tag $(IMAGE):$(VERSION) $(IMAGE):latest

interface: Dockerfile-interface firefox-profile.tar geckodriver.tar.gz scene_common.tar
	env BUILDKIT_PROGRESS=plain \
	  docker build $(REBUILDFLAGS) -f $< \
	    --build-arg http_proxy=$(http_proxy) \
	    --build-arg https_proxy=$(https_proxy) \
	    --build-arg no_proxy=$(no_proxy) \
	    --rm -t $(IMAGE)-interface:$(VERSION) . \
	&& docker tag $(IMAGE)-interface:$(VERSION) $(IMAGE)-interface:latest

broker: Dockerfile-broker
	env BUILDKIT_PROGRESS=plain \
	  docker build $(REBUILDFLAGS) -f $< \
	    --build-arg http_proxy=$(http_proxy) \
	    --build-arg https_proxy=$(https_proxy) \
	    --build-arg no_proxy=$(no_proxy) \
	    --rm -t $(IMAGE)-broker:$(VERSION) . \
	&& docker tag $(IMAGE)-broker:$(VERSION) $(IMAGE)-broker:latest

model-installer-img: Dockerfile-model-installer
	env BUILDKIT_PROGRESS=plain \
	  docker build $(REBUILDFLAGS) -f $< \
	    --build-arg http_proxy=$(http_proxy) \
	    --build-arg https_proxy=$(https_proxy) \
	    --build-arg no_proxy=$(no_proxy) \
	    --rm -t $(IMAGE)-model-installer:$(VERSION) . \
	  && docker tag $(IMAGE)-model-installer:$(VERSION) $(IMAGE)-model-installer:latest

sources: Dockerfile-sources
	env BUILDKIT_PROGRESS=plain \
	  docker build $(REBUILDFLAGS) -f $< \
	    --build-arg http_proxy=$(http_proxy) \
	    --build-arg https_proxy=$(https_proxy) \
	    --build-arg no_proxy=$(no_proxy) \
	    --rm -t $(IMAGE)-sources:$(VERSION) . \
	&& docker tag $(IMAGE)-sources:$(VERSION) $(IMAGE)-sources:latest

scene_common:
	ln -sf ../scene_common ../autocalibration
	ln -sf ../scene_common ../controller
	ln -sf ../scene_common ../percebro
	mkdir -p ../controller/utils && ln -sf ../../utils/waitforbroker ../controller/utils/waitforbroker
	mkdir -p ../percebro/utils && ln -sf ../../utils/waitforbroker ../percebro/utils/waitforbroker

# To force a complete clean build, do:
#   make rebuild
rebuild:
	make -C $(DOCSDIR) clean
	IMAGES=$$(egrep -i '^FROM' Dockerfile* | awk '{print $$2}' \
	    | grep -v $(IMAGE) | sort -u) \
	  ; for i in $$IMAGES ; do docker pull $$i ; done
	make REBUILDFLAGS="--no-cache"

$(DBDIR):
	mkdir -p $@

$(MIGRATIONSDIR):
	mkdir -p $@

$(MEDIADIR):
	mkdir -p $@

$(DATASETS):
	mkdir -p $@

$(USERVIDEODIR):
	mkdir -p $@

editor-files: $(EDITORFILES)

jsm-examples: $(JSMEXAMPLES)

$(EDITORFILES):
	if [ ! -f $@ ] ; then \
	  curl -f $(CURL_FLAGS) --location --create-dirs --output $@ \
	  https://raw.githubusercontent.com/mrdoob/three.js/r$(THREEJS_VERSION)/$@; \
	fi

$(JSMEXAMPLES):
	$(eval RELPATH=$@)
	if [ ! -f $(JSLIBDIR)/examples/$@ ] ; then \
	  curl -f $(CURL_FLAGS) --location --create-dirs --output $(JSLIBDIR)/examples/$@ \
	  https://cdn.jsdelivr.net/npm/three@0.$(THREEJS_VERSION).0/examples/$(RELPATH) \
	  && sed -i -e "s,'three','/static/assets/three.module.js'," $(JSLIBDIR)/examples/$@; \
	fi

database-dirs: $(DBDIR) $(MIGRATIONSDIR) $(MEDIADIR) $(DATASETS)

user-dirs: $(USERVIDEODIR)

install-models: scenescape model-installer-img \
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

.PHONY: doxygen-docs

doxygen-docs:
	make -C $(DOCSDIR)

FPSSCAPE=$(addprefix ../,$(SSCAPEFILES))
SceneScape.tar: doxygen-docs $(FPSSCAPE) Makefile.sscapefiles
	tar -chf $@ -C .. $(SSCAPEFILES)

FPSCENECOMMON=$(addprefix ../,$(SCENECOMMONFILES))
scene_common.tar:  Makefile.scenecommonfiles $(FPSCENECOMMON)
	tar -cf $@ -C .. $(SCENECOMMONFILES)

cJSON.bundle:
	URL=https://github.com/DaveGamble && PKG=$(basename $@) && CURDIR=$${PWD} && TMP=/tmp/sscape.$$$$ && mkdir $${TMP} && cd $${TMP} && git clone $${URL}/$${PKG}.git && cd $${PKG} && git bundle create ../$${PKG}.bundle --all && cd $${CURDIR} && mv $${TMP}/$${PKG}.bundle . && rm -rf $${TMP}

open_model_zoo.bundle:
	URL=https://github.com/openvinotoolkit && PKG=$(basename $@) && CURDIR=$${PWD} && TMP=/tmp/sscape.$$$$ && mkdir $${TMP} && cd $${TMP} && git clone $${URL}/$${PKG}.git && cd $${PKG} && git bundle create ../$${PKG}.bundle --all && cd $${CURDIR} && mv $${TMP}/$${PKG}.bundle . && rm -rf $${TMP}

Makefile.sscapefiles:
	echo 'define SSCAPEFILES' > $@
	( IFS="$$(printf '\n+')" \
	  ; cd .. \
	  ; rsync -R --list-only --exclude-from=exclude_for_release.txt  \
	    $$(git ls-tree --full-tree -r --name-only --full-name HEAD | sed '$$p' ) \
	    | egrep -v '^d' \
	) | cut -c 47- | sort \
	| sed -e '/^\(autocalibration\|controller\|ci\|docker\|docs\|dlstreamer-pipeline-server\|kubernetes\|licenses\|sample_data\|scene_common\|sscape\/tools\|percebro\|tests\)[/]/d ; /^[.]/d' \
	      -e '/^\(\|deploy[.]sh\|third-party-programs[.]txt\)$$/d' \
	      -e '/^utils[/]/ { /waitforbroker/!d }' \
	      -e 's/$$/ \\/' \
	| sed -e '$$s/ .$$//' \
	    >> $@
	echo endef >> $@

secrets:
	make -C ../secrets

certificate:
	CERTDOMAIN=$(CERTDOMAIN) make -C ../certificates

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
