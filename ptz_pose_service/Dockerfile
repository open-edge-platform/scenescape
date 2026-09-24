# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

ARG RUNTIME_OS_IMAGE=python:3.11-slim-bookworm@sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3

# =========================
# STAGE 1: scene_common source (for the runtime stage COPY --from below)
# =========================
FROM intel/scenescape-common-base AS ptz-pose-service-builder

# =========================
# STAGE 2: RUNTIME STAGE
# =========================
FROM ${RUNTIME_OS_IMAGE} AS ptz-pose-service-runtime

# Label image with description and metadata
LABEL org.opencontainers.image.description="Scenescape's PTZ Camera Pose Service"
LABEL org.opencontainers.image.vendor="Intel Corporation"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/open-edge-platform/scenescape"
LABEL org.opencontainers.image.documentation="https://github.com/open-edge-platform/scenescape/blob/main/README.md"

ARG USER_ID=1001
ARG GROUP_ID=1001
ENV WSUSER=scenescape
ENV SCENESCAPE_HOME=/home/$WSUSER/Scenescape

ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Update and upgrade base OS packages, create non-root user
RUN apt update && apt upgrade -y \
    && groupadd -g ${GROUP_ID} $WSUSER \
    && useradd -r -m -u ${USER_ID} -g ${GROUP_ID} -s /bin/bash $WSUSER

COPY ptz_pose_service/requirements-runtime.txt /tmp/
RUN pip install --no-cache-dir \
        -r /tmp/requirements-runtime.txt \
    && rm -rf /tmp/*.txt

# Copy compiled packages from the common-base builder (use system site-packages directly)
COPY --chown=$WSUSER:$WSUSER --from=ptz-pose-service-builder \
    /usr/local/lib/python3.11/site-packages/scene_common \
    /usr/local/lib/python3.11/site-packages/scene_common

COPY --chown=$WSUSER:$WSUSER --from=ptz-pose-service-builder \
    /usr/local/lib/python3.11/site-packages/fast_geometry \
    /usr/local/lib/python3.11/site-packages/fast_geometry

# Vendored dlstreamer.onvif library (pure-python ONVIF discovery/PTZ control).
# Fetched to ptz_pose_service/.vendor/dlstreamer on the host by `make vendor-deps`
# (see ptz_pose_service/Makefile) to avoid GitHub's unauthenticated-download
# rate limiting hitting container builds. Only the pure-python `dlstreamer`
# package is copied (not the `gstgva` GStreamer bindings, which this service
# does not need).
COPY --chown=$WSUSER:$WSUSER ptz_pose_service/.vendor/dlstreamer/python/dlstreamer \
    /usr/local/lib/python3.11/site-packages/dlstreamer

# Copy application code and config
COPY --chown=$USER_ID:$GROUP_ID ./ptz_pose_service/src /app
COPY --chown=$USER_ID:$GROUP_ID ./ptz_pose_service/config /app/config

USER $USER_ID:$GROUP_ID
HEALTHCHECK CMD true

ENTRYPOINT ["python3", "/app/ptz_pose_service.py"]
