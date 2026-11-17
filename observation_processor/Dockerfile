# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

ARG RUNTIME_OS_IMAGE=python:3.11-slim-bookworm@sha256:94a8fee35252d06ab75856f15f12c7bae67b10e8a6da93c7fded82b2610926cd

FROM intel/scenescape-common-base AS scenescape-observation-processor-builder

# TBB headers for the frustum-gaussian C++ extension (common-base already has
# cmake, g++, Eigen and pybind11).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libtbb-dev \
    && rm -rf /var/lib/apt/lists/*

# All Python dependencies are installed into a relocatable venv in this stage;
# the runtime stage only copies the finished venv.
RUN python3 -m venv /opt/venv
COPY observation_processor/requirements-runtime.txt /tmp/
RUN /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements-runtime.txt \
    && rm -f /tmp/requirements-runtime.txt

# Build and install the frustum-gaussian wheel (C++/TBB kernel) into the venv.
COPY spatial_performance_primitives/frustum_gaussian /tmp/frustum_gaussian
RUN make -C /tmp/frustum_gaussian build PYTHON=/opt/venv/bin/python \
    && rm -rf /tmp/frustum_gaussian

# scene_common and fast_geometry come pre-installed in common-base system site-packages.
RUN cp -r /usr/local/lib/python3.11/site-packages/scene_common \
    /opt/venv/lib/python3.11/site-packages/scene_common \
    && cp -r /usr/local/lib/python3.11/site-packages/fast_geometry \
       /opt/venv/lib/python3.11/site-packages/fast_geometry

FROM ${RUNTIME_OS_IMAGE} AS scenescape-observation-processor-runtime

LABEL org.opencontainers.image.description="Scenescape Observation Processor Service"
LABEL org.opencontainers.image.vendor="Intel Corporation"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/open-edge-platform/scenescape"

ARG USER_ID=1001
ARG GROUP_ID=1001
ENV WSUSER=scenescape
ENV SCENESCAPE_HOME=/home/$WSUSER/Scenescape
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/opt/venv/bin:$PATH"

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# ca-certificates: Manager REST over TLS; libgl1 + libgomp1: open3d runtime;
# libtbb12: frustum-gaussian C++ kernel
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libgl1 \
        libgomp1 \
        libtbb12 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g ${GROUP_ID} $WSUSER \
    && useradd -r -m -u ${USER_ID} -g ${GROUP_ID} -s /bin/bash $WSUSER

COPY --from=scenescape-observation-processor-builder /opt/venv /opt/venv
COPY --chown=${USER_ID}:${GROUP_ID} observation_processor/src /app
COPY --chown=${USER_ID}:${GROUP_ID} spatial_performance_primitives/observation_conditioning /app/observation_conditioning

USER ${USER_ID}:${GROUP_ID}
WORKDIR /app
HEALTHCHECK CMD python3 -m observation_processor.healthcheck
ENTRYPOINT ["python3", "-m", "observation_processor.server"]
