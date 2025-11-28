# Makefile for building and running serialization benchmarks

# Compiler and flags
CXX = g++
CXXFLAGS = -std=c++17 -O3 -march=x86-64-v3 -Wall -Wextra

# Directories
IDL_DIR = idl
CPP_DIR = cpp
PYTHON_DIR = python
BUILD_DIR = build
DATA_DIR = data
CPP_GENERATED = $(CPP_DIR)/generated
PYTHON_GENERATED = $(PYTHON_DIR)/generated
PROTO_OUT = $(CPP_GENERATED)/proto
FBS_OUT = $(CPP_GENERATED)/fbs

# Schema files
DETECTION_PROTO = $(IDL_DIR)/detection-message.proto
DETECTION_FBS = $(IDL_DIR)/detection-message.fbs
REGULATED_PROTO = $(IDL_DIR)/regulated-message.proto
REGULATED_FBS = $(IDL_DIR)/regulated-message.fbs

# Source files
BENCHMARK_SOURCE = $(CPP_DIR)/benchmark.cpp

# Generated files
DETECTION_PROTO_SRC = $(PROTO_OUT)/detection-message.pb.cc
REGULATED_PROTO_SRC = $(PROTO_OUT)/regulated-message.pb.cc
DETECTION_FBS_HDR = $(FBS_OUT)/detection-message_generated.h
REGULATED_FBS_HDR = $(FBS_OUT)/regulated-message_generated.h

# Build configuration
INCLUDES = -I$(PROTO_OUT) -I$(FBS_OUT) -I/usr/local/include
LIBS = -lprotobuf -lpthread -lsimdjson -lbenchmark

# Targets
BENCHMARK_TARGET = $(BUILD_DIR)/benchmark

.PHONY: all clean prerequisites proto fbs test-data python-proto-fbs \
        run run-cpp run-python help


# ============================================================================
# Main targets
# ============================================================================

help:
	@echo "Serialization Benchmark Makefile"
	@echo ""
	@echo "Setup:"
	@echo "  prerequisites    Install dependencies and setup .venv (requires sudo)"
	@echo ""
	@echo "Build:"
	@echo "  all              Build all benchmarks (default)"
	@echo "  proto            Generate C++ protobuf code"
	@echo "  fbs              Generate C++ FlatBuffers code"
	@echo "  python-proto-fbs Generate Python protobuf and FlatBuffers code"
	@echo "  test-data        Generate test data files"
	@echo ""
	@echo "Run Benchmarks:"
	@echo "  run              Run all C++ and Python benchmarks"
	@echo "  run-cpp          Run all C++ benchmarks"
	@echo "  run-python       Run all Python benchmarks"
	@echo ""
	@echo "Cleanup:"
	@echo "  clean            Remove all build artifacts and generated code"

all: $(BENCHMARK_TARGET)

# Install system dependencies via apt
prerequisites: 
	@echo "Installing system dependencies..."
	@echo "This requires sudo privileges."
	sudo apt-get update
	sudo apt-get install -y \
		build-essential \
		g++ \
		cmake \
		protobuf-compiler \
		libprotobuf-dev \
		flatbuffers-compiler \
		libflatbuffers-dev \
		libsimdjson-dev \
		libbenchmark-dev \
		rapidjson-dev \
		python3 \
		python3-pip \
		python3-venv \
		python3-full
	@echo "System dependencies installed successfully."
	@echo ""
	@echo "Creating Python virtual environment..."
	python3 -m venv .venv
	@echo "Installing Python packages in virtual environment..."
	./.venv/bin/pip install --upgrade pip
	./.venv/bin/pip install pytest pytest-benchmark protobuf flatbuffers orjson
	@echo ""
	@echo "Setup complete!"
	@echo "Virtual environment created at .venv/"
	@echo "To activate: source .venv/bin/activate"

# ============================================================================
# Code generation
# ============================================================================

# Generate protobuf C++ code
proto: $(DETECTION_PROTO_SRC) $(REGULATED_PROTO_SRC)

$(DETECTION_PROTO_SRC): $(DETECTION_PROTO)
	@echo "Generating detection protobuf C++ code..."
	@mkdir -p $(PROTO_OUT)
	protoc --cpp_out=$(PROTO_OUT) -I$(IDL_DIR) $(DETECTION_PROTO)

$(REGULATED_PROTO_SRC): $(REGULATED_PROTO)
	@echo "Generating regulated protobuf C++ code..."
	@mkdir -p $(PROTO_OUT)
	protoc --cpp_out=$(PROTO_OUT) -I$(IDL_DIR) $(REGULATED_PROTO)

# Generate FlatBuffers C++ code
fbs: $(DETECTION_FBS_HDR) $(REGULATED_FBS_HDR)

$(DETECTION_FBS_HDR): $(DETECTION_FBS)
	@echo "Generating detection FlatBuffers C++ code..."
	@mkdir -p $(FBS_OUT)
	flatc --cpp -o $(FBS_OUT) $(DETECTION_FBS)

$(REGULATED_FBS_HDR): $(REGULATED_FBS)
	@echo "Generating regulated FlatBuffers C++ code..."
	@mkdir -p $(FBS_OUT)
	flatc --cpp -o $(FBS_OUT) $(REGULATED_FBS)

# Generate Python protobuf and flatbuffers code
python-proto-fbs:
	@if [ ! -d ".venv" ]; then \
		echo "Virtual environment not found. Run 'make prerequisites' first."; \
		exit 1; \
	fi
	@echo "Generating Python protobuf and FlatBuffers code..."
	@mkdir -p $(PYTHON_GENERATED)/proto $(PYTHON_GENERATED)/fbs
	protoc --python_out=$(PYTHON_GENERATED)/proto -I$(IDL_DIR) $(DETECTION_PROTO) $(REGULATED_PROTO)
	flatc --python -o $(PYTHON_GENERATED)/fbs $(DETECTION_FBS) $(REGULATED_FBS)
	@echo "Python generated code ready."

# Generate test data files from template
test-data:
	@if [ ! -d ".venv" ]; then \
		echo "Virtual environment not found. Run 'make prerequisites' first."; \
		exit 1; \
	fi
	@echo "Generating test data files..."
	./.venv/bin/python $(PYTHON_DIR)/generate_test_data.py

# ============================================================================
# Build targets
# ============================================================================

$(BENCHMARK_TARGET): $(BENCHMARK_SOURCE) $(DETECTION_PROTO_SRC) $(REGULATED_PROTO_SRC) $(DETECTION_FBS_HDR) $(REGULATED_FBS_HDR)
	@echo "Compiling unified benchmark..."
	@mkdir -p $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) $(INCLUDES) -o $@ \
		$(BENCHMARK_SOURCE) $(DETECTION_PROTO_SRC) $(REGULATED_PROTO_SRC) $(LIBS)
	@echo "Build complete: $@"

# ============================================================================
# Run benchmarks
# ============================================================================

run: run-cpp run-python

run-cpp: $(BENCHMARK_TARGET) test-data
	@echo "\n=== Running C++ benchmarks (1000 objects per message) ==="
	$(BENCHMARK_TARGET) $(DATA_DIR)/detection-message-1000.json $(DATA_DIR)/regulated-message-1000.json --benchmark_repetitions=5

run-python: test-data python-proto-fbs
	@if [ ! -d ".venv" ]; then \
		echo "Virtual environment not found. Run 'make prerequisites' first."; \
		exit 1; \
	fi
	@echo "\n=== Running Python benchmarks (1000 objects per message) ==="
	cd $(PYTHON_DIR) && ../.venv/bin/pytest benchmark.py -v -k "not regulated_flatbuffers"

# ============================================================================
# Cleanup
# ============================================================================

clean:
	@echo "Cleaning build artifacts..."
	rm -rf $(BUILD_DIR)
	rm -rf $(CPP_GENERATED)
	rm -rf $(PYTHON_GENERATED)
	rm -rf $(PYTHON_DIR)/__pycache__
	rm -rf .pytest_cache
	rm -rf .benchmarks
	rm -rf .venv
	@echo "Clean complete."

