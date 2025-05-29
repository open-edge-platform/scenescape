# Copyright (C) 2025 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

IMAGE=scenescape-percebro
VERSION:=$(shell cat version.txt)
FORCE_VAAPI ?= 0

default: Dockerfile cJSON.bundle open_model_zoo.bundle
	env BUILDKIT_PROGRESS=plain \
	  docker build $(REBUILDFLAGS) \
	    --build-arg http_proxy=$(http_proxy) \
	    --build-arg https_proxy=$(https_proxy) \
	    --build-arg no_proxy=$(no_proxy) \
	    --build-arg CERTDOMAIN=$(CERTDOMAIN) \
	    --build-arg USER_ID=$$UID \
	    --build-arg FORCE_VAAPI=$(FORCE_VAAPI) \
	    --rm -t $(IMAGE):$(VERSION) .. -f ./Dockerfile \
	&& docker tag $(IMAGE):$(VERSION) $(IMAGE):latest


cJSON.bundle:
	URL=https://github.com/DaveGamble && PKG=$(basename $@) && CURDIR=$${PWD} && TMP=/tmp/sscape.$$$$ && mkdir $${TMP} && cd $${TMP} && git clone $${URL}/$${PKG}.git && cd $${PKG} && git bundle create ../$${PKG}.bundle --all && cd $${CURDIR} && mv $${TMP}/$${PKG}.bundle . && rm -rf $${TMP}

open_model_zoo.bundle:
	URL=https://github.com/openvinotoolkit && PKG=$(basename $@) && CURDIR=$${PWD} && TMP=/tmp/sscape.$$$$ && mkdir $${TMP} && cd $${TMP} && git clone $${URL}/$${PKG}.git && cd $${PKG} && git bundle create ../$${PKG}.bundle --all && cd $${CURDIR} && mv $${TMP}/$${PKG}.bundle . && rm -rf $${TMP}

rebuild:
	make REBUILDFLAGS="--no-cache"
