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

IMAGE=scenescape-controller
VERSION:=$(shell cat ../version.txt)

-include Makefile.controllerfiles Makefile.rvfiles

default: Makefile.rvfiles robot_vision.tar Makefile.controllerfiles \
	controller.tar scene_common.tar Dockerfile
	env BUILDKIT_PROGRESS=plain \
	  docker build $(REBUILDFLAGS) \
	    --build-arg http_proxy=$(http_proxy) \
	    --build-arg https_proxy=$(https_proxy) \
	    --build-arg no_proxy=$(no_proxy) \
	    --build-arg CERTDOMAIN=$(CERTDOMAIN) \
	    --build-arg USER_ID=$$UID \
	    --rm -t $(IMAGE):$(VERSION) . \
	&& docker tag $(IMAGE):$(VERSION) $(IMAGE):latest

FPCONTROLLER=$(addprefix ../,$(CONTROLLERFILES))
controller.tar: Makefile.controllerfiles $(FPCONTROLLER)
	tar -chf $@ -C .. $(CONTROLLERFILES)

scene_common.tar:
	tar -chf $@ ../scene_common

robot_vision.tar: $(FPROBOTVIS) Makefile.rvfiles
	tar -cf $@ -C ../ $(RVFILES)

FPROBOTVIS=$(addprefix ../,$(RVFILES))
Makefile.rvfiles:
	echo 'define RVFILES' > $@
	( IFS="$$(printf '\n+')" \
	  ; git ls-tree --full-tree -r --name-only --full-name HEAD controller \
	) | grep '/robot_vision/' | sed 's|^controller/||' | sort \
	| sed -e 's/$$/ \\/ ; $$s/ .$$//' >> $@
	echo endef >> $@

rebuild:
	make REBUILDFLAGS="--no-cache"
