# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM ros:jazzy

# Install required Python packages and ROS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    ros-jazzy-nav2-msgs \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir --break-system-packages paho-mqtt scipy

# Copy the bridge script
COPY mqtt_to_ros_bridge.py /mqtt_to_ros_bridge.py

# Create a startup script that sources ROS and passes all arguments
RUN echo '#!/bin/bash\nsource /opt/ros/jazzy/setup.bash\nexec python3 /mqtt_to_ros_bridge.py "$@"' > /entrypoint.sh && chmod +x /entrypoint.sh

# Run the startup script with passed arguments
ENTRYPOINT ["/entrypoint.sh"]

