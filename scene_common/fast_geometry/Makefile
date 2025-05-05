# Copyright (C) 2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.


# Target library name.
TARGET=fast_geometry

# List of source files to build.
SRC= \
    line.cpp \
    point.cpp \
    polygon.cpp \
    rectangle.cpp \

OBJS=$(patsubst %.cpp,%.oxx,$(SRC))

# Compile time flags. Need c++17 for std::variant.
CFLAGS = -O3 -Wall --shared -std=c++17 -fPIC -Werror -Wall -Wextra

# Add pybind neede flags
CFLAGS +=$(shell python3 -m pybind11 --includes)

# Add opencv flags
CFLAGS +=$(shell pkg-config --cflags opencv4)

# Add/Remove sanity checks as desired
#CFLAGS += -DENABLE_MATRIX_CHECKS
#CFLAGS += -DENABLE_RECTANGLE_CHECKS

# Define Library name for bindings
CFLAGS += -DLIBRARY_NAME=$(TARGET)

# Build with debug code on (mostly prints)
#CFLAGS += -DDEBUG_GEOM -g

# Linking flags, for opencv
LDFLAGS=$(shell pkg-config --libs opencv4)

# Suffix used for pybind library name
LIB_SUFFIX=$(shell python3-config --extension-suffix)

# Find python version
PYTHON_VERSION = $(shell python3 -c "import sys; print(f'python{sys.version_info.major}.{sys.version_info.minor}')")

# Rules: How to build .oxx from .cpp
%.oxx: %.cpp
	g++ $(CFLAGS) -c $? -o $@

# Link the target library
$(TARGET): $(OBJS) bindings.oxx
	g++ $(CFLAGS) $(OBJS) bindings.oxx -o $(TARGET)$(LIB_SUFFIX) $(LDFLAGS)

# Clean library and intermediate files
clean:
	rm -f $(TARGET) $(OBJS) bindings.oxx

# Where to install final library
install: $(TARGET)
	mkdir /usr/local/lib/$(PYTHON_VERSION)/dist-packages/$(TARGET)
	install $(TARGET)$(LIB_SUFFIX) /usr/local/lib/$(PYTHON_VERSION)/dist-packages/$(TARGET)/$(TARGET)$(LIB_SUFFIX)
	install init.py /usr/local/lib/$(PYTHON_VERSION)/dist-packages/$(TARGET)/__init__.py

all: clean $(TARGET)

.DEFAULT_GOAL := all
