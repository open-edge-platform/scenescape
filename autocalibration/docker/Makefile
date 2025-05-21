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

IMAGE=scenescape-camcalibration
VERSION:=$(shell cat ../version.txt)

-include Makefile.camcalibfiles Makefile.scenecommonfiles

default: Makefile.camcalibfiles Dockerfile camcalibration.tar scene_common.tar
	env BUILDKIT_PROGRESS=plain \
	  docker build $(REBUILDFLAGS) \
	    --build-arg http_proxy=$(http_proxy) \
	    --build-arg https_proxy=$(https_proxy) \
	    --build-arg no_proxy=$(no_proxy) \
	    --build-arg CERTDOMAIN=$(CERTDOMAIN) \
	    --build-arg USER_ID=$$UID \
	    --rm -t $(IMAGE):$(VERSION) . \
	&& docker tag $(IMAGE):$(VERSION) $(IMAGE):latest

FPCAMCALIB=$(addprefix ../,$(CAMCALIBFILES))
camcalibration.tar: Makefile.camcalibfiles $(FPCAMCALIB)
	tar -cf $@ -C .. $(CAMCALIBFILES)

FPSCENECOMMON=$(addprefix ../,$(SCENECOMMONFILES))
scene_common.tar: Makefile.scenecommonfiles $(FPSCENECOMMON)
	tar -chf $@ -C .. $(SCENECOMMONFILES)

Makefile.scenecommonfiles:
	echo 'define SCENECOMMONFILES' > $@
	( IFS="$$(printf '\n+')" \
	  ; git ls-tree --full-tree -r --name-only --full-name HEAD scene_common \
	) | sort | sed -e 's/$$/ \\/ ; $$s/ .$$//' >> $@
	echo endef >> $@

rebuild:
	make REBUILDFLAGS="--no-cache"
