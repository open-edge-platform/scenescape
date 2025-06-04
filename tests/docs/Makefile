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

VERSION:=$(shell cat ../../version.txt)
COMMON_DIR=../../docs/doxygen

default: doxygen/html/index.html

doxygen/html/index.html: $(COMMON_DIR)/Doxyfile.common doxygen/Doxyfile $(COMMON_DIR)/custom.css
	@cd ../.. \
	; export SSCAPE_VERSION=$(VERSION) \
	; echo GENERATING DOXYGEN DOCUMENTATION FOR TESTS \
	; doxygen tests/docs/doxygen/Doxyfile > /dev/null 2>&1 \
	; echo Please visit $$PWD/docs/doxygen/html/index.html to view the full documentation
