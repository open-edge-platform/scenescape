# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

ARG RUNTIME_OS_IMAGE=python:3.11-slim-bookworm@sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3

FROM intel/scenescape-common-base AS scenescape-positioning-builder

FROM ${RUNTIME_OS_IMAGE} AS scenescape-positioning-runtime

LABEL org.opencontainers.image.description="Scenescape Positioning Service"
LABEL org.opencontainers.image.vendor="Intel Corporation"
LABEL org.opencontainers.image.licenses="Apache-2.0"

ARG USER_ID=1001
ARG GROUP_ID=1001
ENV WSUSER=scenescape
ENV PYTHONPATH=/app

RUN groupadd -g ${GROUP_ID} $WSUSER \
    && useradd -r -m -u ${USER_ID} -g ${GROUP_ID} -s /bin/bash $WSUSER

COPY positioning/requirements-runtime.txt /tmp/requirements-runtime.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements-runtime.txt \
    && rm -f /tmp/requirements-runtime.txt

COPY --from=scenescape-positioning-builder \
    /usr/local/lib/python3.11/site-packages/scene_common \
    /usr/local/lib/python3.11/site-packages/scene_common
COPY --from=scenescape-positioning-builder \
    /usr/local/lib/python3.11/site-packages/fast_geometry \
    /usr/local/lib/python3.11/site-packages/fast_geometry
COPY --chown=$USER_ID:$GROUP_ID positioning/src /app
COPY --chown=$USER_ID:$GROUP_ID positioning/config /app/config

USER $USER_ID:$GROUP_ID
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD python3 -c "import os,sys; sys.exit(0 if os.path.exists('/tmp/positioning-ready') else 1)"
ENTRYPOINT ["python3", "/app/positioning_service.py"]

FROM scenescape-positioning-runtime AS scenescape-positioning-test
COPY --chown=$USER_ID:$GROUP_ID tests/sscape_tests/positioning /app/tests
ENTRYPOINT []
CMD ["python3", "-m", "unittest", "discover", "-s", "/app/tests"]