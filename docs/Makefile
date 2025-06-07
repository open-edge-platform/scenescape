# Copyright (C) 2023 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

VERSION:=$(shell cat ../version.txt)
DOXYGEN_IMAGE:=ghcr.io/doxygen/doxygen
LOG_PATH=$$PWD/docs/doxygen/doxygen.log

default: doxygen/html/index.html

doxygen/html/index.html: doxygen/Doxyfile.common doxygen/Doxyfile doxygen/custom.css
	@cd .. \
	; export SSCAPE_VERSION=$(VERSION) \
	; echo GENERATING DOXYGEN DOCUMENTATION \
	; echo Writing log to $(LOG_PATH)... \
	; docker run --rm \
	    -e SSCAPE_VERSION \
	    -u $(shell id -u):$(shell id -g) \
	    -v $$PWD:/doxygen/ $(DOXYGEN_IMAGE) \
	    /doxygen/docs/doxygen/Doxyfile \
	    >$(LOG_PATH) 2>&1 \
	&& cp -r docs/user-guide/images docs/doxygen/html/images \
	&& cp -r docs/user-guide/files docs/doxygen/html/files \
	&& cp -r docs/doxygen/doxygen-inline-scripts.js docs/doxygen/html \
	&& echo Please visit $$PWD/docs/doxygen/html/index.html to view the full documentation

.PHONY: clean

clean:
	rm -rf doxygen/doxygen.log doxygen/html
