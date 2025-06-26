# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

VERSION:=$(shell cat ../../version.txt)
COMMON_DIR=../../docs/doxygen

default: doxygen/html/index.html

doxygen/html/index.html: $(COMMON_DIR)/Doxyfile.common doxygen/Doxyfile $(COMMON_DIR)/custom.css
	@cd ../.. \
	; export SSCAPE_VERSION=$(VERSION) \
	; echo GENERATING DOXYGEN DOCUMENTATION FOR TESTS \
	; doxygen tests/docs/doxygen/Doxyfile > /dev/null 2>&1 \
	; echo Please visit $$PWD/docs/doxygen/html/index.html to view the full documentation
