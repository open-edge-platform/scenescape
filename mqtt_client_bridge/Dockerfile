# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

ARG ROS_DISTRO=jazzy
FROM ghcr.io/ika-rwth-aachen/mqtt_client:${ROS_DISTRO}-slim

# Copy startup script
COPY --chmod=755 mqtt_start.sh /mqtt_start.sh

# Set environment variables for ROS 2 distributed setup
ENV ROS_LOCALHOST_ONLY=0

# Override CMD to use custom config from mounted volume (keep base ENTRYPOINT)
CMD ["/mqtt_start.sh"]

