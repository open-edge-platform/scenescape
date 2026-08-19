FROM docker.io/intel/dlstreamer-pipeline-server:2026.2.0-ubuntu24-rc1

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir --break-system-packages --no-deps pupil-apriltags

# Restore the pipeline server user from the base image (uid/gid 1999, in the video group).
USER intelmicroserviceuser
