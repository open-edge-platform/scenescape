# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM osrf/ros:jazzy-desktop

# Set proxy for apt
ARG http_proxy=http://proxy-dmz.intel.com:911
ARG https_proxy=http://proxy-dmz.intel.com:912
ENV http_proxy=${http_proxy}
ENV https_proxy=${https_proxy}
ENV HTTP_PROXY=${http_proxy}
ENV HTTPS_PROXY=${https_proxy}

# Install Nav2 and Turtlebot3 packages
RUN apt-get update && \
    apt-get install -y \
        ros-jazzy-turtlebot3-gazebo \
        ros-jazzy-nav2-bringup \
        ros-jazzy-rmw-zenoh-cpp \
        python3-pip \
    && pip3 install --no-cache-dir --break-system-packages paho-mqtt \
    && rm -rf /var/lib/apt/lists/*

# Set Turtlebot3 model
ENV TURTLEBOT3_MODEL=waffle

# Source ROS setup
RUN echo "source /opt/ros/jazzy/setup.bash" >> /root/.bashrc

# Default command
CMD ["bash"]
