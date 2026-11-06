# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE := intel/scenescape-observation-processor
TARGET := scenescape-observation-processor-runtime
USES_SCENE_COMMON := yes

include ../common.mk

PROTO_SRC := proto/observation_processor.proto
GRPC_API_DIR := src/observation_processor/grpc_api

# Generate typed gRPC stubs for local development. The image build runs the
# same generation in the builder stage; generated files are never committed.
.PHONY: proto
proto:
	python3 -m grpc_tools.protoc -Iproto \
	  --python_out=$(GRPC_API_DIR) --grpc_python_out=$(GRPC_API_DIR) \
	  $(PROTO_SRC)
	sed -i 's/^import observation_processor_pb2 as/from . import observation_processor_pb2 as/' \
	  $(GRPC_API_DIR)/observation_processor_pb2_grpc.py
