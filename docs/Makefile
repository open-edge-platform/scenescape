# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

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
