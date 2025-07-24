# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

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
