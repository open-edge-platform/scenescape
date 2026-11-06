# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Mock observation processor service for tracker service tests. The contract is mounted at runtime
# (/protos/observation_processor.proto) and loaded with grpc.protos_and_services().
FROM python:3.13-slim

RUN pip install --no-cache-dir grpcio==1.76.0 grpcio-tools==1.76.0

COPY mock_projection.py /app/mock_projection.py

USER 10001
CMD ["python", "/app/mock_projection.py"]
